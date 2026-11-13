"""Armazenamento J&T Qualidade: SQLite local, JT API ou Supabase REST privado.

SUPABASE_SECRET_KEY é lida apenas no backend; nunca enviada ao JavaScript.
Em produção JT_STORAGE_MODE=supabase; importação histórica via publicar_supabase.py.
"""
from __future__ import annotations
import os
import re
import sqlite3
import time
from functools import lru_cache
from threading import local
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
DEFAULT_SQLITE = ROOT / 'dados' / 'jt_1bd.sqlite3'
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
MODE = os.environ.get('JT_STORAGE_MODE', '').strip().lower()
IS_API = MODE == 'api'
IS_SUPABASE = MODE == 'supabase'
IS_POSTGRES = not (IS_API or IS_SUPABASE) and DATABASE_URL.startswith(('postgresql://', 'postgres://'))


def connection():
    if IS_API or IS_SUPABASE:
        raise RuntimeError('Para importar dados em modo remoto, utilize o publicador correspondente no PC com o SQLite. Não use os importadores locais sobre o serviço remoto.')
    if IS_POSTGRES:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Para PostgreSQL instale: pip install 'psycopg[binary]'") from exc
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    if DATABASE_URL.startswith('sqlite:///'):
        path = Path(DATABASE_URL[10:]).resolve()
    elif DATABASE_URL:
        raise ValueError('DATABASE_URL deve começar com postgresql:// ou sqlite:///')
    else:
        path = DEFAULT_SQLITE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=60000')
    return conn


def sql(sqlite_stmt: str) -> str:
    return sqlite_stmt.replace('?', '%s') if IS_POSTGRES else sqlite_stmt


