#!/usr/bin/env bash
set -Eeuo pipefail

CONTAINER="${CONTAINER:-postgres-db}"
DB_USER="${DB_USER:-admin}"
SQL_FILE="${SQL_FILE:-$(dirname "${BASH_SOURCE[0]}")/utils/init.sql}"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "Erro: arquivo SQL não encontrado: $SQL_FILE"
  exit 1
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Erro: container $CONTAINER não existe."
  exit 1
fi

if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" != "true" ]]; then
  echo "Erro: container $CONTAINER não está rodando."
  exit 1
fi

echo "Aguardando o PostgreSQL..."
for i in {1..30}; do
  if docker exec "$CONTAINER" pg_isready -q -U "$DB_USER" -d postgres; then
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "Erro: PostgreSQL não respondeu em 30 s."
    exit 1
  fi
  sleep 1
done

echo "Executando $SQL_FILE..."
docker exec -i "$CONTAINER" \
  psql -X -v ON_ERROR_STOP=1 -U "$DB_USER" -d postgres < "$SQL_FILE"

echo "Concluído! Banco bikesafe criado/atualizado."