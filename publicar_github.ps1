# Executar na raiz do projeto. Publica SOMENTE codigo; preserva dados e credenciais.
$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/ErisonNeto/J-T--1BD-5CD-CSAT.git'
$origem = (Get-Location).Path
if (-not (Test-Path (Join-Path $origem 'main.py'))) { throw 'Abra a pasta do projeto que contem main.py' }
$destino = Join-Path ([System.IO.Path]::GetTempPath()) ('JT-Qualidade-Publicacao-' + [Guid]::NewGuid().ToString('N'))
$permitidos = @(
  'main.py','database.py','indicador_5cd.py','importar_excel.py','importar_5cd.py',
  'migrar_sqlite_postgres.py','publicar_postgres_via_api.py','publicar_supabase.py','atualizar_gestao.py',
  'verificar_banco.py','xlsx_reader.py','aliases.json','requirements.txt',
  'render.yaml','schema.sql','schema_supabase.sql','.gitignore','.env.exemplo','README_DEPLOY.md',
  'INICIAR_AQUI.md','LEIA-ME.md','README.md','static','publicar_github.ps1'
)
Write-Host 'Clonando repositório público da J&T...' -ForegroundColor Cyan
git clone $repo $destino
if ($LASTEXITCODE -ne 0) { throw 'Falha no clone: instale Git e autentique no GitHub.' }
foreach($file in $permitidos) {
  $p = Join-Path $origem $file
  if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination $destino -Recurse -Force }
}
git -C $destino add .
if ($LASTEXITCODE -ne 0) { throw 'Falha no git add' }
$arquivos = @(git -C $destino diff --cached --name-only)
if ($arquivos | Where-Object { $_ -match '(^|/)(dados/|\.env$|\.venv/)|\.(sqlite3|db|xlsx|xls|csv|zip|rar)$' }) {
  throw 'Arquivo sensível detectado. Não foi feito commit/push.'
}
if (-not $arquivos.Count) { Write-Host 'Sem alterações para publicar.'; exit 0 }
Write-Host 'Arquivos que serão publicados:' -ForegroundColor Cyan
git -C $destino diff --cached --stat
Write-Host 'Conferindo conteúdo a publicar:' -ForegroundColor Cyan
git -C $destino status --short
git -C $destino commit -m 'feat: qualidade 1BD 5CD no Supabase'
if ($LASTEXITCODE -ne 0) { throw 'Falha no commit: confira user.name/user.email do git.' }
git -C $destino push origin main
if ($LASTEXITCODE -ne 0) { throw 'Falha no push; confirme permissão no repositório.' }
Write-Host 'Publicado: https://github.com/ErisonNeto/J-T--1BD-5CD-CSAT' -ForegroundColor Green
