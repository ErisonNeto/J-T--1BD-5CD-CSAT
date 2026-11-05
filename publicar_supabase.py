"""Publicação idempotente do histórico SQLite para NOVO projeto Supabase.

Padrão: auditoria somente leitura; --aplicar e --confirmar-projeto=REF exigidos
para inserir. Não apaga nenhuma tabela e não mostra chaves em logs.
"""
from __future__ import annotations
import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT/'.env', override=False)
SUPABASE_URL = os.environ.get('SUPABASE_URL','').strip().rstrip('/')
SUPABASE_KEY = (os.environ.get('SUPABASE_SECRET_KEY','').strip() or
                os.environ.get('SUPABASE_SERVICE_ROLE_KEY','').strip())
COLUMNS = {
    'jt_1bd_gestao': ('base_chave','codigo','nome','uf','regional','rm','coordenador','supervisor','sc','tipo_sc','situacao'),
    'jt_1bd_registros': ('id','data_avaliacao','remessa','ticket','entregue','base_original','base_chave','problema','horario_assinatura','data_registro','arquivo_origem'),
    'jt_5cd_registros': ('id','data_relatorio','remessa','base_chave','base_original','dias_base','atraso','faixa','operacao','package_id','motivo','arquivo_origem','aba_origem'),
}


def ref_projeto():
    u = urlparse(SUPABASE_URL)
    if u.scheme != 'https' or not u.hostname or not u.hostname.endswith('.supabase.co') or u.path not in ('', '/'):
        raise ValueError('SUPABASE_URL precisa ser a URL raiz HTTPS do novo projeto (*.supabase.co).')
    ref = u.hostname.removesuffix('.supabase.co')
    if not re.fullmatch(r'[a-z0-9-]+', ref):
        raise ValueError('Ref do projeto Supabase inválida.')
    if not SUPABASE_KEY or SUPABASE_KEY.startswith('sb_publishable_'):
        raise ValueError('Configure SUPABASE_SECRET_KEY (sb_secret_...) no .env do PC, nunca publishable/anon.')
    return ref


def headers():
    result={'apikey': SUPABASE_KEY, 'Content-Type':'application/json', 'Accept':'application/json'}
    if SUPABASE_KEY.startswith('eyJ') and SUPABASE_KEY.count('.')==2:
        result['Authorization']=f'Bearer {SUPABASE_KEY}'
    return result


def request(session, method, table, *, params=None, records=None, prefer=None):
    if table not in COLUMNS:
        raise ValueError('Tabela não autorizada')
    h=headers()
    if prefer: h['Prefer']=prefer
    for attempt in range(4):
        try:
            r=session.request(method, f'{SUPABASE_URL}/rest/v1/{table}',
                              headers=h, params=params, json=records, timeout=90)
        except requests.RequestException as exc:
            if attempt == 3: raise RuntimeError(f'Supabase: falha de conexão {type(exc).__name__}.') from exc
            time.sleep(2 * (attempt + 1))
            continue
        if r.ok: return r
        if r.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(2 * (attempt + 1))
            continue
        raise RuntimeError(f'Supabase {method} {table}: HTTP {r.status_code}. Confira a URL, secret key, concessões de acesso à Data API e schema_supabase.sql.')
    raise RuntimeError('Supabase: tentativas esgotadas.')


def remote_count(session, table):
    key = COLUMNS[table][0]
    r = request(session, 'GET', table, params={'select':key,'limit':1}, prefer='count=exact')
    content_range = r.headers.get('Content-Range','')
    if '/' not in content_range:
        raise RuntimeError(f'Supabase não retornou Content-Range para {table}; confira Data API.')
    suffix=content_range.rsplit('/',1)[1]
    if suffix == '*': raise RuntimeError('Contagem exata indisponível no Supabase.')
    return int(suffix)


