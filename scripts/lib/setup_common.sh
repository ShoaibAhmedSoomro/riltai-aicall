#!/usr/bin/env bash

SOCIAL_CANGAROO_DEPLOY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOCIAL_CANGAROO_DEPLOY_REPO_ROOT="$(cd "$SOCIAL_CANGAROO_DEPLOY_LIB_DIR/../.." 2>/dev/null && pwd || true)"

: "${RED:=\033[0;31m}"
: "${GREEN:=\033[0;32m}"
: "${YELLOW:=\033[1;33m}"
: "${BLUE:=\033[0;34m}"
: "${NC:=\033[0m}"

social_cangaroo_info() {
    echo -e "${BLUE}$*${NC}"
}

social_cangaroo_success() {
    echo -e "${GREEN}$*${NC}"
}

social_cangaroo_warn() {
    echo -e "${YELLOW}$*${NC}"
}

social_cangaroo_fail() {
    echo -e "${RED}Error: $*${NC}" >&2
    exit 1
}

social_cangaroo_project_dir() {
    if [[ -n "${SOCIAL_CANGAROO_DEPLOY_PROJECT_DIR:-}" ]]; then
        printf '%s\n' "$SOCIAL_CANGAROO_DEPLOY_PROJECT_DIR"
    else
        pwd
    fi
}

social_cangaroo_template_path() {
    local template_name=$1
    local candidate=""
    local project_dir

    project_dir="$(social_cangaroo_project_dir)"

    for candidate in \
        "$project_dir/deploy/templates/$template_name" \
        "$SOCIAL_CANGAROO_DEPLOY_REPO_ROOT/deploy/templates/$template_name"
    do
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    social_cangaroo_fail "Template '$template_name' not found"
}

social_cangaroo_init_script_path() {
    local candidate=""
    local project_dir

    project_dir="$(social_cangaroo_project_dir)"

    for candidate in \
        "$project_dir/scripts/run_social_cangaroo_init.sh" \
        "$SOCIAL_CANGAROO_DEPLOY_REPO_ROOT/scripts/run_social_cangaroo_init.sh"
    do
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    social_cangaroo_fail "run_social_cangaroo_init.sh not found"
}

social_cangaroo_load_env_file() {
    local env_file=${1:-.env}

    [[ -f "$env_file" ]] || social_cangaroo_fail "$env_file not found"

    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
}

social_cangaroo_host_from_url() {
    local url=$1

    url="${url#https://}"
    url="${url#http://}"
    url="${url%%/*}"

    printf '%s\n' "$url"
}

social_cangaroo_is_ipv4() {
    [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

social_cangaroo_is_local_ipv4() {
    local ip=$1
    local o1 o2 o3 o4 octet

    social_cangaroo_is_ipv4 "$ip" || return 1
    IFS=. read -r o1 o2 o3 o4 <<< "$ip"

    for octet in "$o1" "$o2" "$o3" "$o4"; do
        [[ "$octet" =~ ^[0-9]+$ ]] || return 1
        (( octet >= 0 && octet <= 255 )) || return 1
    done

    (( o1 == 10 )) && return 0
    (( o1 == 127 )) && return 0
    (( o1 == 169 && o2 == 254 )) && return 0
    (( o1 == 172 && o2 >= 16 && o2 <= 31 )) && return 0
    (( o1 == 192 && o2 == 168 )) && return 0
    (( o1 == 100 && o2 >= 64 && o2 <= 127 )) && return 0

    return 1
}

social_cangaroo_infer_server_ip() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}
    local turn_conf="$project_dir/turnserver.conf"
    local ip=""

    if [[ -n "${SERVER_IP:-}" ]]; then
        printf '%s\n' "$SERVER_IP"
        return 0
    fi

    if [[ -f "$turn_conf" ]]; then
        ip="$(sed -n 's/^external-ip=//p' "$turn_conf" | head -1)"
        if [[ -n "$ip" ]]; then
            printf '%s\n' "$ip"
            return 0
        fi
    fi

    if [[ -n "${TURN_HOST:-}" ]] && social_cangaroo_is_ipv4 "$TURN_HOST"; then
        printf '%s\n' "$TURN_HOST"
        return 0
    fi

    if [[ -n "${PUBLIC_HOST:-}" ]] && social_cangaroo_is_ipv4 "$PUBLIC_HOST"; then
        printf '%s\n' "$PUBLIC_HOST"
        return 0
    fi

    return 1
}

