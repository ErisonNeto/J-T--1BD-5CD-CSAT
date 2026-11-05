# J&T Qualidade — nova conta Supabase

1. NÃO substitua sua pasta `dados` nem seu `.env` sem salvar uma cópia. Faça backup do SQLite original.
2. Faça login no projeto NOVO Supabase e confira a URL do projeto. Abra **SQL Editor**, copie o conteúdo inteiro de `schema_supabase.sql` e execute. Confirme as 3 tabelas no **Table Editor**.
3. Crie uma secret API key no projeto novo em **Settings > API Keys**, caso ainda não exista. No `.env` local, defina **JT_STORAGE_MODE=supabase**, **SUPABASE_URL** e **SUPABASE_SECRET_KEY**. Nunca compartilhe a chave nem a salve em GitHub.
4. Na pasta do projeto original com `dados/jt_1bd.sqlite3`, execute `python publicar_supabase.py` (só conferência). Ao validar o destino, execute o comando `--aplicar --confirmar-projeto ...` indicado pelo script.
5. Rode `python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload` e valide `/health`, `/#1bd`, `/#5cd`.
6. Depois use `publicar_github.ps1` para publicar SOMENTE código. No Render, configure os 4 segredos `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `DASH_USER`, `DASH_PASS`. O deploy não é automático sem vincular o repositório.

**Atenção:** as tabelas contêm dados operacionais. O SQL inclui RLS ativo e não autoriza acesso anônimo. O backend usa secret key; essa chave NUNCA deve aparecer no JavaScript.

**Importações futuras:** o `importar_excel.py` e `importar_5cd.py` continuam importando apenas para SQLite. Para usar o processo usual, mude temporariamente `JT_STORAGE_MODE=` no `.env`, execute a importação, altere novamente para `supabase` e execute `python publicar_supabase.py --aplicar --confirmar-projeto <ref>`.
