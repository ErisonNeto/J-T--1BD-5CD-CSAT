# J&T Express — Painel de Qualidade | 1BD · 5CD · CSAT

Painel FastAPI com os indicadores **1BD** e **5CD** e aba reservada para **CSAT**. Exibe filtros por UF, S/C e base (R/M Orlean), histórico por dia, comparativos semanais de segunda a domingo, rankings e exportação CSV. Usa Gestão de colaboradores atualizada.

## Como funciona

- **Local no Windows**: `dados/jt_1bd.sqlite3` para importações e validação.
- **Banco central da J&T**: publicar o SQLite no PostgreSQL através de `publicar_postgres_via_api.py`, que chama a **JT API** com autenticação.
- **Render**: executar o painel com `JT_STORAGE_MODE=api` para consultar o PostgreSQL via `https://jt-api.rockettechbr.com.br/query`, sem acesso direto ao IP privado da VM.

Nenhum arquivo de remessas, `.env`, banco SQLite ou segredo é versionado neste repositório público.

## Publicação

Consulte **[README_DEPLOY.md](README_DEPLOY.md)** para as instruções completas de migração, GitHub e Render. O arquivo `render.yaml` inclui autenticação obrigatória do painel e exige configurar `JT_API_KEY`, `DASH_USER` e `DASH_PASS` como segredos no Render.

## Desenvolvimento

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

O indicador **CSAT** só será implementado depois que os critérios e a fonte oficial forem definidos.
