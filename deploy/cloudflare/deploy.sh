#!/usr/bin/env bash
# Publicación manual, sin pasar por GitHub.
# Requiere: npx (Node) y CLOUDFLARE_API_TOKEN en el entorno.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/3 Construyendo datos…"
python3 scripts/build.py

echo "2/3 Verificando frescura…"
python3 scripts/check_frescura.py

echo "3/3 Publicando en Cloudflare Pages…"
npx --yes wrangler pages deploy public --project-name=nino-peru
