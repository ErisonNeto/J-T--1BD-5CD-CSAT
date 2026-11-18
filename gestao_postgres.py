"""Gestão de bases e gestores vigente no PostgreSQL J&T via JT API."""
from __future__ import annotations
import os
import time
from functools import lru_cache
import requests

GESTAO_SQL = """
SELECT estacao_no, nome_base, uf, responsavel_regiao, coordenador,
       supervisor, status_atual, sc_dc_responsavel, tipo_base
FROM jt_operacao.vw_gestao_colaboradores_atual
"""


def _codigo(valor):
    valor = str(valor or "").strip()
    return valor[:-2] if valor.endswith(".0") and valor[:-2].isdigit() else valor


@lru_cache(maxsize=2)
def mapa_gestao(bucket=None):
    url = os.getenv("JT_API_URL", "https://jt-api.rockettechbr.com.br").strip().rstrip("/")
    key = os.getenv("JT_API_KEY", "").strip()
    if not url.startswith("https://") or not key:
        raise RuntimeError("JT_API_URL HTTPS e JT_API_KEY obrigatórios para consultar a gestão.")
    resposta = requests.post(
        url + "/query", headers={"X-API-Key": key},
        json={"sql": GESTAO_SQL, "params": []}, timeout=(15, 90),
    )
    resposta.raise_for_status()
    payload = resposta.json()
    colunas, linhas = payload.get("colunas"), payload.get("rows")
    if not isinstance(colunas, list) or not isinstance(linhas, list):
        raise RuntimeError("Resposta inválida da gestão PostgreSQL.")
    result = {}
    for linha in linhas:
        row = linha if isinstance(linha, dict) else dict(zip(colunas, linha))
        if _codigo(row.get("estacao_no")):
            result[_codigo(row["estacao_no"])] = row
    if not result:
        raise RuntimeError("Gestão PostgreSQL sem estações.")
    return result


def enriquecer(registros):
    if not registros or "codigo" not in registros[0]:
        return registros
    mapa = mapa_gestao(int(time.time() // 300))
    atualizados = []
    for original in registros:
        row = dict(original)
        g = mapa.get(_codigo(row.get("codigo")))
        if g:
            row["gestao_encontrada"] = True
            row["rm"] = str(g.get("responsavel_regiao") or "").strip()
            row["coordenador"] = str(g.get("coordenador") or "").strip()
            row["supervisor"] = str(g.get("supervisor") or "").strip()
            row["sc"] = row["coordenador"] or row["supervisor"]
            row["tipo_sc"] = ("Coordenador" if row["coordenador"] else
                             "Supervisor" if row["supervisor"] else "S/C")
            if g.get("nome_base"):
                row["base"] = g["nome_base"]
            if g.get("uf"):
                row["uf"] = g["uf"]
            row["situacao"] = g.get("status_atual") or row.get("situacao")
            row["sc_dc_responsavel"] = g.get("sc_dc_responsavel") or ""
        else:
            row["gestao_encontrada"] = False
        atualizados.append(row)
    return atualizados
