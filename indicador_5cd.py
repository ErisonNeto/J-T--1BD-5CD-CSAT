"""API 5CD — volumes de remessas presentes no relatório (não é taxa de SLA).
Semanas SEG-DOM; média semanal de snapshots diários para não somar a mesma
remessa em vários dias. Fonte temporal: coluna I (data do relatório TikTok).
"""
from __future__ import annotations
from collections import defaultdict
import csv
import datetime as dt
from io import StringIO
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from database import rows, scalar, setup
from importar_5cd import setup_5cd

router=APIRouter(prefix='/api/5cd',tags=['5CD'])
ORLEAN='ORLEAN DA SILVA DO NASCIMENTO'


def carregados():
    return rows('''SELECT r.data_relatorio AS data, r.remessa, r.dias_base,
        r.atraso,r.faixa,r.operacao,r.package_id,r.motivo,
        r.base_original,g.codigo,g.nome AS base,g.uf,g.rm,
        g.coordenador,g.supervisor,g.sc,g.tipo_sc
      FROM jt_5cd_registros r JOIN jt_1bd_gestao g ON g.base_chave=r.base_chave
      WHERE g.rm=? ORDER BY r.data_relatorio,r.base_chave,r.remessa''',(ORLEAN,))


def procurar_dia(s, default):
    if not s:return default
    try:return dt.date.fromisoformat(s)
    except ValueError:raise HTTPException(422,f'Data inválida: {s}')


def week_start(day):return day-dt.timedelta(days=day.weekday())


def filtrar(data,uf='',sc='',base=''):
    return [x for x in data if (not uf or x['uf']==uf) and (not sc or x['sc']==sc)
            and (not base or x['base']==base)]


def metrics(records):
    n=len(records)
    return {'total':n, 'aging_5_9':sum(1 for x in records if x['dias_base'] is not None and 5<=x['dias_base']<10),
       'aging_10_14':sum(1 for x in records if x['dias_base'] is not None and 10<=x['dias_base']<15),
       'aging_15_19':sum(1 for x in records if x['dias_base'] is not None and 15<=x['dias_base']<20),
       'aging_20_plus':sum(1 for x in records if x['dias_base'] is not None and x['dias_base']>=20),
       'aging_10_plus':sum(1 for x in records if x['dias_base'] is not None and x['dias_base']>=10),
       'atraso_sim':sum(1 for x in records if x['atraso'] and x['atraso'].strip().lower()=='sim'),
       'aging_sem_dado':sum(1 for x in records if x['dias_base'] is None)}


def compare_count(current, previous):
    if current is None or previous is None:
        return {'abs':None,'percentual':None}
    return {'abs':round(current-previous,2),
            'percentual':round((current/previous-1)*100,2) if previous else None}


def daily_by_key(records,key=None):
    result=defaultdict(lambda:defaultdict(list))
    for r in records:
        group=r[key] or 'Sem S/C' if key else '__all__'
        result[group][r['data']].append(r)
    return result


def avg_dias(mapa,start,end,dias_relatorio=None):
    # Um relatório existe mesmo quando uma base filtrada tem 0 remessas.
    # Ausência de linha para a base naquele dia deve ser 0, não dado faltante.
    dates=[day for day in (dias_relatorio if dias_relatorio is not None else mapa) if start<=day<=end]
    if not dates:return {'media':None,'dias':0,'soma':0}
    v=[len(mapa.get(day,[])) for day in dates]
    return {'media':round(sum(v)/len(v),2),'dias':len(v),'soma':sum(v)}


def get_rankings(records,ref,week0,week1,prior0,prior1,dimension,min_volume=1,dias_relatorio=None):
    dias=daily_by_key(records,dimension)
    out=[]
    for name,m in dias.items():
        ult=metrics(m.get(ref,[]));week=avg_dias(m,week0,week1,dias_relatorio);prev=avg_dias(m,prior0,prior1,dias_relatorio)
        d7=(dt.date.fromisoformat(ref)-dt.timedelta(days=7)).isoformat()
        day7=len(m.get(d7,[])) if dias_relatorio is not None and d7 in dias_relatorio else (len(m[d7]) if d7 in m else None)
        if ult['total']<min_volume and (week['media'] or 0)<min_volume:continue
        sample=next(iter(next(iter(m.values()))))
        out.append({'nome':name,**ult,'semana':week,'semana_passada':prev,
             'variacao_semana':compare_count(week['media'],prev['media']),
             'mesmo_dia_semana_passada':day7,
             'variacao_d7':compare_count(ult['total'] if dias_relatorio is not None and ref in dias_relatorio else (ult['total'] if ref in m else None),day7),
             'codigo':sample['codigo'],'uf':sample['uf'],'sc':sample['sc'],
             'coordenador':sample['coordenador'],'supervisor':sample['supervisor'],
             'tipo':sample['tipo_sc']})
    return sorted(out,key=lambda r:(-r['total'],-(r['semana']['media'] or 0),r['nome']))


