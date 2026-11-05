# Publica somente o codigo no GitHub, sem enviar dados, SQLite e credenciais.
$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/ErisonNeto/J-T--1BD-5CD-CSAT.git'
$origem = (Get-Location).Path
if (-not (Test-Path (Join-Path $origem 'main.py'))) { throw 'Abra a pasta do projeto (main.py) antes de executar' }
$destino = Join-Path ([System.IO.Path]::GetTempPath()) 'JT-Qualidade-Publicacao'
if (Test-Path $destino) { throw "A pasta temporaria ja existe: $destino. Renomeie ou remova antes de executar de novo." }
Write-Host 'Clonando repositorio...' -ForegroundColor Cyan
git clone $repo $destino
if ($LASTEXITCODE -ne 0) { throw 'Falha ao clonar o repositorio' }
Get-ChildItem -LiteralPath $origem -Force | Where-Object {
    $_.Name -notin @('dados', '.env', '.venv', '.git', '__pycache__')
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $destino -Recurse -Force
}
Write-Host 'Arquivos que serao enviados:' -ForegroundColor Cyan
git -C $destino status --short
git -C $destino add .
$arquivos = @(git -C $destino diff --cached --name-only)
if ($arquivos | Where-Object { $_ -match '(^|/)(dados/|\.env$)|\.(sqlite3|xlsx|xls|csv)$' }) {
    git -C $destino reset
    throw 'Arquivo sensivel detectado. Push cancelado.'
}
if (-not $arquivos.Count) { Write-Host 'Nenhuma alteracao pendente.'; exit 0 }
git -C $destino commit -m 'feat: publicar painel de qualidade 1BD 5CD CSAT'
if ($LASTEXITCODE -ne 0) { throw 'Falha no commit. Configure git config user.name e user.email.' }
git -C $destino push origin main
if ($LASTEXITCODE -ne 0) { throw 'Falha no push; confira a autenticacao no GitHub.' }
Write-Host 'Concluido! Repositorio atualizado: https://github.com/ErisonNeto/J-T--1BD-5CD-CSAT' -ForegroundColor Green
