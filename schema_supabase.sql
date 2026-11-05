-- J&T | Qualidade (1BD, 5CD) no projeto Supabase NOVO.
-- Executar no SQL Editor SOMENTE após conferir o projeto correto.
-- Não apaga dados nem tabelas existentes. CSAT será modelado após definir a fonte.
BEGIN;
CREATE TABLE IF NOT EXISTS public.jt_1bd_gestao (
  base_chave TEXT PRIMARY KEY,
  codigo TEXT,
  nome TEXT NOT NULL,
  uf TEXT,
  regional TEXT,
  rm TEXT,
  coordenador TEXT,
  supervisor TEXT,
  sc TEXT,
  tipo_sc TEXT,
  situacao TEXT
);
CREATE TABLE IF NOT EXISTS public.jt_1bd_registros (
  id TEXT PRIMARY KEY,
  data_avaliacao TEXT NOT NULL,
  remessa TEXT NOT NULL,
  ticket TEXT,
  entregue INTEGER NOT NULL CHECK (entregue IN (0,1)),
  base_original TEXT NOT NULL,
  base_chave TEXT NOT NULL,
  problema TEXT,
  horario_assinatura TEXT,
  data_registro TEXT,
  arquivo_origem TEXT
);
CREATE TABLE IF NOT EXISTS public.jt_5cd_registros (
  id TEXT PRIMARY KEY,
  data_relatorio TEXT NOT NULL,
  remessa TEXT NOT NULL,
  base_chave TEXT NOT NULL,
  base_original TEXT NOT NULL,
  dias_base DOUBLE PRECISION,
  atraso TEXT,
  faixa TEXT,
  operacao TEXT,
  package_id TEXT,
  motivo TEXT,
  arquivo_origem TEXT,
  aba_origem TEXT
);
CREATE INDEX IF NOT EXISTS ix_1bd_data ON public.jt_1bd_registros(data_avaliacao);
CREATE INDEX IF NOT EXISTS ix_1bd_base ON public.jt_1bd_registros(base_chave);
CREATE INDEX IF NOT EXISTS ix_1bd_rm ON public.jt_1bd_gestao(rm);
CREATE INDEX IF NOT EXISTS ix_5cd_data ON public.jt_5cd_registros(data_relatorio);
CREATE INDEX IF NOT EXISTS ix_5cd_base ON public.jt_5cd_registros(base_chave);
CREATE INDEX IF NOT EXISTS ix_5cd_date_base ON public.jt_5cd_registros(data_relatorio,base_chave);

-- Segurança: estes relatórios contêm dados operacionais. Somente o backend
-- com secret key pode consultar/importar. Nenhuma policy pública é criada.
ALTER TABLE public.jt_1bd_gestao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jt_1bd_registros ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jt_5cd_registros ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.jt_1bd_gestao, public.jt_1bd_registros, public.jt_5cd_registros FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.jt_1bd_gestao, public.jt_1bd_registros, public.jt_5cd_registros TO service_role;
COMMIT;
