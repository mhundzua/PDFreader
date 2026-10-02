#!/bin/bash
# Kvīšu kārtotājs: palaišana ar dubultklikšķi (macOS).
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; sys.exit(0 if (3, 9) <= sys.version_info[:2] < (3, 13) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Nav atrasts piemērots Python (vajag 3.9 - 3.12)."
  echo "Instalējiet to ar:  brew install python@3.12"
  read -r -p "Spiediet Enter, lai aizvērtu..."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Pirmā palaišana: sagatavoju vidi (tas aizņem dažas minūtes)..."
  "$PY" -m venv .venv || exit 1
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  if ! .venv/bin/python -m pip install -r requirements.txt; then
    read -r -p "Instalēšana neizdevās. Spiediet Enter, lai aizvērtu..."
    exit 1
  fi
  touch .venv/.installed
fi

exec .venv/bin/python -m kartotajs "$@"
