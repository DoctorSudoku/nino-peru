#!/usr/bin/env bash
# Publica: reconstruye, verifica y dispara el despliegue en GitHub Actions.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/3 Construyendo datos…"
python3 scripts/build.py

echo "2/3 Verificando frescura…"
python3 scripts/check_frescura.py

echo "3/3 Disparando el despliegue…"
if command -v gh >/dev/null 2>&1; then
  gh workflow run publicar.yml
  echo "Listo. Sigue el avance en: gh run watch"
else
  echo "Sin 'gh'. Publica desde GitHub → Actions → 'Actualizar datos y publicar'."
fi
