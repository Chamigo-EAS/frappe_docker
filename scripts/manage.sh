#!/usr/bin/env bash
set -euo pipefail

# ── Paths 
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GITOPS_DIR="$BASE_DIR/gitops"
OVERRIDES_DIR="$BASE_DIR/overrides"

mkdir -p "$GITOPS_DIR"

# ── Colores 
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

log()   { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── ENV 
load_env() {
    local file="$1"
    [[ -f "$file" ]] || error "No existe $file"

    set -a
    source "$file"
    set +a
}

# ── Docker Compose 
bench_compose() {
    local env="$1"
    local env_file="$GITOPS_DIR/${env}.env"

    load_env "$env_file"

    : "${ERPNEXT_VERSION:?Falta ERPNEXT_VERSION}"
    : "${SITES_RULE:?Falta SITES_RULE}"

    COMPOSE_CMD=(
        docker compose
        --project-name "$env"
        --env-file "$env_file"
        -f "$BASE_DIR/compose.yaml"
        -f "$OVERRIDES_DIR/compose.redis.yaml"
        -f "$OVERRIDES_DIR/compose.multi-bench.yaml"
    )
}

compose_exec() {
    local env="$1"; shift
    bench_compose "$env"
    "${COMPOSE_CMD[@]}" exec "$@"
}

compose_run() {
    local env="$1"; shift
    bench_compose "$env"
    "${COMPOSE_CMD[@]}" "$@"
}

# ── WAIT HELPERS
wait_for_tcp() {
    local host="$1"
    local port="$2"
    local retries=30

    log "Esperando $host:$port ..."

    for i in $(seq 1 $retries); do
        if nc -z "$host" "$port" >/dev/null 2>&1; then
            ok "$host:$port listo"
            return 0
        fi
        sleep 2
    done

    error "Timeout esperando $host:$port"
}

wait_for_backend() {
    local env="$1"

    log "Esperando backend..."

    for i in {1..30}; do
        if compose_exec "$env" backend ls >/dev/null 2>&1; then
            ok "Backend listo"
            return 0
        fi
        sleep 2
    done

    error "Backend no responde"
}

# ── SITE HELPERS 
site_exists() {
    local env="$1"
    local site="$2"

    compose_exec "$env" backend \
        test -d "/home/frappe/frappe-bench/sites/$site"
}

# ── Infra 
infra_up() {
    log "Infra up..."

    local infra_env="$GITOPS_DIR/infra.env"

    [[ -f "$infra_env" ]] || cat > "$infra_env" <<EOF
DB_ROOT_PASSWORD=root
ERPNEXT_VERSION=version-15
SITES_RULE=erp.local
EOF

    docker compose -p mariadb \
        --env-file "$infra_env" \
        -f "$OVERRIDES_DIR/compose.mariadb-shared.yaml" \
        up -d

    ok "Infra lista"
}

# ── Bench 
bench_up() {
    local env="${1:?Falta env}"

    log "Bench up $env"

    compose_run "$env" up -d

    wait_for_backend "$env"
}


bench_down() {
    local env_name="${1:?Especifica el nombre del env}"

    warn "Bajando bench: ${env_name}..."

    compose_run "$env_name" down

    ok "Bench '${env_name}' bajado "
}

# ── Site 
new_site() {
    local env="${1:?Falta env}"
    local site="${2:?Falta site}"
    local admin="${3:?Falta password}"

    load_env "$GITOPS_DIR/infra.env"
    local db_root="${DB_ROOT_PASSWORD:-root}"

    wait_for_backend "$env"

    if site_exists "$env" "$site"; then
        warn "Site $site ya existe — skip"
        return 0
    fi

    log "Creando site $site..."
    log "env : $env"
    log "root : $db_root"

    export  MYSQL_PWD=$db_root

    compose_exec "$env" backend \
        bench new-site "$site" \
        --mariadb-root-password "$db_root" \
        --admin-password "$admin" \
        --db-name "${site//./_}" \
        --no-mariadb-socket

    ok "Site creado"
}

install_app() {
    local env="${1:?}"
    local site="${2:?}"
    local app="${3:?}"

    wait_for_backend "$env"

    if compose_exec "$env" backend \
        bench --site "$site" list-apps | grep -q "$app"; then
        warn "$app ya instalado"
        return 0
    fi

    compose_exec "$env" backend \
        bench --site "$site" install-app "$app"
}

# ── CLI 
case "${1:-}" in
    infra-up)     infra_up ;;
    bench-up)     bench_up "${2:-}" ;;
    bench-down)     bench_down "${2:-}" ;;
    new-site)     new_site "${2:-}" "${3:-}" "${4:-}" ;;
    install-app)  install_app "${2:-}" "${3:-}" "${4:-}" ;;
    *)
        echo "Uso: $0 infra-up | bench-up <env> | bench-down <env> | new-site <env> <site> <pass>"
        ;;
esac
