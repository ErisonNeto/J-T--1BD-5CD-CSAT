"""Publica as três tabelas de Qualidade na VM PostgreSQL através da JT API HTTPS.

Execute no PC J&T, junto com dados/jt_1bd.sqlite3 e o .env existente.
Padrão: somente validação. Use --aplicar para efetuar UPSERT; não apaga históricos.
Não escreve em sem_mov_retidos_detalhe nem jt_gestao_bases (gestão compartilhada).
"""
from __future__ import annotations
import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
API = os.environ.get('JT_API_URL','').rstrip('/')
KEY = os.environ.get('JT_API_KEY','').strip()
COLUMNS = {
    'jt_1bd_gestao': ('base_chave','codigo','nome','uf','regional','rm','coordenador','supervisor','sc','tipo_sc','situacao'),
    'jt_1bd_registros': ('id','data_avaliacao','remessa','ticket','entregue','base_original','base_chave','problema','horario_assinatura','data_registro','arquivo_origem'),
    'jt_5cd_registros': ('id','data_relatorio','remessa','base_chave','base_original','dias_base','atraso','faixa','operacao','package_id','motivo','arquivo_origem','aba_origem'),
}


def post(session, path, payload, attempts=3):
    for n in range(attempts):
        try:
            r = session.post(API+path, headers={'X-API-Key':KEY}, json=payload, timeout=120)
        except requests.RequestException as e:
            if n+1==attempts:
                raise RuntimeError(f'Falha de conexão com JT API em {path}: {type(e).__name__}') from e
            time.sleep(2*(n+1))
            continue
        if r.ok:
            return r.json()
        if r.status_code in (408,429,500,502,503,504) and n+1<attempts:
            time.sleep(2*(n+1))
            continue
        raise RuntimeError(f'JT API {path}: HTTP {r.status_code}. Não imprimimos o corpo da resposta por segurança.')
    raise RuntimeError(f'JT API {path}: tentativas esgotadas')


def query(s, stmt, params=None):
    obj=post(s,'/query',{'sql':stmt,'params':params or []})
    if isinstance(obj,list):return obj
    if isinstance(obj,dict):
        for fld in ('rows','data','result','resultado','registros'):
            if isinstance(obj.get(fld),list):return obj[fld]
    raise RuntimeError(f'JT API /query retornou formato não reconhecido: {type(obj).__name__}')


def qty(s, stmt, params=None):
    rows=query(s,stmt,params)
    if not rows:return 0
    row=rows[0]
    return int(next(iter(row.values())) if isinstance(row,dict) else row[0])


def present(s,table):
    return qty(s,"SELECT COUNT(*) AS qtd FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",[table])>0


def source_counts(db):
    out={}
    for table,columns in COLUMNS.items():
        c=db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
        out[table]=c
        missing={k for k in columns}-{r[1] for r in db.execute('PRAGMA table_info('+table+')')}
        if missing:raise RuntimeError(f'Colunas faltantes no SQLite {table}: {sorted(missing)}')
    return out


def main():
    p=argparse.ArgumentParser(description='J&T Qualidade: SQLite -> PostgreSQL via JT API')
    p.add_argument('--sqlite',type=Path,default=ROOT/'dados'/'jt_1bd.sqlite3')
    p.add_argument('--lote',type=int,default=300)
    p.add_argument('--aplicar',action='store_true',help='Confirma publicação das três tabelas por UPSERT')
    p.add_argument('--somente',choices=list(COLUMNS),help='Publica somente uma tabela')
    args=p.parse_args()
    if not 10<=args.lote<=1000:p.error('--lote deve estar entre 10 e 1000')
    if not args.sqlite.is_file():p.error(f'SQLite inexistente: {args.sqlite}')
    if not API.startswith('https://') or not KEY:
        p.error('Configure JT_API_URL HTTPS e JT_API_KEY no .env local antes da publicação')
    with sqlite3.connect(f'file:{args.sqlite.resolve().as_posix()}?mode=ro',uri=True) as db, requests.Session() as sess:
        db.row_factory=sqlite3.Row
        counts=source_counts(db)
        print('ORIGEM SQLite validada:')
        for t,n in counts.items():print(' ',t,':',f'{n:,}')
        expected={'jt_1bd_gestao':510,'jt_1bd_registros':12354,'jt_5cd_registros':29964}
        for t,minval in expected.items():
            if counts[t]<minval:
                print(f'ATENÇÃO: {t} tem {counts[t]:,} registros; histórico de referência é {minval:,}.')
        check=qty(sess,'SELECT 1 AS ok')
        if check!=1:raise RuntimeError('JT API respondeu sem confirmar SELECT 1')
        print('JT API autenticada, conexão PostgreSQL OK.')
        tables=[args.somente] if args.somente else list(COLUMNS)
        for table in tables:
            exists=present(sess,table)
            prev=qty(sess,f'SELECT COUNT(*) AS qtd FROM public.{table}') if exists else 0
            print(f'{table}: destino {"existe" if exists else "não existe"} | {prev:,} no destino | {counts[table]:,} na origem')
            if not args.aplicar:
                continue
            cs=COLUMNS[table]
            cols=','.join(cs)
            src=db.execute('SELECT '+cols+' FROM '+table+' ORDER BY '+cs[0])
            done=0
            while True:
                batch=src.fetchmany(args.lote)
                if not batch:break
                payload={
                    'tabela':table,
                    'chave':[cs[0]],
                    'registros':[{k:row[k] for k in cs} for row in batch],
                    'criar_tabela':not exists,
                    'adicionar_colunas':False,
                }
                post(sess,'/import',payload)
                exists=True
                done+=len(batch)
                print(f'  {table}: {done:,}/{counts[table]:,}',flush=True)
            final=qty(sess,f'SELECT COUNT(*) AS qtd FROM public.{table}')
            print(f'  CONFERÊNCIA {table}: banco={final:,} | carga_processada={done:,}')
            if final<counts[table]:
                raise RuntimeError(f'{table}: total do destino menor que da origem; examine os IDs antes de prosseguir')
            sample=db.execute('SELECT '+cs[0]+' FROM '+table+' LIMIT 1').fetchone()
            if sample:
                found=qty(sess,f'SELECT COUNT(*) AS qtd FROM public.{table} WHERE {cs[0]}=%s',[sample[0]])
                if found<1:raise RuntimeError(f'{table}: amostra não encontrada no PostgreSQL')
        if args.aplicar:
            n=qty(sess,'SELECT COUNT(*) AS qtd FROM public.jt_5cd_registros WHERE data_relatorio=%s',['2026-11-04'])
            print(f'5CD 04/11/2026 no destino: {n:,} registros')
            print('PUBLICAÇÃO FINALIZADA. Nenhuma tabela de outro indicador foi apagada.')
        else:
            print('VALIDAÇÃO CONCLUÍDA. Nada foi enviado. Execute novamente com --aplicar para publicar.')


if __name__=='__main__':
    try:main()
    except (RuntimeError,sqlite3.Error) as exc:
        print('ERRO:',exc,file=sys.stderr)
        sys.exit(1)
