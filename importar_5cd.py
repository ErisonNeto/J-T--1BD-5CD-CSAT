"""Carga 5CD TikTok: coluna I = data DO RELATÓRIO, O = remessa, P = base.
As bases e atribuições de R/M, coordenadores e supervisores vêm da Gestão atualizada.
Cada remessa entra no máximo uma vez por (data de relatório, base, remessa).
Abas importadas: Dados históricos 历史数据 e BD (BD tem prioridade se sobrepostas).
Uso: python importar_5cd.py --gestao caminho.xlsx --arquivos caminho5cd.xlsx
Sem DATABASE_URL: SQLite incluído. Com DATABASE_URL: banco PostgreSQL.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
from pathlib import Path
from database import connection, setup, sql
from importar_excel import carregar_gestao, carregar_aliases, ORLEAN
from xlsx_reader import ler_aba, data_excel, normalizar

ROOT=Path(__file__).resolve().parent
ABAS=('Dados históricos 历史数据','BD')


def setup_5cd():
    setup()
    with connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS jt_5cd_registros (
            id TEXT PRIMARY KEY,
            data_relatorio TEXT NOT NULL,
            remessa TEXT NOT NULL,
            base_chave TEXT NOT NULL,
            base_original TEXT NOT NULL,
            dias_base REAL,
            atraso TEXT,
            faixa TEXT,
            operacao TEXT,
            package_id TEXT,
            motivo TEXT,
            arquivo_origem TEXT,
            aba_origem TEXT
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_5cd_data ON jt_5cd_registros(data_relatorio)')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_5cd_base ON jt_5cd_registros(base_chave)')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_5cd_date_base ON jt_5cd_registros(data_relatorio,base_chave)')
        conn.commit()


def load_file(path: Path, only_orlean=True):
    aliases=carregar_aliases()
    with connection() as conn:
        gestores={r['base_chave']:r['rm'] for r in conn.execute('SELECT base_chave,rm FROM jt_1bd_gestao').fetchall()}
    totals=Counter()
    faltantes=Counter()
    exemplo=[]
    statement=sql('''INSERT INTO jt_5cd_registros
        (id,data_relatorio,remessa,base_chave,base_original,dias_base,atraso,faixa,operacao,package_id,motivo,arquivo_origem,aba_origem)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          base_original=excluded.base_original,
          dias_base=excluded.dias_base,
          atraso=excluded.atraso,
          faixa=excluded.faixa,
          operacao=excluded.operacao,
          package_id=excluded.package_id,
          motivo=excluded.motivo,
          arquivo_origem=excluded.arquivo_origem,
          aba_origem=excluded.aba_origem''')
    # ID estável -> idempotente e não multiplica o pacote por repetições no mesmo relatório.
    # Importa apenas R/M Orlean para economizar armazenamento; Gestão define ownership.
    with connection() as conn:
        for tab in ABAS:
            validos=0
            try:
                rows=ler_aba(path,tab)
                header=next(rows)
            except (ValueError,StopIteration):
                totals[f'aba_ausente:{tab}']+=1
                continue
            if normalizar(header.get('O'))!='TRACKINGNOS' or normalizar(header.get('P'))!='BASE':
                raise ValueError(f'{path.name} | aba {tab}: colunas O/P inesperadas: {header.get("O")!r}/{header.get("P")!r}')
            if 'DTENVIO' not in normalizar(header.get('I')):
                raise ValueError(f'{path.name} | aba {tab}: coluna I não é data de envio do relatório.')
            for r in rows:
                totals['linhas_lidas']+=1
                base=r.get('P','').strip()
                remessa=r.get('O','').strip()
                if not remessa or not base:
                    totals['sem_remessa_ou_base']+=1
                    continue
                base_key=normalizar(base)
                base_key=aliases.get(base_key,base_key)
                rm=gestores.get(base_key)
                if rm is None:
                    faltantes[base]+=1
                    totals['sem_gestao']+=1
                    continue
                if normalizar(rm)!=ORLEAN and only_orlean:
                    totals['outra_rm']+=1
                    continue
                try:
                    data=data_excel(r.get('I'))
                except ValueError:
                    totals['data_invalida']+=1
                    continue
                try:
                    aging=float(r['C']) if r.get('C','').strip() not in ('','#N/A','-') else None
                except (TypeError,ValueError):
                    aging=None
                uid=hashlib.sha256(f'5cd|{data}|{remessa}|{base_key}'.encode('utf-8')).hexdigest()
                vals=(uid,data,remessa,base_key,base,aging,
                    r.get('M','').strip(),r.get('D','').strip(),r.get('B','').strip(),
                    r.get('N','').strip(),r.get('T','').strip(),path.name,tab)
                conn.execute(statement,vals)
                totals['linhas_orlean']+=1
                validos+=1
                if validos%2500==0:conn.commit()
            conn.commit()
            print(f'  {tab}: {validos:,} linhas pertencentes ao R/M Orlean',flush=True)
    return totals,faltantes


def main():
    parser=argparse.ArgumentParser(description='Importar TikTok 5CD para painel único 1BD/5CD/CSAT')
    parser.add_argument('--pasta',type=Path,default=ROOT/'dados')
    parser.add_argument('--gestao',type=Path)
    parser.add_argument('--arquivos',nargs='*',type=Path)
    args=parser.parse_args()
    pasta=args.pasta.resolve()
    gestao=args.gestao.resolve() if args.gestao else max((p for p in pasta.rglob('*.xlsx') if 'gest' in p.name.lower() and 'colaborador' in p.name.lower()),key=lambda p:p.stat().st_mtime,default=None)
    if gestao is None or not gestao.exists():parser.error('Arquivo Gestão não encontrado. Informe --gestao.')
    arquivos=[p.resolve() for p in args.arquivos] if args.arquivos else sorted(p for p in pasta.rglob('*.xlsx') if '5cd' in p.name.lower() and not p.name.startswith('~$'))
    if not arquivos:parser.error('Arquivo 5CD não encontrado. Informe --arquivos.')
    setup_5cd()
    validos,conflitos=carregar_gestao(gestao)
    print('GESTÃO:',len(validos),'bases únicas | conflitos:',len(conflitos))
    for k,v in conflitos.items(): print('  CONFLITO PENDENTE:',k,'— excluído até saneamento')
    for arquivo in arquivos:
        if not arquivo.exists():parser.error(f'Arquivo não encontrado: {arquivo}')
        print('5CD:',arquivo.name,flush=True)
        contagem,sem_match=load_file(arquivo)
        print('  Totais:',dict(contagem))
        print('  Sem match (top 12):',sem_match.most_common(12))
    with connection() as conn:
        r=conn.execute(sql('''SELECT COUNT(*) AS n, COUNT(DISTINCT data_relatorio) AS dias,
           MIN(data_relatorio) AS inicio, MAX(data_relatorio) AS fim
           FROM jt_5cd_registros''')).fetchone()
        print('BANCO 5CD:',f'{r["n"]:,}','registros distintos por data/remessa/base,',r['dias'],'dias, de',r['inicio'],'até',r['fim'])
        latest=conn.execute(sql('SELECT COUNT(*) AS n FROM jt_5cd_registros WHERE data_relatorio=?'),(r['fim'],)).fetchone()
        print('ULTIMO DIA:',r['fim'], '|',latest['n'],'remessas')
    print('Carga finalizada. Inicie o painel e abra /#5cd.')

if __name__=='__main__':main()
