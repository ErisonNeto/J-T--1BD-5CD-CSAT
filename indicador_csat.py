"""J&T CSAT: taxa por semana oficial da coluna D (W44/W45), R/M Orlean.

Fonte: BASE!D (semana), BASE!O (base), BASE!S (avaliação 1/0).
JOIN com Gestão efetuado durante a carga, com foto do responsável por base.
A data H serve somente à evolução diária, sem redefinir a semana oficial.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date, timedelta
from functools import lru_cache
from io import StringIO
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from database import IS_API, IS_SUPABASE, IS_POSTGRES, connection, rows

router = APIRouter(prefix='/api/csat', tags=['CSAT'])

COLS = (
    'id', 'ano', 'semana_numero', 'semana_id', 'semana_descricao',
    'data_avaliacao', 'base_chave', 'base', 'codigo', 'uf', 'rm',
    'coordenador', 'supervisor', 'sc', 'tipo_sc', 'avaliacao',
    'ticket', 'tracking', 'categoria', 'arquivo_origem',
)
CSAT_QUERY = f"SELECT {', '.join(COLS)} FROM jt_csat_registros ORDER BY ano, semana_numero, id"


def setup_local():
    if IS_API or IS_SUPABASE or IS_POSTGRES:
        return
    with connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS jt_csat_registros (
             id TEXT PRIMARY KEY, ano INTEGER, semana_numero INTEGER,
             semana_id TEXT, semana_descricao TEXT, data_avaliacao TEXT,
             base_chave TEXT, base TEXT, codigo TEXT, uf TEXT, rm TEXT,
             coordenador TEXT, supervisor TEXT, sc TEXT, tipo_sc TEXT,
             avaliacao INTEGER, ticket TEXT, tracking TEXT, categoria TEXT,
             arquivo_origem TEXT)''')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_csat_semana ON jt_csat_registros(ano, semana_numero)')
        conn.commit()


def dados():
    if IS_SUPABASE:
        raise HTTPException(503, 'CSAT está no PostgreSQL da J&T. Configure JT_STORAGE_MODE=api no Render após publicar a tabela.')
    setup_local()
    try:
        return rows(CSAT_QUERY)
    except Exception as exc:
        # Banco remoto sem tabela criada, falhas de rede e ausência de permissões
        # não podem virar zero avaliações silenciosamente.
        raise HTTPException(503, f'CSAT ainda não está acessível no banco: {type(exc).__name__}. Confira publicação e JT API.') from exc


def filtro_dim(registros, uf='', sc='', base=''):
    return [r for r in registros if (not uf or r.get('uf') == uf)
            and (not sc or (r.get('sc') or 'Sem S/C') == sc)
            and (not base or r.get('base') == base)]


def agrupar(registros):
    n = len(registros)
    sim = sum(int(r['avaliacao']) for r in registros)
    return {'total': n, 'sim': sim, 'nao': n-sim,
            'taxa': round(sim/n, 8) if n else None}


def comparar(atual, anterior):
    a, b = atual.get('taxa'), anterior.get('taxa')
    return {'pp': round((a-b)*100, 2) if a is not None and b is not None else None,
            'percentual': round((a/b-1)*100, 2) if a is not None and b not in (None, 0) else None}


def semana_sort(s):
    # Período oficial definido pela coluna D, sem recalcular semana pelo dia H.
    try:
        year, week = s.split('-W')
        return int(year), int(week)
    except (ValueError, AttributeError):
        return (0, 0)


def dim_options(data, uf='', sc=''):
    pool = filtro_dim(data, uf=uf)
    scs = sorted({r.get('sc') or 'Sem S/C' for r in pool})
    if sc:
        pool = filtro_dim(pool, sc=sc)
    return {
        'ufs': sorted({r['uf'] for r in data if r.get('uf')}),
        'scs': scs,
        'bases': [{'nome': name, 'uf': u} for name, u in sorted(
            {(r['base'], r.get('uf') or '') for r in pool})],
        'semanas': [
            {'id': week, 'rotulo': next((r['semana_descricao'] for r in data if r['semana_id'] == week), week)}
            for week in sorted({r['semana_id'] for r in data}, key=semana_sort)
        ],
    }


def serie_semanal(data):
    semana_map = defaultdict(list)
    for r in data:
        semana_map[r['semana_id']].append(r)
    out = []
    prev = None
    for s in sorted(semana_map, key=semana_sort):
        summary = agrupar(semana_map[s])
        out.append({'semana': s,
                    'rotulo': semana_map[s][0]['semana_descricao'],
                    **summary,
                    'vs_anterior': comparar(summary, prev) if prev else {'pp': None, 'percentual': None}})
        prev = summary
    return out


def serie_diaria(data, inicio=None, fim=None):
    # A coluna H informa a data da avaliação e pode cair fora do intervalo
    # textual da semana D. Mantemos os dois campos independentes.
    bydate = defaultdict(list)
    for r in data:
        if r.get('data_avaliacao'):
            bydate[r['data_avaliacao']].append(r)
    return [{'data': d, **agrupar(bydate[d])} for d in sorted(bydate)]


def rankear(periodo, semana_atual, semana_anterior, coluna, minimo):
    grupos = defaultdict(list)
    for r in periodo:
        key = r.get(coluna) or 'Sem S/C'
        grupos[key].append(r)
    weeks_a = defaultdict(list)
    weeks_b = defaultdict(list)
    for r in semana_atual:
        weeks_a[r.get(coluna) or 'Sem S/C'].append(r)
    for r in semana_anterior:
        weeks_b[r.get(coluna) or 'Sem S/C'].append(r)
    out = []
    for key, items in grupos.items():
        cur = agrupar(items)
        if cur['total'] < minimo:
            continue
        ref = items[0]
        a = agrupar(weeks_a[key])
        b = agrupar(weeks_b[key])
        out.append({'nome': key, 'uf': ref.get('uf') or '',
                    'sc': ref.get('sc') or 'Sem S/C',
                    'tipo': ref.get('tipo_sc') or 'Sem S/C',
                    **cur, 'semana': a, 'semana_passada': b,
                    'variacao_semana': comparar(a, b)})
    return sorted(out, key=lambda x: (x['taxa'] if x['taxa'] is not None else 2, -x['nao'], x['nome']))


@router.get('/filtros')
def filtros(uf: str = '', sc: str = ''):
    return dim_options(dados(), uf, sc)


@router.get('/dashboard')
def dashboard(semana_inicio: str = '', semana_fim: str = '',
              uf: str = '', sc: str = '', base: str = '',
              min_volume: int = Query(1, ge=1, le=1000)):
    allrows = dados()
    if not allrows:
        return {'sem_dados': True, 'mensagem': 'Nenhuma avaliação CSAT importada. Rode python publicar_csat_via_api.py --aplicar --confirmar-banco jt_indicadores.'}
    options = dim_options(allrows)
    semanas = [x['id'] for x in options['semanas']]
    last = semanas[-1]
    s_from = semana_inicio or last
    s_to = semana_fim or last
    if s_from not in semanas or s_to not in semanas:
        raise HTTPException(422, 'Semana fora do histórico CSAT. Use os valores disponibilizados nos filtros.')
    if semana_sort(s_from) > semana_sort(s_to):
        raise HTTPException(422, 'Semana inicial maior que a final.')
    filtered = filtro_dim(allrows, uf, sc, base)
    periodo = [r for r in filtered if semana_sort(s_from) <= semana_sort(r['semana_id']) <= semana_sort(s_to)]
    current = [r for r in filtered if r['semana_id'] == s_to]
    pos = semanas.index(s_to)
    previous_id = semanas[pos-1] if pos > 0 else None
    previous = [r for r in filtered if r['semana_id'] == previous_id] if previous_id else []
    cur = agrupar(current)
    prev = agrupar(previous)
    total = agrupar(periodo)
    return {
        'sem_dados': False,
        'contexto': {'rm': 'ORLEAN DA SILVA DO NASCIMENTO',
                     'semana_inicio': s_from, 'semana_fim': s_to,
                     'ultima_semana': last, 'semana_anterior': previous_id,
                     'semanas': options['semanas'],
                     'nota': 'A semana oficial é a coluna D (W44/W45). A coluna H é usada apenas na evolução diária.'},
        'resumo': total,
        'semana_atual': cur,
        'semana_passada': prev,
        'variacao_semana': comparar(cur, prev),
        'evolucao_semanal': serie_semanal(filtered),
        'evolucao_diaria': serie_diaria(periodo),
        'ranking_uf': rankear(periodo, current, previous, 'uf', 1),
        'ranking_sc': rankear(periodo, current, previous, 'sc', min_volume),
        'ranking_bases': rankear(periodo, current, previous, 'base', min_volume),
        'ranking_categorias': rankear(periodo, current, previous, 'categoria', 1),
        'qualidade_dados': {'total_orlean': len(allrows), 'semanas': len(semanas)},
    }


@router.get('/exportar.csv')
def exportar(semana_inicio: str = '', semana_fim: str = '',
             uf: str = '', sc: str = '', base: str = ''):
    data = dados()
    if not data:
        raise HTTPException(404, 'CSAT sem avaliações para exportar.')
    semanas = sorted({r['semana_id'] for r in data}, key=semana_sort)
    a, b = semana_inicio or semanas[-1], semana_fim or semanas[-1]
    if a not in semanas or b not in semanas or semana_sort(a)>semana_sort(b):
        raise HTTPException(422, 'Período semanal inválido.')
    items = [r for r in filtro_dim(data, uf, sc, base)
             if semana_sort(a)<=semana_sort(r['semana_id'])<=semana_sort(b)]
    # Exportação agregada: sem IDs de tickets ou tracking para evitar exposição
    # desnecessária de identificadores operacionais em um dashboard de acesso por link.
    bykey = defaultdict(list)
    for r in items:
        bykey[(r['semana_id'],r['base'],r['uf'],r.get('sc') or 'Sem S/C')].append(r)
    csvfile = StringIO()
    writer = csv.writer(csvfile, delimiter=';')
    writer.writerow(['Semana', 'Base', 'UF', 'S/C', 'Avaliações', 'Positivas', 'Negativas', 'CSAT (%)'])
    for key, values in sorted(bykey.items()):
        a1 = agrupar(values)
        writer.writerow([*key, a1['total'], a1['sim'], a1['nao'], f'{a1["taxa"]*100:.2f}'.replace('.', ',')])
    text = '\ufeff' + csvfile.getvalue()
    return StreamingResponse(iter([text]),media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename="J-T-CSAT-Orlean.csv"'})