@router.get('/filtros')
def filtros(uf:str='',sc:str=''):
    setup_5cd()
    original=carregados()
    data=filtrar(original,uf=uf)
    scs=sorted({r['sc'] for r in data if r['sc']})
    if sc:data=filtrar(data,sc=sc)
    return {'ufs':sorted({r['uf'] for r in original if r['uf']}),
         'scs':scs,'bases':[{'nome':nome,'uf':unidade} for nome,unidade in
              sorted({(r['base'],r['uf']) for r in data})]}


@router.get('/dashboard')
def dashboard(inicio:str='',fim:str='',uf:str='',sc:str='',base:str='',
              min_volume:int=Query(1,ge=1,le=10000)):
    setup_5cd()
    source=carregados()
    if not source:
        return {'sem_dados':True,'mensagem':'Nenhuma remessa 5CD importada. Rode python importar_5cd.py.'}
    limite_min=dt.date.fromisoformat(min(r['data'] for r in source));limite_max=dt.date.fromisoformat(max(r['data'] for r in source))
    end=min(procurar_dia(fim,limite_max),limite_max)
    start=procurar_dia(inicio,max(limite_min,end-dt.timedelta(days=27)))
    if start > limite_max and inicio:
        return {'sem_dados': True, 'mensagem':
                f'Não há dados para o período selecionado. Última data importada: {limite_max.strftime("%d/%m/%Y")}.'}
    if start>end:raise HTTPException(422,'Data inicial maior que a final')
    report_dates={r['data'] for r in source}
    filtered=filtrar(source,uf,sc,base)
    by=daily_by_key(filtered)['__all__']
    av=[d for d in report_dates if start.isoformat()<=d<=end.isoformat()]
    reference=max(av) if av else end.isoformat()
    date_ref=dt.date.fromisoformat(reference)
    wk=week_start(date_ref)
    prev0=wk-dt.timedelta(days=7)
    prev1=wk-dt.timedelta(days=1)
    wk1=wk+dt.timedelta(days=6)
    dia7=(date_ref-dt.timedelta(days=7)).isoformat()
    semana=avg_dias(by,wk.isoformat(),wk1.isoformat(),report_dates)
    anterior=avg_dias(by,prev0.isoformat(),prev1.isoformat(),report_dates)
    today=metrics(by.get(reference,[]))
    prior=len(by.get(dia7,[])) if dia7 in report_dates else None
    daily=[]
    for day in sorted(d for d in report_dates if start.isoformat()<=d<=end.isoformat()):
        snapshot=metrics(by.get(day,[]))
        d7=(dt.date.fromisoformat(day)-dt.timedelta(days=7)).isoformat()
        daily.append({'data':day,**snapshot,'vs_d7':compare_count(snapshot['total'],len(by.get(d7,[])) if d7 in report_dates else None)})
    weeks=defaultdict(dict)
    for day in report_dates:
        st=week_start(dt.date.fromisoformat(day)).isoformat()
        weeks[st][day]=by.get(day,[])
    weekly=[]
    for st in sorted(weeks):
        ds=dt.date.fromisoformat(st)
        cur=avg_dias(weeks[st],st,(ds+dt.timedelta(days=6)).isoformat())
        prevdate=(ds-dt.timedelta(days=7)).isoformat()
        prevwk=avg_dias(weeks.get(prevdate,{}),prevdate,(ds-dt.timedelta(days=1)).isoformat())
        weekly.append({'inicio':st,'fim':(ds+dt.timedelta(days=6)).isoformat(),**cur,
                       'vs_semana_anterior':compare_count(cur['media'],prevwk['media'])})
    # Rankings calculados com TODOS os dias do filtro dimensional, não apenas o período
    # escolhido, pois os comparativos de segunda-domingo e D-7 precisam de histórico.
    reg_ref=[r for r in filtered if r['data']==reference]
    data_disp=[r for r in filtered if r['data']==reference]
    return {
        'sem_dados':False,
        'contexto':{'inicio':start.isoformat(),'fim':end.isoformat(),'data_referencia':reference,
          'primeira_data':limite_min.isoformat(),'ultima_data':limite_max.isoformat(),
          'semana_inicio':wk.isoformat(),'semana_fim':wk1.isoformat(),
          'semana_passada_inicio':prev0.isoformat(),'semana_passada_fim':prev1.isoformat(),
          'uf':uf,'sc':sc,'base':base,'rm':ORLEAN,
          'nota':'I é a data do relatório. Semana é média dos snapshots disponíveis entre segunda e domingo. Não somar a mesma remessa entre dias; dias sem relatório não são zero.'},
        'resumo':today,
        'aging_variacao_semana':{name:compare_count(
           (round(sum(metrics(by.get(day,[]))[name] for day in report_dates if wk.isoformat()<=day<=wk1.isoformat())/semana['dias'],2) if semana['dias'] else None),
           (round(sum(metrics(by.get(day,[]))[name] for day in report_dates if prev0.isoformat()<=day<=prev1.isoformat())/anterior['dias'],2) if anterior['dias'] else None))
           for name in ('aging_5_9','aging_10_14','aging_15_19','aging_20_plus','aging_10_plus')},
        'semana_atual':{**semana,'vs_semana_passada':compare_count(semana['media'],anterior['media'])},
        'semana_passada':anterior,
        'dia_atual':{'data':reference,'total':today['total'],
               'vs_mesmo_dia_semana_passada':compare_count(today['total'] if reference in by else None,prior)},
        'mesmo_dia_semana_passada':prior,
        'evolucao_diaria':daily,'evolucao_semanal':weekly[-16:],
        'ranking_uf':get_rankings(filtered,reference,wk.isoformat(),wk1.isoformat(),prev0.isoformat(),prev1.isoformat(),'uf',1,report_dates),
        'ranking_sc':get_rankings(filtered,reference,wk.isoformat(),wk1.isoformat(),prev0.isoformat(),prev1.isoformat(),'sc',min_volume,report_dates),
        'ranking_bases':get_rankings(filtered,reference,wk.isoformat(),wk1.isoformat(),prev0.isoformat(),prev1.isoformat(),'base',min_volume,report_dates),
        'qualidade_dados':{'remessas_datas':len(filtered),'registros_ult_data':len(reg_ref),
          'total_banco':scalar('SELECT COUNT(*) AS n FROM jt_5cd_registros')}
    }


