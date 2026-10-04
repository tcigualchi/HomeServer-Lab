#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null || { echo 'Python 3 é obrigatório'; exit 1; }
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
mkdir -p data logs backups config
[[ -f .env ]] || cp .env.example .env
alembic upgrade head
echo 'Instalação concluída. Execute: source .venv/bin/activate && python scripts/create_admin.py'
echo 'Depois: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000'
