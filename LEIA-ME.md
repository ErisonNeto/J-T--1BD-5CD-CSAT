# Painel Único J&T — 1BD · 5CD · CSAT

## Gestão atualizada em 04/11/2026 — Johan / Orlean

Este pacote incorpora a Gestão recebida em 04/11/2026 às 23:55.
Foram corrigidos os responsáveis de 10 bases: CST -PA, CPN -PA, SLP -PA,
VGA -PA, F CST-PA, SIP-PA, CRA-PA, MAR-PA, STA-PA e PRM-PA.
A Gestão atual identifica 11 bases de Johan como **coordenador** (incluindo F IGA-PA,
que já estava correta). Os supervisores dessas 11 bases estão em branco na fonte;
o painel não inventa supervisores.

O banco SQLite distribuído já está **atualizado**. Permanecem inalterados:
12.354 registros do 1BD e 29.964 do 5CD. Os filtros e rankings atribuem os
registros a S/C por meio do JOIN com a Gestão atual.

Para aplicar **apenas a correção da Gestão** em uma pasta antiga do projeto,
copie o arquivo `atualizar_gestao.py` e `dados/Gestão de colaboradores.xlsx`
para as mesmas posições dessa pasta antiga, sem substituir o SQLite. Então execute:

```powershell
python atualizar_gestao.py
```

Ou, quando já existir o ambiente virtual:

```powershell
.\.venv\Scripts\python.exe atualizar_gestao.py
```

O comando substitui somente os vínculos de bases, não exclui nem reimporta
remessas do 1BD/5CD. Reinicie o servidor para refazer os filtros.

## Situação atual (04/11/2026)

| Aba | Status | Origem |
|---|---|---|
| **1BD** | Funcional | TikTok, aba `明細_Detalhamento` + Gestão de colaboradores |
| **5CD** | **Funcional e já carregado no SQLite incluído** | TikTok, abas `Dados históricos 历史数据` e `BD`, + Gestão atualizada |
| CSAT | Em preparação | Aguardando planilha e regras de apuração |

**Atenção:** nenhuma migração para PostgreSQL foi executada no seu computador. A versão deste ZIP começa funcionando com o SQLite já populado, para não depender de configurar banco ou API agora.

### Dados importados que acompanham este ZIP

- 1BD: 12.354 avaliações na base histórica, preservadas.
- 5CD: **29.964** registros distintos por data do relatório (I) + remessa (O) + base (P), filtro somente Gestão do Orlean; 90 datas, de 01/08/2026 a 04/11/2026.
- 5CD no relatório 04/11/2026: **594 remessas** do Orlean.
- Gestão: 510 nomes de bases sem conflito; **1 base conflitante** (`ARI -MT`, não atribuída ao Orlean) fica fora do cruzamento até corrigir. Bases fora do Orlean não entram no indicador.
- Foram identificados 10.432 registros da fonte 5CD sem correspondência direta na Gestão/aliases; a maior parte está fora das regiões do Orlean. Confira o log de importação ao atualizar a Gestão. Para nomes divergentes validados, ajuste `aliases.json`.

### Entendendo o 5CD

- **I**: `Dt. Envio TikTok` = **data do relatório**, nunca a data da operação ou entrega individual do pacote.
- **O**: `tracking_nos` = código de remessa.
- **P**: `Base` = nome que se cruza com `Gestão de colaboradores > Responsáveis atuais!A:A` para obter código, UF, R/M, coordenador e supervisor.
- **C**: `Dias em Base` = faixas 5 a 9, 10 a 14, 15 a 19, 20+.
- **M**: `Está em atraso?` = atributo complementar. Muitos registros vêm com `#N/A`; **não calcular taxa de cumprimento usando esse campo**.
- Cada remessa é contada **uma vez por data do relatório e base**. A mesma remessa pode aparecer em mais de um dia, porque se trata de snapshots de pendências.
- KPI principal: **quantidade de remessas no último relatório disponível dentro do período filtrado**, não a soma de pendências em vários dias.
- Comparação semanal: cada semana é **segunda a domingo**; o valor da semana é a **média diária do volume nos dias em que existem relatórios**, nunca a soma das mesmas remessas ao longo dos dias. Os dias faltantes não são forçados a zero.
- Ao filtrar uma base ou S/C, um dia com relatório mas sem pendências daquela base é considerado **0**; um dia sem relatório para a regional inteira é considerado ausente.
- Variação = `(semana atual / semana anterior − 1) × 100`, em percentual, e diferença absoluta de remessas. D-7 compara a data do relatório ao mesmo dia da semana anterior.
- **Aumento de pendências é ruim; redução de pendências é boa.** Os rankings 5CD mostram maiores volumes primeiro.
- Não há taxa 5CD (%) oficial calculada nesta versão porque este export lista pendências e não oferece um total de pedidos elegíveis para ser usado como denominador.