def setup():
    if IS_API or IS_SUPABASE:
        return
    with connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS jt_1bd_gestao (
          base_chave TEXT PRIMARY KEY,
          codigo TEXT, nome TEXT NOT NULL, uf TEXT, regional TEXT,
          rm TEXT, coordenador TEXT, supervisor TEXT, sc TEXT,
          tipo_sc TEXT, situacao TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS jt_1bd_registros (
          id TEXT PRIMARY KEY, data_avaliacao TEXT NOT NULL,
          remessa TEXT NOT NULL, ticket TEXT, entregue INTEGER NOT NULL,
          base_original TEXT NOT NULL, base_chave TEXT NOT NULL,
          problema TEXT, horario_assinatura TEXT, data_registro TEXT,
          arquivo_origem TEXT)''')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_1bd_data ON jt_1bd_registros(data_avaliacao)')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_1bd_base ON jt_1bd_registros(base_chave)')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_1bd_rm ON jt_1bd_gestao(rm)')
        conn.commit()


_API_THREAD = local()

# Colunas fixas das consultas do dashboard. Necessárias quando a JT API
# devolve arrays posicionais em vez de objetos JSON com nomes de coluna.
_API_COLS_1BD = (
    'data', 'remessa', 'ticket', 'entregue', 'base_original', 'base',
    'codigo', 'uf', 'rm', 'coordenador', 'supervisor', 'sc', 'tipo_sc',
    'situacao', 'problema',
)
_API_COLS_5CD = (
    'data', 'remessa', 'dias_base', 'atraso', 'faixa', 'operacao',
    'package_id', 'motivo', 'base_original', 'codigo', 'base', 'uf',
    'rm', 'coordenador', 'supervisor', 'sc', 'tipo_sc',
)


# Projeção fixa da consulta CSAT; suporta JT API em listas posicionais.
_API_COLS_CSAT = (
    'id', 'ano', 'semana_numero', 'semana_id', 'semana_descricao',
    'data_avaliacao', 'base_chave', 'base', 'codigo', 'uf', 'rm',
    'coordenador', 'supervisor', 'sc', 'tipo_sc', 'avaliacao',
    'ticket', 'tracking', 'categoria', 'arquivo_origem',
)


def _api_columns(statement: str):
    normalized = re.sub(r'\s+', ' ', statement).lower()
    if 'from jt_csat_registros' in normalized:
        return _API_COLS_CSAT
    if 'from jt_1bd_registros r join jt_1bd_gestao g' in normalized:
        return _API_COLS_1BD
    if 'from jt_5cd_registros r join jt_1bd_gestao g' in normalized:
        return _API_COLS_5CD
    if normalized.lstrip().startswith('select count(*) as n from '):
        return ('n',)
    return None


def _response_rows(data, columns=None):
    if isinstance(data, dict):
        for key in ('rows', 'data', 'result', 'resultado', 'registros'):
            if isinstance(data.get(key), list):
                return _response_rows(data[key], columns)
        raise RuntimeError('Formato inesperado da resposta da JT API.')
    if not isinstance(data, list):
        raise RuntimeError('JT API /query deve retornar uma lista de linhas.')
    result = []
    for row in data:
        if isinstance(row, dict):
            result.append(row)
        elif isinstance(row, (list, tuple)) and columns is not None:
            if len(row) != len(columns):
                raise RuntimeError('JT API retornou linha posicional com '
                                   f'{len(row)} colunas; esperado {len(columns)}.')
            result.append(dict(zip(columns, row)))
        else:
            raise RuntimeError('JT API retornou linha sem nomes de coluna para '
                               'consulta não reconhecida. Não é seguro inferir campos.')
    return result


def _api_post_query(query: str, params: tuple, columns=None):
    import requests
    url = os.environ.get('JT_API_URL', '').strip().rstrip('/')
    key = os.environ.get('JT_API_KEY', '').strip()
    if not url.startswith('https://') or not key:
        raise RuntimeError('Render precisa de JT_API_URL HTTPS e JT_API_KEY nas Environment Variables.')
    # Reutiliza conexoes HTTPS durante a paginacao (uma Session por thread).
    session = getattr(_API_THREAD, 'session', None)
    if session is None:
        session = requests.Session()
        _API_THREAD.session = session
    resp = session.post(url + '/query', headers={'X-API-Key': key},
                        json={'sql': query, 'params': list(params)}, timeout=120)
    if not resp.ok:
        raise RuntimeError(f'JT API /query HTTP {resp.status_code} (verifique API e SQL).')
    return _response_rows(resp.json(), columns)


@lru_cache(maxsize=8)
def _cached_api_rows(statement: str, parameters: tuple, columns: tuple | None, bucket: int):
    """Busca o conjunto completo em lotes maiores, sem truncar se a API limitar o lote.

    O cache e pequeno para nao reter muitas copias de bases historicas
    na memoria do Render. Bucket temporal compartilha o resultado entre
    /filtros, /dashboard e chamadas simultaneas do mesmo intervalo.
    """
    cols = columns or _api_columns(statement)
    if statement.lstrip().lower().startswith('select count(*) as n from '):
        return tuple(_api_post_query(statement, parameters, cols))

    page_size = max(500, min(5000, int(os.environ.get('JT_API_PAGE_SIZE', '2000'))))
    output, offset = [], 0
    while True:
        page_sql = f'{statement.strip().rstrip(";")} LIMIT %s OFFSET %s'
        try:
            batch = _api_post_query(page_sql, parameters + (page_size, offset), cols)
        except RuntimeError as exc:
            # Compatibilidade com servidores que recusam LIMIT > 500.
            if offset == 0 and page_size > 500 and 'HTTP ' in str(exc):
                page_size = 500
                continue
            raise
        if not batch:
            break
        output.extend(batch)
        offset += len(batch)
        if offset > 200000:
            raise RuntimeError('Limite de paginação JT API excedido.')
        # Nao interromper em lote parcial: algumas versoes da JT API
        # aplicam um limite proprio, inferior ao LIMIT solicitado.
    return tuple(output)


# Supabase REST: usa apenas a API Key no header apikey para sb_secret_*.
# Chaves legacy JWT podem incluir Authorization: Bearer; nunca o são no navegador.
SB_URL = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
SB_KEY = (os.environ.get('SUPABASE_SECRET_KEY', '').strip() or
          os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip())
SB_TABLES = {'jt_1bd_gestao', 'jt_1bd_registros', 'jt_5cd_registros'}


def _sb_credentials():
    parsed = urlparse(SB_URL)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path not in ('', '/'):
        raise RuntimeError('Configure SUPABASE_URL com a URL HTTPS raiz do projeto (*.supabase.co).')
    if not SB_KEY or SB_KEY.startswith('sb_publishable_'):
        raise RuntimeError('Configure SUPABASE_SECRET_KEY no backend, não a chave publishable/anon.')
    return SB_URL, SB_KEY


def _sb_get(table: str, select='*', offset=0, limit=1000):
    import requests
    if table not in SB_TABLES:
        raise ValueError('Tabela fora da lista permitida')
    url, key = _sb_credentials()
    headers = {'apikey': key, 'Accept': 'application/json'}
    if key.count('.') == 2 and key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {key}'
    result = requests.get(f'{url}/rest/v1/{table}', headers=headers,
                          params={'select': select, 'order': 'id.asc' if table != 'jt_1bd_gestao' else 'base_chave.asc',
                                  'limit': limit, 'offset': offset}, timeout=45)
    if not result.ok:
        raise RuntimeError(f'Supabase GET {table}: HTTP {result.status_code}. Verifique URL, chave, grants, RLS e Data API.')
    data = result.json()
    if not isinstance(data, list):
        raise RuntimeError(f'Supabase devolveu formato inesperado em {table}')
    return data


@lru_cache(maxsize=30)
def _sb_count(table: str, bucket: int):
    """COUNT rápido via PostgREST; não baixa dezenas de milhares de registros."""
    import requests
    if table not in SB_TABLES:
        raise ValueError('Tabela fora da lista permitida')
    url, key = _sb_credentials()
    headers = {'apikey': key, 'Accept': 'application/json', 'Prefer': 'count=exact'}
    if key.count('.') == 2 and key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {key}'
    response = requests.get(f'{url}/rest/v1/{table}', headers=headers,
                            params={'select': 'base_chave' if table == 'jt_1bd_gestao' else 'id', 'limit': 1}, timeout=30)
    if not response.ok:
        raise RuntimeError(f'Supabase COUNT {table}: HTTP {response.status_code}; confira URL, key, RLS e Data API.')
    header = response.headers.get('Content-Range', '')
    if '/' not in header or header.rsplit('/', 1)[-1] == '*':
        raise RuntimeError(f'Supabase COUNT {table}: contagem exata indisponível.')
    return int(header.rsplit('/', 1)[-1])


@lru_cache(maxsize=20)
def _sb_table(table: str, bucket: int):
    result = []
    page = 1000
    offset = 0
    while True:
        part = _sb_get(table, offset=offset, limit=page)
        result.extend(part)
        if len(part) < page:
            break
        offset += len(part)
        if offset > 250000:
            raise RuntimeError('Paginação Supabase excedeu limite de segurança.')
    return tuple(result)


def _sb_query(query: str, params=()):
    # As consultas utilizadas pelos dois indicadores são intencionalmente fixas.
    # Não enviamos SQL arbitrário nem criamos funções SECURITY DEFINER públicas.
    statement = re.sub(r'\s+', ' ', query.strip()).lower()
    ttl = max(30, int(os.environ.get('SUPABASE_CACHE_SECONDS', '120')))
    bucket = int(time.time() // ttl)
    if statement.startswith('select count(*) as n from '):
        table = statement.split(' from ', 1)[1].split()[0].split('.')[-1]
        if table not in SB_TABLES:
            raise RuntimeError('Tabela fora da lista permitida no Supabase')
        return [{'n': _sb_count(table, bucket)}]

    gestao = {row['base_chave']: row for row in _sb_table('jt_1bd_gestao', bucket)}
    rm = str(params[0]) if params else 'ORLEAN DA SILVA DO NASCIMENTO'
    if 'from jt_1bd_registros r join jt_1bd_gestao g' in statement:
        output = []
        for r in _sb_table('jt_1bd_registros', bucket):
            g = gestao.get(r['base_chave'])
            if not g or g.get('rm') != rm:
                continue
            output.append({
                'data': r['data_avaliacao'], 'remessa': r['remessa'], 'ticket': r['ticket'],
                'entregue': r['entregue'], 'base_original': r['base_original'],
                'base': g['nome'], 'codigo': g['codigo'], 'uf': g['uf'], 'rm': g['rm'],
                'coordenador': g['coordenador'], 'supervisor': g['supervisor'],
                'sc': g['sc'], 'tipo_sc': g['tipo_sc'], 'situacao': g['situacao'],
                'problema': r['problema'],
            })
        return sorted(output, key=lambda x: (x['data'], x['base'] or ''))
    if 'from jt_5cd_registros r join jt_1bd_gestao g' in statement:
        output = []
        for r in _sb_table('jt_5cd_registros', bucket):
            g = gestao.get(r['base_chave'])
            if not g or g.get('rm') != rm:
                continue
            output.append({
                'data': r['data_relatorio'], 'remessa': r['remessa'],
                'dias_base': r['dias_base'], 'atraso': r['atraso'], 'faixa': r['faixa'],
                'operacao': r['operacao'], 'package_id': r['package_id'],
                'motivo': r['motivo'], 'base_original': r['base_original'],
                'codigo': g['codigo'], 'base': g['nome'], 'uf': g['uf'], 'rm': g['rm'],
                'coordenador': g['coordenador'], 'supervisor': g['supervisor'],
                'sc': g['sc'], 'tipo_sc': g['tipo_sc'],
            })
        return sorted(output, key=lambda x: (x['data'], x['codigo'] or '', x['remessa']))
    raise RuntimeError('Consulta não suportada pelo adaptador Supabase. Não é executado SQL arbitrário.')


def rows(query: str, params=(), *, columns=None):
    if IS_SUPABASE:
        return _sb_query(query, params)
    if IS_API:
        if not query.lstrip().upper().startswith(('SELECT ', 'WITH ')):
            raise RuntimeError('JT API aceita apenas SELECT neste painel.')
        statement = query.replace('?', '%s')
        ttl = max(30, int(os.environ.get('JT_API_CACHE_SECONDS', '300')))
        projected = tuple(columns) if columns else None
        return [dict(r) for r in _cached_api_rows(statement, tuple(params), projected, int(time.time() // ttl))]
    with connection() as conn:
        cur = conn.execute(sql(query), params)
        return [dict(r) for r in cur.fetchall()]


def scalar(query: str, params=()):
    data = rows(query, params)
    return next(iter(data[0].values())) if data else None
