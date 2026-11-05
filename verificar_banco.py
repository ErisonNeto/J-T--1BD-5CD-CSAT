"""Diagnóstico somente leitura. Não cria tabelas, não importa nem apaga remessas."""
from pathlib import Path
import sqlite3
from urllib.parse import quote
from database import ROOT, DATABASE_URL, DEFAULT_SQLITE, IS_POSTGRES

if IS_POSTGRES:
    print("O .env está apontando para PostgreSQL. Diagnóstico SQLite não aplicável.")
    raise SystemExit(0)
if DATABASE_URL and DATABASE_URL.startswith("sqlite:///"):
    file_path = Path(DATABASE_URL[len("sqlite:///"):])
    if not file_path.is_absolute():
        file_path = ROOT / file_path
    file_path = file_path.resolve()
else:
    file_path = DEFAULT_SQLITE
print("Arquivo SQLite em uso:", file_path)
print("Existe?", "SIM" if file_path.is_file() else "NÃO")
if not file_path.is_file():
    print("Pasta do projeto:", ROOT)
    print("Extraia o projeto completo com a pasta dados e reinicie.")
    raise SystemExit(1)
conn = sqlite3.connect(f"file:{quote(file_path.as_posix(), safe='/:')}?mode=ro", uri=True)
for table, field in (("jt_1bd_gestao", None), ("jt_1bd_registros", "data_avaliacao"), ("jt_5cd_registros", "data_relatorio")):
    table_exists = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
    if not table_exists:
        print(table, "TABELA AUSENTE")
        continue
    count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if field:
        last = conn.execute(f"SELECT max({field}) FROM {table}").fetchone()[0]
        print(table, "linhas:", count, "último relatório:", last)
    else:
        print(table, "linhas:", count)
conn.close()