## Executar localmente (PowerShell do VS Code)

### Instalar na primeira vez

Use a pasta **nova** extraída do ZIP (não é necessário usar `py`, que não funcionou no seu PC):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Iniciar o painel

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Abra http://localhost:8001 e clique na aba **5CD**; links diretos: `/#1bd`, `/#5cd`, `/#csat`. Se a porta estiver em uso pelo servidor da versão anterior, pare-o com `Ctrl+C` primeiro.

### Atualizar 5CD quando chegar nova planilha

Coloque o Excel `5CD...xlsx` e a `Gestão de colaboradores.xlsx` na pasta `dados/`. Não coloque duas Gestões antigas se quiser evitar confusão na seleção automática (o importador usa a mais recente).

```powershell
.\.venv\Scripts\python.exe importar_5cd.py
```

Ou indique os caminhos explicitamente:

```powershell
.\.venv\Scripts\python.exe importar_5cd.py --gestao "dados\Gestão de colaboradores.xlsx" --arquivos "dados\TIKTOK-5CD.xlsx"
```

O importador extrai as abas `Dados históricos 历史数据` e `BD`. Quando a mesma combinação data/remessa/base aparece mais de uma vez, faz UPSERT sem duplicar. A aba BD substitui valores sobrepostos do histórico, se houver. **Não apaga o histórico de outras datas**.

Para atualizar só o 1BD, continue usando `importar_excel.py` (com a mesma Gestão atualizada).

## Migrar para seu PostgreSQL da VM quando estiver pronto

**Não faça isso antes de decidir usar o PostgreSQL.** Quando chegar a hora:

1. Copie `.env.exemplo` para `.env` e preencha `DATABASE_URL` com uma URL correta acessível de onde você executa o importador; não inclua senhas em capturas ou GitHub.
2. Confirme que a conexão com o PostgreSQL está autorizada e acessível na rede. Um IP host-only de VM não funciona a partir de qualquer computador na internet.
3. Rode `python migrar_sqlite_postgres.py` **uma vez**, depois que conectar. O migrador inclui **1BD, Gestão e 5CD** e pode ser reexecutado sem criar IDs duplicados.
4. Reinicie o `uvicorn` usando a mesma `.env`.

`JT_API_URL`/`JT_API_KEY` **não substituem** `DATABASE_URL`: este projeto, por enquanto, só utiliza conexão direta SQLite/PostgreSQL, não a API HTTP remota. Para importar através de `jt-api.rockettechbr.com.br` sem expor 5432, precisamos implementar rotas de ingestão autenticadas na API existente do servidor.

## Endpoints

- `GET /health` — 1BD e 5CD carregados.
- `GET /api/indicadores` — status 1BD/5CD/CSAT.
- `GET /api/dashboard`, `GET /api/filtros`, `GET /api/exportar.csv` — 1BD.
- `GET /api/5cd/dashboard`, `GET /api/5cd/filtros`, `GET /api/5cd/exportar.csv` — **5CD**.

## Segurança

- Não versione `.env` nem credenciais.
- Configure `DASH_USER` e `DASH_PASS` antes de publicar na internet.
- O arquivo XLSX original de aproximadamente 59 MB não acompanha o ZIP; só os dados 5CD do Orlean já normalizados e importados no SQLite.


### Padrão de datas D-2
Ao abrir o dashboard, os filtros de Data inicial e Data final de 1BD e 5CD recebem automaticamente a data D-2 conforme a data local do computador. O usuário pode alterar as datas. O botão Limpar repõe D-2. Se ainda não houver importação para D-2, o dashboard avisa a última data importada.


## Padrão visual SLA / Shipping Time
- Cabeçalho branco com faixa vermelha, badges J&T, Last Mile e R/M Orlean.
- Abas 1BD, 5CD e CSAT dentro de um único painel.
- Filtros em cards compactos, datas padrão D-2 (continuam editáveis).
- KPIs com acentos laterais, gráficos e rankings com o estilo J&T.
- Arquivos visuais: `static/index.html` e `static/style.css`. Substituir somente esses dois para atualizar um projeto já instalado.
- Não é necessário alterar `.env`, `dados/`, SQLite, Python nem a API.