def local_counts(db):
    out={}
    for table, columns in COLUMNS.items():
        existing = {row[1] for row in db.execute('PRAGMA table_info('+table+')')}
        missing = set(columns)-existing
        if missing: raise RuntimeError(f'{table}: esquema SQLite incompleto, faltam {sorted(missing)}')
        out[table]=int(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0])
    return out


def main():
    parser=argparse.ArgumentParser(description='Publica J&T Qualidade SQLite no NOVO Supabase via API REST')
    parser.add_argument('--sqlite',type=Path,default=ROOT/'dados'/'jt_1bd.sqlite3')
    parser.add_argument('--lote',type=int,default=200)
    parser.add_argument('--aplicar',action='store_true',help='UPSERT nas três tabelas; exige --confirmar-projeto')
    parser.add_argument('--confirmar-projeto',help='Ref exata do destino, mostrada na auditoria')
    parser.add_argument('--somente',choices=COLUMNS.keys(),help='Somente uma tabela')
    args=parser.parse_args()
    if not 10 <= args.lote <= 500:parser.error('--lote entre 10 e 500')
    if not args.sqlite.is_file():parser.error(f'Banco SQLite não existe: {args.sqlite}')
    try:ref=ref_projeto()
    except ValueError as exc:parser.error(str(exc))
    if args.aplicar and args.confirmar_projeto != ref:
        parser.error(f'Para enviar dados ao projeto {ref}, acrescente --confirmar-projeto {ref}')
    with sqlite3.connect(f'file:{args.sqlite.resolve().as_posix()}?mode=ro', uri=True) as conn, requests.Session() as session:
        conn.row_factory=sqlite3.Row
        src_counts=local_counts(conn)
        print('PROJETO DE DESTINO:',ref, flush=True)
        print('ORIGEM LOCAL:',args.sqlite.name, flush=True)
        for table,count in src_counts.items():print(f'  {table}: {count:,} registros', flush=True)
        tables=[args.somente] if args.somente else list(COLUMNS)
        for table in tables:
            before=remote_count(session,table)
            print(f'  SUPABASE {table}: {before:,} registros atuais', flush=True)
            if not args.aplicar:continue
            cols=COLUMNS[table]
            src=conn.execute('SELECT '+','.join(cols)+' FROM '+table+' ORDER BY '+cols[0])
            done=0
            while True:
                batch=src.fetchmany(args.lote)
                if not batch:break
                payload=[{k:row[k] for k in cols} for row in batch]
                request(session,'POST',table,
                        params={'on_conflict':cols[0]}, records=payload,
                        prefer='resolution=merge-duplicates,return=minimal')
                done+=len(batch)
                if done%1000 < len(batch) or done==src_counts[table]:
                    print(f'    enviados {done:,}/{src_counts[table]:,}',flush=True)
            after=remote_count(session,table)
            if after<src_counts[table]:
                raise RuntimeError(f'{table}: conferência falhou (banco={after:,}, origem={src_counts[table]:,}).')
            first=conn.execute('SELECT '+cols[0]+' FROM '+table+' ORDER BY '+cols[0]+' LIMIT 1').fetchone()
            if first:
                resp=request(session,'GET',table,
                    params={'select':cols[0], cols[0]:'eq.'+str(first[0]),'limit':1})
                if not resp.json():raise RuntimeError(f'{table}: amostra do SQLite não encontrada no Supabase')
            print(f'    CONFERÊNCIA OK: {after:,} registros',flush=True)
    print('PUBLICAÇÃO FINALIZADA.' if args.aplicar else 'AUDITORIA OK. Nenhum registro foi enviado.',flush=True)
    if not args.aplicar:print('Para aplicar: python publicar_supabase.py --aplicar --confirmar-projeto '+ref)

if __name__=='__main__':
    try:main()
    except (RuntimeError,sqlite3.Error,ValueError) as exc:
        print('ERRO:',exc,file=sys.stderr)
        sys.exit(1)
