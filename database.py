"""Acesso local SQLite ou PostgreSQL 18 pela variável DATABASE_URL."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
# Compartilhado por FastAPI, importador diário e migrador; variáveis do processo têm prioridade.
load_dotenv(ROOT / ".env", override=False)
DEFAULT_SQLITE = ROOT / "dados" / "jt_1bd.sqlite3"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgresql://", "postgres://"))


def connection():
    if IS_POSTGRES:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Para PostgreSQL instale: pip install 'psycopg[binary]'") from exc
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    if DATABASE_URL and DATABASE_URL.startswith("sqlite:///"):
        path = Path(DATABASE_URL[10:]).resolve()
    elif DATABASE_URL:
        raise ValueError("DATABASE_URL deve começar com postgresql:// ou sqlite:///")
    else:
        path = DEFAULT_SQLITE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def sql(sqlite_stmt: str) -> str:
    return sqlite_stmt.replace("?", "%s") if IS_POSTGRES else sqlite_stmt


def setup():
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS jt_1bd_gestao (
          base_chave TEXT PRIMARY KEY,
          codigo TEXT, nome TEXT NOT NULL, uf TEXT, regional TEXT,
          rm TEXT, coordenador TEXT, supervisor TEXT, sc TEXT,
          tipo_sc TEXT, situacao TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS jt_1bd_registros (
          id TEXT PRIMARY KEY, data_avaliacao TEXT NOT NULL,
          remessa TEXT NOT NULL, ticket TEXT, entregue INTEGER NOT NULL,
          base_original TEXT NOT NULL, base_chave TEXT NOT NULL,
          problema TEXT, horario_assinatura TEXT, data_registro TEXT,
          arquivo_origem TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_1bd_data ON jt_1bd_registros(data_avaliacao)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_1bd_base ON jt_1bd_registros(base_chave)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_1bd_rm ON jt_1bd_gestao(rm)")
        conn.commit()


def rows(query: str, params=()):
    with connection() as conn:
        cur = conn.execute(sql(query), params)
        return [dict(x) for x in cur.fetchall()]


def scalar(query: str, params=()):
    result = rows(query, params)
    return next(iter(result[0].values())) if result else None
