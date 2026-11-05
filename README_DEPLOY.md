# Publicação Qualidade no Supabase NOVO

## Banco
- `schema_supabase.sql`: SQL executado no editor do Supabase da conta NOVA, contendo 3 tabelas e RLS ativo, sem permissões públicas.
- `publicar_supabase.py`: coleta histórico do `dados/jt_1bd.sqlite3`, com UPSERT por ID e amostras de verificação. Usa secret key unicamente no backend.
- Base: **1BD = 12.354**, **5CD = 29.964** e **Gestão = 510** (números da última carga local confirmada). O script exibe sempre os totais reais.
- Importação é idempotente. O arquivo operacional `dados/jt_1bd.sqlite3` NÃO é incluído nesta atualização de código.

## Variáveis
```
JT_STORAGE_MODE=supabase
SUPABASE_URL=https://REF.supabase.co
SUPABASE_SECRET_KEY=sb_secret_... (somente env, nunca GitHub)
SUPABASE_CACHE_SECONDS=120
META_1BD=0.80
DASH_USER=usuario
DASH_PASS=senha_forte
```

## Testes
```
python verificar_banco.py
python publicar_supabase.py
python publicar_supabase.py --aplicar --confirmar-projeto REF
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Render
`render.yaml` define o modo `supabase` e exige variáveis secretas. Não configure DATABASE_URL nem JT_API_URL para este indicador. Em ambiente Render, ligar `REQUIRE_DASH_AUTH` e `REQUIRE_REMOTE_DB`.

## Segurança
- RLS ativo nas 3 tabelas sem policies para anon/authenticated.
- Grants apenas para service_role e REVOKE para anon/authenticated.
- Chave secret somente no backend; não chamar REST do navegador com essa chave.
- NUNCA subir `dados/` ou `.env` ao GitHub.
- Repositório público contém apenas código, não linhas de remessas, planilhas ou tokens.
- Dependendo das configurações da Data API, será necessário habilitar o schema public; o SQL concede permissões service_role.
- A troca de conta do Supabase não troca automaticamente as chaves do Render, que devem ser configuradas manualmente como segredo.
