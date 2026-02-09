#!/bin/bash
# Initialize the RDS PostgreSQL database with the Monteclaude schema.
# Run once after terraform apply, from a machine that can reach RDS
# (e.g., via SSM session on one of the EC2 instances).
#
# Usage:
#   export DATABASE_URL="postgresql://user:pass@host:5432/monteclaude"
#   ./init-db.sh
#
# Or provide the connection string as an argument:
#   ./init-db.sh "postgresql://user:pass@host:5432/monteclaude"

set -euo pipefail

DB_URL="${1:-${DATABASE_URL:-}}"

if [ -z "$DB_URL" ]; then
  echo "ERROR: Provide DATABASE_URL env var or pass connection string as argument"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/../../packages/server/db/init.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "ERROR: Schema file not found: $SCHEMA_FILE"
  exit 1
fi

echo "Applying schema to database..."
psql "$DB_URL" -f "$SCHEMA_FILE"
echo "Done. Schema applied successfully."
