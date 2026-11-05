"""Atualiza somente atribuições de bases (R/M, coordenador e supervisor).

Mantém os históricos 1BD e 5CD intactos. Reclassifica automaticamente as linhas
no dashboard por JOIN com jt_1bd_gestao. Não exige planilhas originais 1BD/5CD.

Uso:
  python atualizar_gestao.py
  python atualizar_gestao.py --gestao "dados/Gestão de colaboradores.xlsx"
"""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
from database import connection, setup
from importar_excel import carregar_gestao
from xlsx_reader import normalizar

ROOT = Path(__file__).resolve().parent
ORLEAN = "ORLEAN DA SILVA DO NASCIMENTO"
JOHAN = "JOHAN RAFAEL QUEIROZ PACHECO"


def main():
    parser = argparse.ArgumentParser(description="Atualizar Gestão no painel J&T sem reimportar histórico")
    parser.add_argument("--gestao", type=Path, default=ROOT / "dados" / "Gestão de colaboradores.xlsx")
    args = parser.parse_args()
    gestao = args.gestao.resolve()
    if not gestao.is_file():
        parser.error(f"Gestão não encontrada: {gestao}")
    setup()
    validos, conflitos = carregar_gestao(gestao)
    print("=" * 68)
    print("GESTÃO ATUALIZADA — 1BD + 5CD (SEM ALTERAR REMESSAS)")
    print("=" * 68)
    print(f"Origem: {gestao.name}")
    print(f"Bases únicas válidas: {len(validos)} | Nomes com conflito: {len(conflitos)}")
    for chave, registros in conflitos.items():
        print(f"  ALERTA CONFLITO: {chave} | {len(registros)} linhas; fora do cruzamento")
    with connection() as conn:
        rows = conn.execute("SELECT codigo, nome, rm, coordenador, supervisor, sc, tipo_sc FROM jt_1bd_gestao").fetchall()
        orlean = [r for r in rows if normalizar(r['rm']) == normalizar(ORLEAN)]
        johan = sorted((r for r in orlean if normalizar(r['coordenador']) == normalizar(JOHAN) or normalizar(r['supervisor']) == normalizar(JOHAN)), key=lambda r:r['nome'])
        print(f"Bases do Orlean: {len(orlean)}")
        print(f"Bases vinculadas a Johan: {len(johan)}")
        for r in johan:
            print(f"  {r['codigo']} | {r['nome']} | Coordenador: {r['coordenador'] or '-'} | Supervisor: {r['supervisor'] or '-'}")
        for table in ('jt_1bd_registros', 'jt_5cd_registros'):
            try:
                total = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()['n']
                filtrado = conn.execute(f"""SELECT COUNT(*) AS n FROM {table} r
                   JOIN jt_1bd_gestao g ON g.base_chave=r.base_chave WHERE g.rm=?""", (ORLEAN,)).fetchone()['n']
                print(f"{table}: {total:,} registros históricos preservados | Orlean: {filtrado:,}")
            except Exception as exc:
                print(f"{table}: tabela ainda não existe ({exc})")
    print("Atualização concluída. Reinicie o dashboard e confira os filtros S/C.")

if __name__ == '__main__':
    main()
