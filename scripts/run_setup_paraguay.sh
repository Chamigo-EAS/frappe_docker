#!/usr/bin/env bash
set -e

SITE="${1:?Falta site}"
EMPRESA="${2:?Falta empresa}"
RUC="${3:?Falta RUC}"

echo "[INFO] Copiando script al contenedor..."

docker compose cp ./scripts/setup_paraguay.py backend:/tmp/setup_paraguay.py

echo "[INFO] Ejecutando configuración en ERPNext..."

docker compose exec -T backend bash -c "
cd /home/frappe/frappe-bench && \
bench --site ${SITE} console <<EOF
EMPRESA = '${EMPRESA}'
RUC = '${RUC}'
exec(open('/tmp/setup_paraguay.py').read())
EOF
"

echo "[OK] Proceso finalizado"
