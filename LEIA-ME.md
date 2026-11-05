# J&T Qualidade 1BD, 5CD e CSAT

**Esta é a versão com integração à JT API HTTPS e PostgreSQL da VM.**

Leia primeiro `INICIAR_AQUI.md` e, para o passo a passo de implantação e segurança, `README_DEPLOY.md`.

- SQLite local: contém 1BD e 5CD após a importação Excel.
- Banco central: publicar com `python publicar_postgres_via_api.py --aplicar`.
- GitHub: executar `./publicar_github.ps1` a partir da raiz (sem Excel e sem credenciais).
- Render: configurar `JT_STORAGE_MODE=api`, `JT_API_KEY` e autenticação do painel.
- CSAT: ainda sem regras/arquivo oficiais.

Nunca envie `.env`, SQLite ou planilhas de remessas ao repositório público.