social_cangaroo_infer_public_base_url() {
    if [[ -n "${PUBLIC_BASE_URL:-}" ]]; then
        printf '%s\n' "${PUBLIC_BASE_URL%/}"
        return 0
    fi

    if [[ -n "${BACKEND_API_ENDPOINT:-}" ]]; then
        printf '%s\n' "${BACKEND_API_ENDPOINT%/}"
        return 0
    fi

    if [[ -n "${PUBLIC_HOST:-}" ]]; then
        printf 'https://%s\n' "$PUBLIC_HOST"
        return 0
    fi

    if [[ -n "${SERVER_IP:-}" ]]; then
        printf 'https://%s\n' "$SERVER_IP"
        return 0
    fi

    return 1
}

social_cangaroo_infer_public_host() {
    local public_base_url=""

    if [[ -n "${PUBLIC_HOST:-}" ]]; then
        printf '%s\n' "$PUBLIC_HOST"
        return 0
    fi

    public_base_url="$(social_cangaroo_infer_public_base_url 2>/dev/null || true)"
    if [[ -n "$public_base_url" ]]; then
        social_cangaroo_host_from_url "$public_base_url"
        return 0
    fi

    if [[ -n "${TURN_HOST:-}" ]]; then
        printf '%s\n' "$TURN_HOST"
        return 0
    fi

    return 1
}

social_cangaroo_set_env_key() {
    local env_file=$1
    local key=$2
    local value=$3
    local tmp_file="${env_file}.tmp.$$"

    awk -v key="$key" -v value="$value" '
        BEGIN { updated = 0 }
        $0 ~ "^" key "=" {
            print key "=" value
            updated = 1
            next
        }
        { print }
        END {
            if (!updated) {
                print key "=" value
            }
        }
    ' "$env_file" > "$tmp_file"

    mv "$tmp_file" "$env_file"
}

social_cangaroo_delete_env_key() {
    local env_file=$1
    local key=$2
    local tmp_file="${env_file}.tmp.$$"

    awk -v key="$key" '$0 !~ "^" key "=" { print }' "$env_file" > "$tmp_file"
    mv "$tmp_file" "$env_file"
}

