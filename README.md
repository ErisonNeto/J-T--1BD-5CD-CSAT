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


## Exportar remessas e tickets (Excel)

Os botões **Exportar remessas (Excel)** nos três indicadores geram arquivos `.xlsx` por linha operacional, respeitando os filtros da aba:
- **1BD:** data da avaliação, remessa, ticket, resultado 1BD, problema, horários e dados de Gestão.
- **5CD:** data original do relatório, remessa, Package ID, dias em base, atraso/faixa, operação, motivo, base e responsável.
- **CSAT:** semana oficial, data da avaliação, tracking/remessa, ticket, nota positiva/negativa, categoria, base e responsável. Mantém avaliações repetidas para auditoria.

Os IDs são gravados como **texto no Excel**, evitando notação científica e perda de zeros. Há uma aba `Informações` com a quantidade de registros e os critérios aplicados.

**Segurança:** o painel pode continuar público, mas TODOS os downloads de CSV/XLSX exigem autenticação Basic com `DASH_USER` e `DASH_PASS` definidas em **Render > J-T--1BD-5CD-CSAT > Environment**. Se não estiverem configuradas, a exportação retorna HTTP 503 em vez de expor rastreios/tickets. O navegador solicitará usuário e senha na primeira exportação. Não publique credenciais em código, JS ou URL.

Os CSVs legados permanecem disponíveis nos endereços `/api/exportar.csv`, `/api/5cd/exportar.csv` e `/api/csat/exportar.csv` (este último continua como resumo agregado). Os botões do painel utilizam os novos endpoints `exportar.xlsx`.

Depois de configurar as variáveis, execute um novo deploy do último commit no Render e teste cada botão com filtros de um único dia/semana. Nenhum endpoint de exportação grava no banco.
