"""J&T · Painel de Qualidade 1BD, 5CD e CSAT — API e dashboard web.

A taxa 1BD é baseada nas ocorrências do relatório de avaliação, não na deduplicação
por remessa. A gestão atual define o responsável por base, e os filtros nunca
reclassificam bases de outras regiões como pertencentes ao Orlean.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import base64
import csv
import datetime as dt
from io import StringIO
import os
from pathlib import Path
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from database import rows, scalar, setup, IS_POSTGRES, IS_API, IS_SUPABASE, DATABASE_URL

ROOT = Path(__file__).resolve().parent
ORLEAN = 'ORLEAN DA SILVA DO NASCIMENTO'
USUARIO = os.getenv('DASH_USER', '').strip()
REQUIRE_DASH_AUTH = os.getenv('REQUIRE_DASH_AUTH', '').lower() in ('1','true','yes')
REQUIRE_REMOTE_DB = os.getenv('REQUIRE_REMOTE_DB', '').lower() in ('1','true','yes')
SENHA = os.getenv('DASH_PASS', '').strip()
try:
    META = float(os.getenv('META_1BD', '0.80'))
except ValueError:
    META = 0.80

app = FastAPI(title='J&T — Qualidade | 1BD · 5CD · CSAT', version='1.1.0')


@app.middleware('http')
async def basic_auth(request: Request, call_next):
    if request.url.path == '/health':
        return await call_next(request)
    if REQUIRE_DASH_AUTH and not (USUARIO and SENHA):
        return JSONResponse({'erro':'DASH_USER e DASH_PASS devem ser configurados'}, status_code=503)
    if REQUIRE_REMOTE_DB and not (IS_POSTGRES or IS_API or IS_SUPABASE):
        return JSONResponse({'erro':'Banco remoto nao configurado; defina JT_STORAGE_MODE e credenciais'}, status_code=503)
    if REQUIRE_DASH_AUTH and USUARIO and SENHA:
        auth=request.headers.get('authorization', '')
        success=False
        if auth.startswith('Basic '):
            try:
                userpass=base64.b64decode(auth[6:]).decode('utf-8')
                user,pwd=userpass.split(':',1)
                success=secrets.compare_digest(user,USUARIO) and secrets.compare_digest(pwd,SENHA)
            except (ValueError,UnicodeError):
                pass
        if not success:
            return JSONResponse({'erro':'Autenticação obrigatória'}, status_code=401,
                                headers={'WWW-Authenticate':'Basic realm="J&T Qualidade"'})
    return await call_next(request)


@app.get('/')
def inicio():
    return FileResponse(ROOT/'static'/'index.html')


@app.get('/static/{arquivo}')
def static(arquivo: str):
    if arquivo not in ('style.css','app.js','5cd.js','csat.js'):
        raise HTTPException(404,'Arquivo não encontrado')
    return FileResponse(ROOT/'static'/arquivo)


def dados_orlean():
    return rows('''SELECT r.data_avaliacao AS data, r.remessa, r.ticket, r.entregue,
               r.base_original, g.nome AS base, g.codigo AS codigo, g.uf, g.rm,
               g.coordenador, g.supervisor, g.sc, g.tipo_sc, g.situacao,
               r.problema
        FROM jt_1bd_registros r JOIN jt_1bd_gestao g
           ON g.base_chave=r.base_chave
        WHERE g.rm=? ORDER BY r.data_avaliacao, g.nome''', (ORLEAN,))


def parse_date(value, fallback):
    if not value:
        return fallback
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422,f'Data inválida: {value}. Use AAAA-MM-DD.')


def week_start(day):
    return day-dt.timedelta(days=day.weekday())


def filter_dim(items, uf='', sc='', base=''):
    return [r for r in items if (not uf or r['uf']==uf)
            and (not sc or r['sc']==sc)
            and (not base or r['base']==base)]


def agg(items):
    c=len(items)
    yes=sum(int(r['entregue']) for r in items)
    return {'total':c,'sim':yes,'nao':c-yes,'taxa':(yes/c if c else None)}


def compare(current, previous):
    a=current.get('taxa'); b=previous.get('taxa')
    return {'pp':round((a-b)*100,2) if a is not None and b is not None else None,
            'percentual':round((a/b-1)*100,2) if a is not None and b not in (None,0) else None}


def daterange(a,b):
    for i in range((b-a).days+1):
        yield a+dt.timedelta(days=i)


def period(items,a,b):
    return [r for r in items if a.isoformat()<=r['data']<=b.isoformat()]


def time_series(items, start, end):
    daily=defaultdict(list)
    for r in items:daily[r['data']].append(r)
    out=[]
    for day in daterange(start,end):
        cur=agg(daily.get(day.isoformat(), []))
        prev=agg(daily.get((day-dt.timedelta(days=7)).isoformat(), []))
        out.append({'data':day.isoformat(),**cur,'vs_d7':compare(cur,prev)})
    return out


def weekly_series(items):
    by_week=defaultdict(list)
    for r in items:by_week[week_start(dt.date.fromisoformat(r['data']))].append(r)
    out=[]
    for d in sorted(by_week):
        cur=agg(by_week[d]);prev=agg(by_week.get(d-dt.timedelta(days=7),[]))
        out.append({'inicio':d.isoformat(), 'fim':(d+dt.timedelta(days=6)).isoformat(),
                    **cur,'vs_semana_anterior':compare(cur,prev)})
    return out


def month_series(items):
    by_month=defaultdict(list)
    for r in items:by_month[r['data'][:7]].append(r)
    return [{'mes':m,**agg(v)} for m,v in sorted(by_month.items())]


def rankings(items, semana, anterior, hoje, dia_d7, dimension, min_volume=1):
    by_period=defaultdict(list)
    by_current=defaultdict(list)
    by_prior=defaultdict(list)
    by_day=defaultdict(list)
    by_day_d7=defaultdict(list)
    for r in items:
        key=r[dimension] or 'Sem atribuição'
        by_period[key].append(r)
    for r in semana:by_current[r[dimension] or 'Sem atribuição'].append(r)
    for r in anterior:by_prior[r[dimension] or 'Sem atribuição'].append(r)
    for r in hoje:by_day[r[dimension] or 'Sem atribuição'].append(r)
    for r in dia_d7:by_day_d7[r[dimension] or 'Sem atribuição'].append(r)
    out=[]
    for key, registros in by_period.items():
        cur=agg(registros)
        if cur['total']<min_volume:continue
        w=agg(by_current.get(key,[]));p=agg(by_prior.get(key,[]))
        today=agg(by_day.get(key,[]));past_day=agg(by_day_d7.get(key,[]))
        d={'nome':key,**cur, 'semana':w,'semana_passada':p,
           'variacao_semana':compare(w,p),
           'mesmo_dia_semana_passada':past_day,
           'dia_atual':today,
           'variacao_d7':compare(today,past_day)}
        if dimension=='base':
            d.update({'uf':registros[0]['uf'], 'sc':registros[0]['sc'],
                      'codigo':registros[0]['codigo']})
        elif dimension=='sc':
            d.update({'tipo':registros[0]['tipo_sc']})
        out.append(d)
    return sorted(out, key=lambda x:(x['taxa'] if x['taxa'] is not None else 2,-x['total'],x['nome']))


@app.get('/health')
def health():
    if REQUIRE_DASH_AUTH and not (USUARIO and SENHA):
        raise HTTPException(503, 'Painel sem autenticação configurada')
    if REQUIRE_REMOTE_DB and not (IS_POSTGRES or IS_API or IS_SUPABASE):
        raise HTTPException(503, 'Configure JT_STORAGE_MODE=supabase e as variaveis SUPABASE_URL e SUPABASE_SECRET_KEY')
    try:
        setup()
        from importar_5cd import setup_5cd
        setup_5cd()
        return {'ok':True,'indicador':'1BD + 5CD + CSAT',
                'registros':scalar('SELECT COUNT(*) AS n FROM jt_1bd_registros'),
                'registros_5cd':scalar('SELECT COUNT(*) AS n FROM jt_5cd_registros')}
    except Exception as e:
        raise HTTPException(503,str(e))


@app.get('/api/filtros')
def filtros(uf: str='', sc: str=''):
    setup()
    data=dados_orlean()
    data=filter_dim(data,uf=uf)
    scs=sorted(set(r['sc'] for r in data if r['sc']))
    if sc:data=filter_dim(data,sc=sc)
    return {'ufs':sorted(set(r['uf'] for r in dados_orlean() if r['uf'])),
            'scs':scs,
            'bases':[{'nome':nome,'uf':uf1} for nome,uf1 in sorted(set((r['base'],r['uf']) for r in data))]}


@app.get('/api/dashboard')
def dashboard(inicio: Optional[str]=None,fim: Optional[str]=None,uf: str='',sc: str='',
              base: str='',min_volume:int=Query(1,ge=1,le=1000)):
    setup()
    todos=dados_orlean()
    if not todos:
        return {'sem_dados':True,'mensagem':'Importe as planilhas com python importar_excel.py'}
    data_max=dt.date.fromisoformat(max(r['data'] for r in todos))
    data_min=dt.date.fromisoformat(min(r['data'] for r in todos))
    end=min(parse_date(fim,data_max),data_max)
    start=parse_date(inicio,max(data_min,end-dt.timedelta(days=27)))
    if start > data_max and inicio:
        return {'sem_dados': True, 'mensagem':
                f'Não há dados para o período selecionado. Última data importada: {data_max.strftime("%d/%m/%Y")}.'}
    if start>end:raise HTTPException(422,'Data inicial maior que a data final')
    selecionados=filter_dim(todos,uf,sc,base)
    registros=period(selecionados,start,end)
    semana_inicio=week_start(end)
    semana_fim=semana_inicio+dt.timedelta(days=6)
    semana_anterior_inicio=semana_inicio-dt.timedelta(days=7)
    semana_anterior_fim=semana_inicio-dt.timedelta(days=1)
    semana=period(selecionados,semana_inicio,semana_fim)
    anterior=period(selecionados,semana_anterior_inicio,semana_anterior_fim)
    dia=period(selecionados,end,end)
    dia_anterior=period(selecionados,end-dt.timedelta(days=7),end-dt.timedelta(days=7))
    agora=agg(registros)
    w=agg(semana)
    wprev=agg(anterior)
    today=agg(dia)
    last_day=agg(dia_anterior)
    semanal_series=weekly_series(selecionados)
    base_ranking=rankings(registros,semana,anterior,dia,dia_anterior,'base',min_volume=min_volume)
    sc_ranking=rankings(registros,semana,anterior,dia,dia_anterior,'sc',min_volume=min_volume)
    uf_ranking=rankings(registros,semana,anterior,dia,dia_anterior,'uf',min_volume=1)
    return {
        'sem_dados':False,
        'contexto':{'inicio':start.isoformat(),'fim':end.isoformat(),'primeira_data':data_min.isoformat(),
                    'ultima_data':data_max.isoformat(),'rm':ORLEAN,
                    'uf':uf,'sc':sc,'base':base,'meta':META,
                    'semana_inicio':semana_inicio.isoformat(),'semana_fim':semana_fim.isoformat(),
                    'semana_passada_inicio':semana_anterior_inicio.isoformat(),
                    'semana_passada_fim':semana_anterior_fim.isoformat(),
                    'nota':'Comparativos semanais usam semanas de segunda a domingo; a semana atual inclui somente as datas disponíveis.'},
        'resumo':agora,
        'semana_atual':{**w,'vs_semana_passada':compare(w,wprev)},
        'semana_passada':wprev,
        'dia_atual':{**today,'vs_mesmo_dia_semana_passada':compare(today,last_day)},
        'mesmo_dia_semana_passada':last_day,
        'evolucao_diaria':time_series(selecionados,max(start,data_min),end),
        'evolucao_semanal':semanal_series[-16:],
        'evolucao_mensal':month_series(selecionados),
        'ranking_sc':sc_ranking,
        'ranking_bases':base_ranking,
        'ranking_uf':uf_ranking,
        'qualidade_dados':{'bases_gestao':scalar('SELECT COUNT(*) AS n FROM jt_1bd_gestao'),
                            'ocorrencias_totais':scalar('SELECT COUNT(*) AS n FROM jt_1bd_registros'),
                            'ocorrencias_orlean':len(todos)}
    }


@app.get('/api/exportar.csv')
def exportar(inicio: Optional[str]=None,fim: Optional[str]=None,uf: str='',sc: str='',base: str=''):
    setup()
    data=dados_orlean()
    if not data:
        raise HTTPException(404,'Sem dados para exportar')
    data_max=dt.date.fromisoformat(max(r['data'] for r in data))
    data_min=dt.date.fromisoformat(min(r['data'] for r in data))
    end=min(parse_date(fim,data_max),data_max)
    start=parse_date(inicio,data_min)
    if start>end:raise HTTPException(422,'Data inicial maior que a final')
    data=period(filter_dim(data,uf,sc,base),start,end)
    keys=['data','remessa','ticket','entregue','base_original','base','codigo','uf','rm',
          'coordenador','supervisor','sc','tipo_sc','situacao','problema']
    io=StringIO()
    writer=csv.writer(io,delimiter=';')
    writer.writerow(['Data','Remessa','Ticket','Entregue 1BD?','Base original','Nome base Gestão',
                     'Código da base','UF','R/M','Coordenador','Supervisor','S/C','Tipo S/C','Situação','Problema'])
    for row in data:
        writer.writerow([('Sim' if row[key] else 'Não') if key=='entregue' else row[key] for key in keys])
    output='\ufeff'+io.getvalue()
    filename=f'J-T-1BD-Orlean_{start}_{end}.csv'
    return StreamingResponse(iter([output]),media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition':f'attachment; filename="{filename}"'})


from indicador_5cd import router as router_5cd
app.include_router(router_5cd)

from indicador_csat import router as router_csat
app.include_router(router_csat)


@app.get('/api/indicadores')
def indicadores():
    """Status real: 1BD implantado; métricas 5CD e CSAT dependem de layouts validados."""
    return {
        'nome':'Painel de Qualidade',
        'indicadores':[
            {'id':'1bd','nome':'Entregas concluídas em 1BD','status':'ativo','fonte':'TikTok — 明細_Detalhamento','endpoint':'/api/dashboard'},
            {'id':'5cd','nome':'Remessas 5CD em aberto','status':'ativo','fonte':'TikTok — BD + Dados históricos','endpoint':'/api/5cd/dashboard'},
            {'id':'csat','nome':'Satisfação do cliente','status':'ativo','fonte':'TikTok CSAT — BASE, colunas D/O/S','endpoint':'/api/csat/dashboard'},
        ],
        'filtro_regional':'ORLEAN DA SILVA DO NASCIMENTO',
        'comparativos':'Semanas fixas de segunda a domingo + mesmo dia da semana passada'
    }
