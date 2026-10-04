#!/usr/bin/env bash
set -euo pipefail
echo 'Este script remove apenas o ambiente virtual e unidades instaladas; banco e .env são preservados.'
rm -rf .venv
echo 'Ambiente virtual removido. Revise e remova manualmente os arquivos systemd se instalados.'
