"""Migra os dados historicos 1BD + 5CD do SQLite incluido no pacote para PostgreSQL.

Pre-condicao: DATABASE_URL em .env, apontando ao PostgreSQL autorizado.
Comportamento: cria tabelas faltantes, faz UPSERT (nao duplica / nao apaga dados),
compara a quantidade de registros/orlean na fonte e destino.
"""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

from database import connection, setup, IS_POSTGRES

ROOT = Path(__file__).resolve().parent
SCHEMA = {
  'jt_1bd_gestao': ('base_chave','codigo','nome','uf','regional','rm','coordenador','supervisor','sc','tipo_sc','situacao'),
  'jt_5cd_registros': ('id','data_relatorio','remessa','base_chave','base_original','dias_base','atraso','faixa','operacao','package_id','motivo','arquivo_origem','aba_origem'),
  'jt_1bd_registros': ('id','data_avaliacao','remessa','ticket','entregue','base_original','base_chave','problema','horario_assinatura','data_registro','arquivo_origem'),
}

def chunks(cursor, size: int):
    while True:
        batch = cursor.fetchmany(size)
        if not batch:
            break
        yield [tuple(row) for row in batch]

def migrate(source: Path, batch_size: int):
    if not IS_POSTGRES:
        raise SystemExit('ERRO: DATABASE_URL nao esta definida como postgresql:// em .env. '
                         'JT_API_URL e JT_API_KEY nao substituem DATABASE_URL. '
                         'Configure o banco antes de migrar; nada foi alterado.')
    if not source.is_file():
        raise SystemExit(f'ERRO: SQLite historico nao encontrado: {source}')
    from importar_5cd import setup_5cd
    setup_5cd()  # cria tabelas 1BD + 5CD sem alterar outros indicadores
    with sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True) as db_sqlite:
        for table, cols in SCHEMA.items():
            n_source = db_sqlite.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            col_list = ','.join(cols)
            placeholders = ','.join(['%s'] * len(cols))
            updates = ','.join(f'{c}=excluded.{c}' for c in cols[1:])
            stmt = (f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) '
                    f'ON CONFLICT ({cols[0]}) DO UPDATE SET {updates}')
            print(f'Migrando {table}: {n_source:,} registros da origem...')
            source_cursor = db_sqlite.execute(f'SELECT {col_list} FROM {table}')
            imported = 0
            with connection() as target:
                for batch in chunks(source_cursor, batch_size):
                    with target.cursor() as cursor:
                        cursor.executemany(stmt, batch)
                    target.commit()
                    imported += len(batch)
                    print(f'  {imported:,}/{n_source:,}', end='\r', flush=True)
                final = target.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']
            print(f'  Origem: {n_source:,} | Processados: {imported:,} | Banco: {final:,}')
            if final < n_source:
                print('AVISO: banco tem menos linhas do que a origem; verificar IDs/conflitos.')
    with connection() as target:
        row = target.execute("""SELECT COUNT(*) AS total, COALESCE(SUM(r.entregue),0) AS sim
              FROM jt_1bd_registros r JOIN jt_1bd_gestao g ON g.base_chave = r.base_chave
              WHERE g.rm = %s""", ('ORLEAN DA SILVA DO NASCIMENTO',)).fetchone()
        total, sim = row['total'], row['sim']
        print(f'ORLEAN NO POSTGRESQL: {total:,} avaliacoes | {sim:,} Sim | {100*sim/total if total else 0:.2f}%')
        if total == 0:
            print('ATENCAO: sem dados associados a Orlean. Verifique Gestao/aliases antes de publicar.')
    print('Concluido. Atualize o dashboard para ler DATABASE_URL no mesmo .env.')

def main():
    parser = argparse.ArgumentParser(description='Migracao SQLite -> PostgreSQL | 1BD')
    parser.add_argument('--sqlite', type=Path, default=ROOT/'dados'/'jt_1bd.sqlite3')
    parser.add_argument('--lote', type=int, default=1000)
    args = parser.parse_args()
    if args.lote < 1:
        parser.error('--lote precisa ser positivo')
    migrate(args.sqlite.resolve(), args.lote)

if __name__ == '__main__':
    main()