social_cangaroo_sync_remote_env_file() {
    local env_file=${1:-.env}
    local project_dir
    local public_base_url=""
    local public_host=""
    local server_ip=""

    project_dir="$(cd "$(dirname "$env_file")" && pwd)"
    social_cangaroo_load_env_file "$env_file"

    public_base_url="$(social_cangaroo_infer_public_base_url)" || social_cangaroo_fail "Could not determine PUBLIC_BASE_URL"
    public_base_url="${public_base_url%/}"
    public_host="$(social_cangaroo_infer_public_host)" || social_cangaroo_fail "Could not determine PUBLIC_HOST"
    server_ip="$(social_cangaroo_infer_server_ip "$project_dir")" || social_cangaroo_fail "Could not determine SERVER_IP"

    [[ "$public_base_url" =~ ^https?:// ]] || social_cangaroo_fail "PUBLIC_BASE_URL must include http:// or https://"
    social_cangaroo_is_ipv4 "$server_ip" || social_cangaroo_fail "SERVER_IP must be an IPv4 address (got: $server_ip)"

    social_cangaroo_set_env_key "$env_file" ENVIRONMENT "${ENVIRONMENT:-production}"
    social_cangaroo_set_env_key "$env_file" SERVER_IP "$server_ip"
    social_cangaroo_set_env_key "$env_file" PUBLIC_HOST "$public_host"
    social_cangaroo_set_env_key "$env_file" PUBLIC_BASE_URL "$public_base_url"

    # Remote installs always run coturn (the "remote" compose profile). The API
    # reports this flag to browsers, which skip TURN entirely when it is false,
    # so sync it here for installs whose .env predates the key.
    social_cangaroo_set_env_key "$env_file" ENABLE_COTURN true

    # BACKEND_API_ENDPOINT / MINIO_PUBLIC_ENDPOINT / TURN_HOST are derived in-app
    # from PUBLIC_BASE_URL / PUBLIC_HOST (see api/constants.py), so sync neither
    # writes nor removes them: new installs simply omit them, and any value an
    # operator set by hand is left untouched as an explicit override.
}

social_cangaroo_validate_remote_runtime_env() {
    [[ "${FASTAPI_WORKERS:-}" =~ ^[1-9][0-9]*$ ]] || social_cangaroo_fail "FASTAPI_WORKERS must be a positive integer"
    [[ -n "${TURN_SECRET:-}" ]] || social_cangaroo_fail "TURN_SECRET is missing"
    [[ -n "${PUBLIC_HOST:-}" ]] || social_cangaroo_fail "PUBLIC_HOST is missing"
    [[ -n "${PUBLIC_BASE_URL:-}" ]] || social_cangaroo_fail "PUBLIC_BASE_URL is missing"
    social_cangaroo_is_ipv4 "${SERVER_IP:-}" || social_cangaroo_fail "SERVER_IP must be a valid IPv4 address"
    [[ "${PUBLIC_BASE_URL}" =~ ^https?:// ]] || social_cangaroo_fail "PUBLIC_BASE_URL must include http:// or https://"
    # BACKEND_API_ENDPOINT / MINIO_PUBLIC_ENDPOINT / TURN_HOST are derived in-app
    # from PUBLIC_BASE_URL / PUBLIC_HOST (see api/constants.py), so they are not
    # required here. When an operator sets them explicitly (split deployment),
    # their value is honored as-is — no equality check.
}

social_cangaroo_uses_init_compose_layout() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}
    local compose_file="$project_dir/docker-compose.yaml"

    [[ -f "$compose_file" ]] || return 1
    grep -q "social-cangaroo-init:" "$compose_file" \
        && grep -q "nginx-generated:/etc/nginx/conf.d:ro" "$compose_file" \
        && grep -q "coturn-generated:/etc/coturn:ro" "$compose_file"
}

social_cangaroo_require_init_compose_layout() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}

    if ! social_cangaroo_uses_init_compose_layout "$project_dir"; then
        social_cangaroo_fail "This install uses the legacy remote compose layout. Run ./update_remote.sh first so Docker uses social-cangaroo-init generated config."
    fi
}

social_cangaroo_render_remote_nginx_conf() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}
    local destination=${2:-"$project_dir/nginx.conf"}
    local template=""
    local tmp_upstream=""

    template="$(social_cangaroo_template_path "nginx.remote.conf.template")"
    tmp_upstream="$(mktemp)"

    {
        echo "# Backend API workers - one uvicorn process per port, balanced by least_conn."
        echo "# Auto-generated by Social Cangaroo remote config renderer. Do not edit manually."
        echo "upstream social_cangaroo_api {"
        echo "    least_conn;"
        for ((i=0; i<FASTAPI_WORKERS; i++)); do
            printf '    server api:%d max_fails=3 fail_timeout=10s;\n' "$((8000 + i))"
        done
        echo "    keepalive 32;"
        echo "}"
    } > "$tmp_upstream"

    awk -v public_host="$PUBLIC_HOST" -v upstream_file="$tmp_upstream" '
        BEGIN {
            while ((getline line < upstream_file) > 0) {
                upstream = upstream line ORS
            }
            close(upstream_file)
        }
        {
            gsub(/__SOCIAL_CANGAROO_PUBLIC_HOST__/, public_host)
            if ($0 == "__SOCIAL_CANGAROO_UPSTREAM_BLOCK__") {
                printf "%s", upstream
            } else {
                print
            }
        }
    ' "$template" > "$destination"

    rm -f "$tmp_upstream"
}

