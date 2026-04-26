# =============================================================================
# Containerfile — Imagen custom de ERPNext desde fork
# Basado en images/production/Containerfile (enfoque correcto multi-stage)
#
# BUILD:
#   # Paso 1: generar apps.json con erpnext (o apps adicionales)
#   export APPS_JSON_BASE64=$(base64 -w 0 apps/apps.json)
#
#   # Paso 2: construir imagen
#   docker build \
#     --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
#     --build-arg=FRAPPE_BRANCH=version-16 \
#     --build-arg=ERPNEXT_REPO=https://github.com/frappe/erpnext \
#     --build-arg=ERPNEXT_BRANCH=version-16 \
#     --tag=192.168.10.86:8083/chamigo/erpnext-custom:v16 \
#     --file=Containerfile \
#     .
#
# NOTA: Para agregar apps propias en el futuro, descomentar la sección
#       APPS_JSON_BASE64 y usar apps/apps.json con las apps adicionales.
# =============================================================================

ARG PYTHON_VERSION=3.14
ARG DEBIAN_BASE=bookworm

# ─── STAGE BASE
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_BASE} AS base

ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ARG WKHTMLTOPDF_DISTRO=bookworm
ARG NODE_VERSION=24.0.0
ENV NVM_DIR=/home/frappe/.nvm
ENV PATH=${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/:${PATH}

# Copiar archivos nginx antes del RUN para mejor cache
COPY resources/core/nginx/nginx-template.conf    /templates/nginx/frappe.conf.template
COPY resources/core/nginx/nginx-entrypoint.sh    /usr/local/bin/nginx-entrypoint.sh
COPY resources/core/nginx/security_headers.conf  /etc/nginx/snippets/security_headers.conf

RUN useradd -ms /bin/bash frappe \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        curl git vim nginx gettext-base file \
        # weasyprint
        libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libpangocairo-1.0-0 \
        # Chromium headless para PDF/print
        chromium-headless-shell \
        # Backups
        restic gpg \
        # MariaDB client
        mariadb-client less \
        # Postgres client
        libpq-dev postgresql-client \
        # Utilidades
        wait-for-it jq media-types \
    # ── Node via NVM 
    && mkdir -p ${NVM_DIR} \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.5/install.sh | bash \
    && . ${NVM_DIR}/nvm.sh \
    && nvm install ${NODE_VERSION} \
    && nvm use v${NODE_VERSION} \
    && npm install -g yarn \
    && nvm alias default v${NODE_VERSION} \
    && rm -rf ${NVM_DIR}/.cache \
    && echo 'export NVM_DIR="/home/frappe/.nvm"' >>/home/frappe/.bashrc \
    && echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >>/home/frappe/.bashrc \
    # ── wkhtmltopdf ───────────────────────────────────────────────────────────
    && if [ "$(uname -m)" = "aarch64" ]; then export ARCH=arm64; fi \
    && if [ "$(uname -m)" = "x86_64"  ]; then export ARCH=amd64; fi \
    && downloaded_file=wkhtmltox_${WKHTMLTOPDF_VERSION}.${WKHTMLTOPDF_DISTRO}_${ARCH}.deb \
    && curl -sLO https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/${downloaded_file} \
    && apt-get install -y ./${downloaded_file} \
    && rm ${downloaded_file} \
    # ── Cleanup y permisos nginx ──────────────────────────────────────────────
    && rm -rf /var/lib/apt/lists/* \
    && rm -fr /etc/nginx/sites-enabled/default \
    && mkdir -p /etc/nginx/snippets \
    && pip3 install frappe-bench \
    && sed -i '/user www-data/d' /etc/nginx/nginx.conf \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && touch /run/nginx.pid \
    && chown -R frappe:frappe \
        /etc/nginx/conf.d \
        /etc/nginx/nginx.conf \
        /etc/nginx/snippets \
        /var/log/nginx \
        /var/lib/nginx \
        /run/nginx.pid \
    && chmod 755 /usr/local/bin/nginx-entrypoint.sh \
    && chmod 644 /templates/nginx/frappe.conf.template


# ─── STAGE BUILD-DEPS 
FROM base AS build-deps

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        wget \
        # Compilación nativa (arm64 support)
        libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev \
        # psycopg2
        libpq-dev \
        # Dependencias frappe
        libffi-dev liblcms2-dev libldap2-dev libmariadb-dev \
        libsasl2-dev libtiff5-dev libwebp-dev \
        pkg-config redis-tools rlwrap tk8.6-dev cron \
        # pandas / numpy
        gcc build-essential libbz2-dev \
    && rm -rf /var/lib/apt/lists/*

USER frappe


# ─── STAGE BUILDER: bench init + ERPNext + apps adicionales 
FROM build-deps AS builder

ARG FRAPPE_BRANCH=version-16
ARG FRAPPE_PATH=https://github.com/frappe/frappe
ARG ERPNEXT_REPO=https://github.com/frappe/erpnext
ARG ERPNEXT_BRANCH=version-16

# (Opcional) apps adicionales via apps.json — descomentar cuando sea necesario
# ARG APPS_JSON_BASE64
# RUN if [ -n "${APPS_JSON_BASE64}" ]; then \
#         mkdir -p /opt/frappe && echo "${APPS_JSON_BASE64}" | base64 -d > /opt/frappe/apps.json; \
#     fi

# Inicializar bench con frappe
RUN bench init \
      --frappe-branch=${FRAPPE_BRANCH} \
      --frappe-path=${FRAPPE_PATH} \
      --no-procfile \
      --no-backups \
      --skip-redis-config-generation \
      --verbose \
      /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# Instalar ERPNext
RUN bench get-app \
      --branch=${ERPNEXT_BRANCH} \
      --resolve-deps \
      erpnext \
      ${ERPNEXT_REPO}

# instalar apps adicionales — descomentar cuando sea necesario
# RUN if [ -f /opt/frappe/apps.json ]; then \
#         bench get-app --apps_path=/opt/frappe/apps.json; \
#     fi

# Config base vacía + limpieza .git
RUN echo "{}" > sites/common_site_config.json \
    && find apps -mindepth 1 -path "*/.git" | xargs rm -fr


# ─── STAGE FINAL (erpnext): imagen runtime 
FROM base AS erpnext

# Mensaje disuasorio en shell (evitar modificaciones en producción)
RUN echo 'echo "Contenedor de producción. Consultar docs antes de modificar."' \
      >> /home/frappe/.bashrc

USER frappe

COPY --from=builder --chown=frappe:frappe \
    /home/frappe/frappe-bench /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

VOLUME [ \
  "/home/frappe/frappe-bench/sites", \
  "/home/frappe/frappe-bench/sites/assets", \
  "/home/frappe/frappe-bench/logs" \
]

# CMD default: gunicorn (backend web)
# Los demás servicios (worker, scheduler, socketio) se definen en compose.yaml
CMD [ \
  "/home/frappe/frappe-bench/env/bin/gunicorn", \
  "--chdir=/home/frappe/frappe-bench/sites", \
  "--bind=0.0.0.0:8000", \
  "--threads=4", \
  "--workers=2", \
  "--worker-class=gthread", \
  "--worker-tmp-dir=/dev/shm", \
  "--timeout=120", \
  "--preload", \
  "frappe.app:application" \
]

LABEL org.opencontainers.image.title="Chamigo ERPNext Custom" \
      org.opencontainers.image.description="ERPNext v16 — imagen personalizada Chamigo" \
      org.opencontainers.image.version="v16"