-- J&T Qualidade | CSAT TikTok | Banco jt_indicadores
-- Execute SOMENTE se tiver acesso administrativo ao PostgreSQL.
-- Quem não tem VM usa publicar_csat_via_api.py para criação via JT API /import.
-- Não modifica nenhuma tabela do 1BD, 5CD ou Gestão compartilhada.
BEGIN;
CREATE TABLE IF NOT EXISTS public.jt_csat_registros (
    id TEXT PRIMARY KEY,
    ano INTEGER NOT NULL,
    semana_numero INTEGER NOT NULL,
    semana_id TEXT NOT NULL,
    semana_descricao TEXT NOT NULL,
    data_avaliacao TEXT,
    base_chave TEXT NOT NULL,
    base TEXT NOT NULL,
    codigo TEXT,
    uf TEXT,
    rm TEXT NOT NULL,
    coordenador TEXT,
    supervisor TEXT,
    sc TEXT,
    tipo_sc TEXT,
    avaliacao INTEGER NOT NULL CHECK (avaliacao IN (0, 1)),
    ticket TEXT,
    tracking TEXT,
    categoria TEXT,
    arquivo_origem TEXT
);
-- Também funciona quando a tabela já foi criada via /import e tem UNIQUE(id).
CREATE INDEX IF NOT EXISTS ix_csat_semana ON public.jt_csat_registros(ano, semana_numero);
CREATE INDEX IF NOT EXISTS ix_csat_semana_base ON public.jt_csat_registros(semana_id, base_chave);
CREATE INDEX IF NOT EXISTS ix_csat_uf_sc ON public.jt_csat_registros(uf, sc);
CREATE INDEX IF NOT EXISTS ix_csat_data ON public.jt_csat_registros(data_avaliacao);
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jt_app') THEN
        GRANT SELECT, INSERT, UPDATE ON public.jt_csat_registros TO jt_app;
    END IF;
END $$;
COMMIT;