social_cangaroo_render_remote_turn_conf() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}
    local destination=${2:-"$project_dir/turnserver.conf"}
    local template=""
    local external_ip="${TURN_EXTERNAL_IP:-${SERVER_IP:-}}"

    template="$(social_cangaroo_template_path "turnserver.remote.conf.template")"
    [[ -n "$external_ip" ]] || social_cangaroo_fail "TURN external IP/host is missing"

    awk \
        -v external_ip="$external_ip" \
        -v turn_secret="$TURN_SECRET" \
        '
        {
            gsub(/__SOCIAL_CANGAROO_TURN_EXTERNAL_IP__/, external_ip)
            gsub(/__SOCIAL_CANGAROO_TURN_SECRET__/, turn_secret)
            print
        }
    ' "$template" > "$destination"
}

social_cangaroo_preflight_remote_init_render() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}
    local env_file="$project_dir/.env"
    local cert_dir="$project_dir/certs"
    local init_script=""
    local tmp_root=""
    local nginx_conf=""
    local turn_conf=""
    local nginx_workers=0
    local rendered_secret=""
    local rendered_ip=""
    local rendered_server_name=""

    social_cangaroo_load_env_file "$env_file"
    social_cangaroo_validate_remote_runtime_env
    [[ -f "$cert_dir/local.crt" ]] || social_cangaroo_fail "certs/local.crt not found"
    [[ -f "$cert_dir/local.key" ]] || social_cangaroo_fail "certs/local.key not found"

    init_script="$(social_cangaroo_init_script_path)"
    tmp_root="$(mktemp -d)"
    nginx_conf="$tmp_root/nginx/default.conf"
    turn_conf="$tmp_root/coturn/turnserver.conf"

    (
        export ENVIRONMENT SERVER_IP PUBLIC_HOST PUBLIC_BASE_URL BACKEND_API_ENDPOINT MINIO_PUBLIC_ENDPOINT TURN_HOST TURN_SECRET FASTAPI_WORKERS
        export SOCIAL_CANGAROO_INIT_WORKSPACE_DIR="$project_dir"
        export SOCIAL_CANGAROO_INIT_OUTPUT_ROOT="$tmp_root"
        export SOCIAL_CANGAROO_INIT_CERTS_DIR="$cert_dir"
        bash "$init_script" >/dev/null
    )

    [[ -f "$nginx_conf" ]] || social_cangaroo_fail "social-cangaroo-init did not render nginx config"
    [[ -f "$turn_conf" ]] || social_cangaroo_fail "social-cangaroo-init did not render coturn config"

    nginx_workers=$(awk '/^[[:space:]]*server api:[0-9]+/ { count += 1 } END { print count + 0 }' "$nginx_conf")
    [[ "$nginx_workers" -eq "$FASTAPI_WORKERS" ]] || social_cangaroo_fail "FASTAPI_WORKERS=$FASTAPI_WORKERS but nginx.conf has $nginx_workers upstream servers"

    rendered_server_name="$(awk '/^[[:space:]]*server_name / { print $2; exit }' "$nginx_conf" | sed 's/;$//')"
    [[ "$rendered_server_name" == "$PUBLIC_HOST" ]] || social_cangaroo_fail "nginx.conf server_name ($rendered_server_name) does not match PUBLIC_HOST ($PUBLIC_HOST)"

    rendered_secret="$(sed -n 's/^static-auth-secret=//p' "$turn_conf" | head -1)"
    [[ "$rendered_secret" == "$TURN_SECRET" ]] || social_cangaroo_fail "TURN_SECRET in .env does not match turnserver.conf"

    rendered_ip="$(sed -n 's/^external-ip=//p' "$turn_conf" | head -1)"
    [[ "$rendered_ip" == "$SERVER_IP" ]] || social_cangaroo_fail "SERVER_IP in .env does not match turnserver.conf"

    rm -rf "$tmp_root"
}

