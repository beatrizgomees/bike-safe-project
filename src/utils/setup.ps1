
$ErrorActionPreference = "Stop"

$Container = "postgres-db"
$DbName = "bikesafe"
$DbUser = "admin"
$SqlFile = Join-Path $PSScriptRoot "init.sql"

if (-not (Test-Path $SqlFile)) {
    throw "Arquivo init.sql não encontrado: $SqlFile"
}

$Running = docker inspect -f '{{.State.Running}}' $Container 2>$null

if ($LASTEXITCODE -ne 0) {
    throw "Container '$Container' não existe."
}

if ($Running -ne "true") {
    throw "Container '$Container' não está rodando."
}

Write-Host "Verificando PostgreSQL..."
docker exec $Container pg_isready -U $DbUser -d $DbName

if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL não está pronto ou não foi possível conectar."
}

Write-Host "Executando init.sql..."
Get-Content $SqlFile -Raw |
    docker exec -i $Container psql -X -v ON_ERROR_STOP=1 -U $DbUser -d $DbName

if ($LASTEXITCODE -ne 0) {
    throw "Falha ao executar init.sql."
}

Write-Host "Script executado com sucesso!"
