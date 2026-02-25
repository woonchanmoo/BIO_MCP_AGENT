#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SERVERS=(
  "servers/Ensembl-MCP-Server-main"
  "servers/PDB-MCP-Server-main"
  "servers/PubMed-MCP-Server-main"
)

for server in "${SERVERS[@]}"; do
  echo "========================================"
  echo "Building ${server}"
  echo "========================================"
  cd "${ROOT_DIR}/${server}"
  npm install
  npm run build
  echo
done

echo "All bundled MCP Node servers are built successfully."