# Reconcile the running Postgres role password with POSTGRES_PASSWORD in .env.
#
# POSTGRES_PASSWORD only takes effect when the postgres data volume is first
# initialized. If the volume was created before .env had a generated password
# (e.g. an early start used the compose fallback `:-postgres`), or the password
# was later rotated, the role keeps its old password while the API connects with
# the .env value over TCP (pg_hba `scram-sha-256`) and dies with "password
# authentication failed for user postgres". start_docker.sh handles this for the
# OSS quickstart; the remote path (remote_up.sh) needs the same reconciliation.
#
# Bring postgres up on its own, then ALTER the role over the trusted local
# socket (pg_hba trusts `local`, so this works even when the password is
# currently mismatched). Idempotent: on a fresh volume it just re-sets the same
# value. Survives the later `--force-recreate` because the password lives in the
# data volume, not the container.
social_cangaroo_sync_postgres_password() {
    local project_dir=$1
    shift
    local compose=("$@")
    local env_file="$project_dir/.env"
    local password=""
    local ready=""
    local i

    [[ ${#compose[@]} -gt 0 ]] || compose=(docker compose)

    if [[ -f "$env_file" ]]; then
        password="$(awk -F= '/^POSTGRES_PASSWORD=/{sub(/^POSTGRES_PASSWORD=/, ""); print; exit}' "$env_file")"
    fi

    # No explicit password: the compose fallback (`:-postgres`) governs both the
    # DB init and the API's DATABASE_URL, so the two already agree — nothing to do.
    [[ -n "$password" ]] || return 0

    social_cangaroo_info "Syncing Postgres password from .env..."
    ( cd "$project_dir" && "${compose[@]}" up -d postgres ) >/dev/null

    for ((i = 0; i < 30; i++)); do
        if ( cd "$project_dir" && "${compose[@]}" exec -T postgres pg_isready -U postgres ) >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 1
    done
    [[ -n "$ready" ]] || social_cangaroo_fail "Postgres did not become ready while syncing POSTGRES_PASSWORD."

    printf '%s\n' "ALTER USER postgres WITH PASSWORD :'pw';" \
        | ( cd "$project_dir" && "${compose[@]}" exec -T postgres \
              psql -U postgres -d postgres -v ON_ERROR_STOP=1 -v "pw=$password" ) >/dev/null \
        || social_cangaroo_fail "Failed to sync Postgres password from .env."
    social_cangaroo_success "✓ Postgres password synced with .env"
}

social_cangaroo_prepare_remote_install() {
    local project_dir=${1:-$(social_cangaroo_project_dir)}
    local env_file="$project_dir/.env"

    social_cangaroo_sync_remote_env_file "$env_file"
    social_cangaroo_require_init_compose_layout "$project_dir"
    social_cangaroo_preflight_remote_init_render "$project_dir"
}

# ---------------------------------------------------------------------------
# TLS certificate helpers (self-signed bootstrap + Let's Encrypt via webroot)
# ---------------------------------------------------------------------------

# Map an IPv4 address to a public sslip.io / nip.io hostname, e.g.
# 203.0.113.10 -> 203-0-113-10.sslip.io. The hostname resolves back to the
# embedded IP from any public resolver, so Let's Encrypt can validate it over
# the HTTP-01 challenge without the operator owning a domain. Public IPs only:
# Let's Encrypt refuses to validate private/reserved addresses.
social_cangaroo_sslip_host_from_ip() {
    local ip=$1
    local suffix=${2:-sslip.io}

    social_cangaroo_is_ipv4 "$ip" || social_cangaroo_fail "social_cangaroo_sslip_host_from_ip: '$ip' is not an IPv4 address"
    printf '%s.%s\n' "${ip//./-}" "$suffix"
}

# Install certbot via the host package manager if it is not already present.
# Returns non-zero (instead of exiting) when no supported package manager is
# found or the install fails, so callers can fall back to a self-signed cert.
social_cangaroo_install_certbot() {
    if command -v certbot >/dev/null 2>&1; then
        return 0
    fi

    social_cangaroo_info "Installing Certbot..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y -qq certbot
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y -q certbot
    elif command -v yum >/dev/null 2>&1; then
        yum install -y -q certbot
    else
        social_cangaroo_warn "Could not detect a package manager (apt/dnf/yum) to install certbot."
        return 1
    fi
}

# Obtain (or renew) a Let's Encrypt certificate for $host using the webroot
# challenge served by the running nginx container out of <project>/certs, then
# copy the issued cert to certs/local.{crt,key} (the files nginx reads). This
# needs nginx already running and serving /.well-known/acme-challenge/ on :80.
# Returns non-zero on failure so callers can keep the self-signed cert.
social_cangaroo_issue_letsencrypt_webroot() {
    local project_dir=$1
    local host=$2
    local email=${3:-}
    local webroot="$project_dir/certs"
    local live_dir="/etc/letsencrypt/live/$host"
    local -a email_args

    if [[ -n "$email" ]]; then
        email_args=(--email "$email")
    else
        email_args=(--register-unsafely-without-email)
    fi

    mkdir -p "$webroot/.well-known/acme-challenge"

    certbot certonly --webroot -w "$webroot" \
        --non-interactive --agree-tos --keep-until-expiring \
        "${email_args[@]}" \
        -d "$host" || return 1

    [[ -f "$live_dir/fullchain.pem" && -f "$live_dir/privkey.pem" ]] || return 1

    cp "$live_dir/fullchain.pem" "$webroot/local.crt"
    cp "$live_dir/privkey.pem" "$webroot/local.key"
    chmod 644 "$webroot/local.crt" "$webroot/local.key"
}

# Install a certbot deploy hook so renewed certificates are copied into
# <project>/certs and nginx is restarted to load them. Renewal itself is driven
# by certbot's packaged systemd timer / cron; webroot renewals need no downtime
# because the running nginx serves the challenge.
social_cangaroo_install_cert_renewal_hook() {
    local project_dir=$1
    local host=$2
    local hook_dir="/etc/letsencrypt/renewal-hooks/deploy"
    local hook_path="$hook_dir/social-cangaroo-reload.sh"

    mkdir -p "$hook_dir"

    cat > "$hook_path" << HOOK_EOF
#!/bin/bash
cp /etc/letsencrypt/live/$host/fullchain.pem $project_dir/certs/local.crt
cp /etc/letsencrypt/live/$host/privkey.pem $project_dir/certs/local.key
chmod 644 $project_dir/certs/local.crt $project_dir/certs/local.key

cd $project_dir
docker compose --profile remote restart nginx 2>/dev/null || true
HOOK_EOF
    chmod +x "$hook_path"
}

social_cangaroo_download_bundle_file_for_ref() {
    local destination=$1
    local remote_path=$2
    local ref=${3:-main}
    local raw_base="https://raw.githubusercontent.com/ShoaibAhmedSoomro/social-cangaroo/$ref"
    local fallback_base="https://raw.githubusercontent.com/ShoaibAhmedSoomro/social-cangaroo/main"

    if ! curl -fsSL -o "$destination" "$raw_base/$remote_path"; then
        social_cangaroo_warn "Warning: '$remote_path' not found at '$ref' - falling back to main"
        curl -fsSL -o "$destination" "$fallback_base/$remote_path"
    fi
}

social_cangaroo_download_init_support_bundle() {
    local project_dir=$1
    local ref=${2:-main}

    mkdir -p "$project_dir/scripts/lib" "$project_dir/deploy/templates"

    mkdir -p "$project_dir/scripts"
    social_cangaroo_download_bundle_file_for_ref "$project_dir/scripts/lib/setup_common.sh" "scripts/lib/setup_common.sh" "$ref"
    social_cangaroo_download_bundle_file_for_ref "$project_dir/scripts/run_social_cangaroo_init.sh" "scripts/run_social_cangaroo_init.sh" "$ref"
    chmod +x "$project_dir/scripts/run_social_cangaroo_init.sh"
    social_cangaroo_download_bundle_file_for_ref "$project_dir/deploy/templates/nginx.remote.conf.template" "deploy/templates/nginx.remote.conf.template" "$ref"
    social_cangaroo_download_bundle_file_for_ref "$project_dir/deploy/templates/turnserver.remote.conf.template" "deploy/templates/turnserver.remote.conf.template" "$ref"
}

social_cangaroo_download_remote_support_bundle() {
    local project_dir=$1
    local ref=${2:-main}

    social_cangaroo_download_bundle_file_for_ref "$project_dir/remote_up.sh" "remote_up.sh" "$ref"
    chmod +x "$project_dir/remote_up.sh"
    social_cangaroo_download_init_support_bundle "$project_dir" "$ref"
}
