"""Importação histórica e incremental do 1BD TikTok.

Coloque os XLSX em ./dados e execute: python importar_excel.py
O importador é idempotente em novas exportações que repetem registros históricos.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path

from database import connection, setup, sql
from xlsx_reader import data_excel, ler_aba, normalizar

ROOT = Path(__file__).resolve().parent
ORLEAN = normalizar("ORLEAN DA SILVA DO NASCIMENTO")


def arquivos_entrada(pasta: Path, gestao: str | None = None, dados: list[str] | None = None):
    if gestao:
        gestao_path = Path(gestao).resolve()
    else:
        matches = [f for f in pasta.rglob('*.xlsx') if 'gest' in f.name.lower() and 'colaborador' in f.name.lower()]
        if not matches:
            raise FileNotFoundError("Não encontrei 'Gestão de colaboradores.xlsx' em dados/")
        gestao_path = max(matches, key=lambda p: p.stat().st_mtime)
    if dados:
        files = [Path(f).resolve() for f in dados]
    else:
        files = sorted(f for f in pasta.rglob('*.xlsx')
                       if not f.name.startswith('~$')
                       and not ('gest' in f.name.lower() and 'colaborador' in f.name.lower())
                       and ('1bd' in f.name.lower() or 'entregas concluídas' in f.name.lower()))
    files = [f for f in files if f.resolve() != gestao_path.resolve() and f.is_file()]
    if not files:
        raise FileNotFoundError("Não encontrei relatórios 1BD XLSX em dados/")
    return gestao_path, files


def _primeiro_nao_vazio(vals):
    return next((v for v in vals if str(v or '').strip()), '')


def carregar_gestao(caminho: Path):
    grupos = defaultdict(list)
    header = None
    for i, row in enumerate(ler_aba(caminho, 'Responsáveis atuais')):
        if i == 0:
            header = row
            for col, nome in {'A': 'Nome da base', 'G': 'Responsável da Região', 'H': 'Coordenador', 'I': 'Supervisor'}.items():
                if normalizar(nome) not in normalizar(header.get(col, '')):
                    raise ValueError(f'Gestão: coluna {col} não corresponde a {nome}')
            continue
        nome = row.get('A','').strip()
        if not nome:
            continue
        uf = row.get('F','').strip().upper()
        gestor = row.get('G','').strip()
        coord = row.get('H','').strip()
        sup = row.get('I','').strip()
        codigo = row.get('B','').strip()
        sc = coord or sup
        nivel = 'Coordenador' if coord else ('Supervisor' if sup else 'Sem S/C')
        grupos[normalizar(nome)].append((codigo,nome,uf,row.get('E','').strip(),gestor,coord,sup,sc,nivel,row.get('O','').strip()))
    validos = {}
    conflitos = {}
    for chave, valores in grupos.items():
        # Duplicações idênticas na planilha são inofensivas e não geram contagem dupla.
        atribuicoes = set((v[0], normalizar(v[4]), normalizar(v[5]), normalizar(v[6])) for v in valores)
        if len(atribuicoes) == 1:
            validos[chave] = valores[0]
        else:
            conflitos[chave] = valores
    with connection() as conn:
        conn.execute('DELETE FROM jt_1bd_gestao')
        statement = sql('''INSERT INTO jt_1bd_gestao (
              base_chave,codigo,nome,uf,regional,rm,coordenador,supervisor,sc,tipo_sc,situacao
              ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''')
        for key,v in validos.items():
            conn.execute(statement, (key, *v))
        conn.commit()
    return validos, conflitos


def carregar_aliases():
    path=ROOT/'aliases.json'
    aliases=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return {normalizar(k):normalizar(v) for k,v in aliases.items()}


def carregar_1bd(caminho: Path, aliases: dict):
    contagem=Counter()
    rep=Counter()
    orlean_preview=Counter()
    por_base_sem_match=Counter()
    sql_stmt=sql('''INSERT INTO jt_1bd_registros
        (id,data_avaliacao,remessa,ticket,entregue,base_original,base_chave,problema,horario_assinatura,data_registro,arquivo_origem)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          entregue=excluded.entregue,
          problema=excluded.problema,
          horario_assinatura=excluded.horario_assinatura,
          data_registro=excluded.data_registro,
          arquivo_origem=excluded.arquivo_origem''')
    with connection() as conn:
        gestao_map={r['base_chave']:r['rm'] for r in conn.execute('SELECT base_chave, rm FROM jt_1bd_gestao').fetchall()}
        for i,r in enumerate(ler_aba(caminho, '明細_Detalhamento')):
            if i==0:
                if 'Remessa' not in r.get('I','') or '1BD' not in r.get('K',''):
                    raise ValueError(f'{caminho.name}: estrutura da aba Detalhamento inesperada (I/K).')
                continue
            if not r.get('I','').strip():
                continue
            try:
                date=data_excel(r.get('G'))
            except ValueError:
                contagem['data_invalida']+=1
                continue
            remessa=r.get('I','').strip()
            ticket=r.get('H','').strip()
            status=normalizar(r.get('K'))
            if status not in ('SIM','NAO'):
                contagem['status_invalido']+=1
                continue
            base=r.get('N','').strip()
            original_key=normalizar(base)
            base_key=aliases.get(original_key,original_key)
            chave=(date,ticket,remessa,base_key)
            rep[chave]+=1
            # Mantém linhas repetidas do mesmo ticket e mesma data: o resumo oficial contabiliza cada ocorrência.
            ident='|'.join((date,ticket,remessa,base_key,str(rep[chave])))
            uid=hashlib.sha256(ident.encode('utf-8')).hexdigest()
            vals=(uid,date,remessa,ticket,1 if status=='SIM' else 0,base,base_key,
                  r.get('L',''),r.get('J',''),r.get('M',''),caminho.name)
            conn.execute(sql_stmt,vals)
            contagem['linhas_validas']+=1
            if base_key in gestao_map and normalizar(gestao_map[base_key])==ORLEAN:
                orlean_preview[(date,status)]+=1
            elif base_key not in gestao_map:
                por_base_sem_match[base]+=1
            if contagem['linhas_validas'] % 15000 == 0:
                conn.commit()
        conn.commit()
    return contagem,orlean_preview,por_base_sem_match


def main():
    parser=argparse.ArgumentParser(description='Carga Excel 1BD do TikTok para indicadores J&T')
    parser.add_argument('--pasta', default=str(ROOT/'dados'))
    parser.add_argument('--gestao', default=None)
    parser.add_argument('--arquivos', nargs='*', default=None)
    args=parser.parse_args()
    pasta=Path(args.pasta).resolve()
    gestao,files=arquivos_entrada(pasta,args.gestao,args.arquivos)
    setup()
    validos, conflitos = carregar_gestao(gestao)
    aliases=carregar_aliases()
    print('='*64)
    print('1BD TIKTOK · J&T | CARGA HISTÓRICA / INCREMENTAL')
    print('='*64)
    print(f'Gestão: {gestao.name} | {len(validos)} bases únicas | {len(conflitos)} conflitos pendentes')
    if conflitos:
        for key,vl in conflitos.items():
            print(f'  GESTÃO CONFLITANTE: {key}: {vl}')
    print(f'Relatórios 1BD encontrados: {len(files)}')
    sem_match=Counter()
    for arquivo in files:
        cnt,preview,faltantes=carregar_1bd(arquivo,aliases)
        sem_match.update(faltantes)
        print(f'  OK {arquivo.name}: {cnt["linhas_validas"]:,} registros | Orlean (arquivo): {sum(preview.values()):,} registros')
        for k,v in cnt.items():
            if k!='linhas_validas':print('  AVISO:',k,v)
    with connection() as conn:
        resum=conn.execute('''SELECT COUNT(*) AS total, SUM(r.entregue) AS sim
            FROM jt_1bd_registros r JOIN jt_1bd_gestao g ON g.base_chave=r.base_chave
            WHERE g.rm=?''' if not __import__('database').IS_POSTGRES else '''SELECT COUNT(*) AS total, SUM(r.entregue) AS sim
            FROM jt_1bd_registros r JOIN jt_1bd_gestao g ON g.base_chave=r.base_chave
            WHERE g.rm=%s''',('ORLEAN DA SILVA DO NASCIMENTO',)).fetchone()
        count=int(resum['total']); sim=int(resum['sim'] or 0)
        print(f'BANCO | Orlean: {count:,} avaliações | {sim:,} Sim | {(100*sim/count) if count else 0:.2f}%')
        latest=conn.execute('''SELECT MAX(r.data_avaliacao) AS data FROM jt_1bd_registros r
            JOIN jt_1bd_gestao g ON r.base_chave=g.base_chave WHERE g.rm='ORLEAN DA SILVA DO NASCIMENTO' ''').fetchone()
        print('Última data Orlean:',latest['data'])
    if sem_match:
        print('\nBases sem correspondência na Gestão (todas as regionais):')
        for base,n in sem_match.most_common(15):print(f'   {base}: {n} registros')
    print('Concluído. Agora execute: uvicorn main:app --host 0.0.0.0 --port 8001')


if __name__ == '__main__':
    main()