@router.get('/exportar.csv')
def exportar(inicio:str='',fim:str='',uf:str='',sc:str='',base:str=''):
    setup_5cd()
    source=carregados()
    if not source:raise HTTPException(404,'Sem 5CD no banco')
    dmin=dt.date.fromisoformat(min(r['data'] for r in source));dmax=dt.date.fromisoformat(max(r['data'] for r in source))
    end=min(procurar_dia(fim,dmax),dmax); start=procurar_dia(inicio,dmin)
    if start>end:raise HTTPException(422,'Datas incorretas')
    selected=(r for r in filtrar(source,uf,sc,base) if start.isoformat()<=r['data']<=end.isoformat())
    stream=StringIO()
    w=csv.writer(stream,delimiter=';')
    columns=['data','remessa','package_id','base_original','base','codigo','uf','rm','coordenador','supervisor','sc','tipo_sc','dias_base','faixa','atraso','operacao','motivo']
    w.writerow(['Data relatório (col I)','Remessa (col O)','Package ID','Base original (col P)',
       'Base gestão','Código','UF','R/M','Coordenador','Supervisor','S/C','Tipo S/C',
       'Dias em base','Faixa','Em atraso?','Operação','Motivo'])
    for r in selected:
        vals=[]
        for k in columns:
            s=str(r.get(k) if r.get(k) is not None else '')
            # CSV seguro para abertura em Excel: não executar fórmulas de campos não confiáveis
            if s.startswith(('=','+','-','@')) and k not in ('dias_base',):s="'"+s
            vals.append(s)
        w.writerow(vals)
    return StreamingResponse(iter(['\ufeff'+stream.getvalue()]),media_type='text/csv; charset=utf-8',
      headers={'Content-Disposition':f'attachment; filename="JT-5CD-Orlean_{start}_{end}.csv"'})
