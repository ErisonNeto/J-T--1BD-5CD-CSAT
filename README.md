# J&T | Painel de Qualidade — 1BD · 5CD · CSAT

Painel de qualidade TikTok para as bases do R/M Orlean. Este repositório está sendo preparado para receber o código do dashboard FastAPI.

## Indicadores
- 1BD: taxa de avaliações 'Sim' sobre total de avaliações, a partir da aba `明細_Detalhamento` (G = data, I = remessa, K = Sim/Não, N = base).
- 5CD: quantidade de remessas distintas por data de relatório e base (I = data do relatório, O = remessa, P = base). Não confundir com taxa de SLA; médias semanais dos relatórios existentes.
- CSAT: aguarda planilha, denominador e regra oficial. Não há valores fictícios.

Responsáveis e filtro R/M Orlean: `Gestão de colaboradores`; correção do Johan mantida na versão local. Datas inicial e final padronizadas em D-2; semanas são segunda a domingo. Comparações D-7 e semana anterior incluídas.

## Banco
As tabelas desta aplicação são criadas pelo arquivo [schema.sql](schema.sql) no PostgreSQL `jt_indicadores`: `jt_1bd_gestao`, `jt_1bd_registros` e `jt_5cd_registros`. O SQL não remove outros indicadores.

A carga inicial pode utilizar o SQLite local do dashboard via `migrar_sqlite_postgres.py`, executado numa máquina que tenha acesso autorizado ao PostgreSQL (não no Render). *Não versionar SQLite, XLSX, .env nem credenciais.*

## Publicação
- Código do FastAPI, frontend e importadores deve ser enviado para a raiz deste repositório.
- Render pode importar o `render.yaml`, com `DATABASE_URL` e as credenciais do painel configuradas como variáveis de ambiente.
- **A VM host-only 192.168.56.10 NÃO é acessível diretamente pelo Render.** Para manter o PostgreSQL na VM, é preciso disponibilizar uma API HTTPS autenticada na VM e adaptar o dashboard para consultá-la. Alternativa: usar um PostgreSQL hospedado acessível pelo Render, com controles de acesso.
- `JT_API_URL` e `JT_API_KEY` não substituem `DATABASE_URL` no código existente: a integração HTTP ainda precisa ser implementada.
- Sem banco acessível e alimentado, o serviço pode iniciar vazio; isso não equivale a publicação de dados operacionais.

## Segurança
Proteja o dashboard antes de publicar, mantenha `.env` fora do Git e gire chaves que já tenham sido expostas.
