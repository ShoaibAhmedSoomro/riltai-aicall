#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SOCIAL_CANGAROO_INIT_WORKSPACE_DIR:-/workspace}"
OUTPUT_ROOT="${SOCIAL_CANGAROO_INIT_OUTPUT_ROOT:-/generated}"
NGINX_OUTPUT_DIR="$OUTPUT_ROOT/nginx"
COTURN_OUTPUT_DIR="$OUTPUT_ROOT/coturn"
CERTS_DIR="${SOCIAL_CANGAROO_INIT_CERTS_DIR:-/certs}"

# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/setup_common.sh"

SOCIAL_CANGAROO_DEPLOY_PROJECT_DIR="$WORKSPACE_DIR"

mkdir -p "$NGINX_OUTPUT_DIR" "$COTURN_OUTPUT_DIR"

if [[ "${ENVIRONMENT:-local}" == "production" ]]; then
    social_cangaroo_validate_remote_runtime_env
    [[ -f "$CERTS_DIR/local.crt" ]] || social_cangaroo_fail "certs/local.crt not found"
    [[ -f "$CERTS_DIR/local.key" ]] || social_cangaroo_fail "certs/local.key not found"

    export TURN_EXTERNAL_IP="$SERVER_IP"
    social_cangaroo_render_remote_nginx_conf "$WORKSPACE_DIR" "$NGINX_OUTPUT_DIR/default.conf"
    social_cangaroo_render_remote_turn_conf "$WORKSPACE_DIR" "$COTURN_OUTPUT_DIR/turnserver.conf"
    social_cangaroo_success "✓ social-cangaroo-init rendered remote nginx and coturn config"
    exit 0
fi

if [[ -n "${TURN_SECRET:-}" && -n "${TURN_HOST:-}" ]]; then
    export TURN_EXTERNAL_IP="$TURN_HOST"
    social_cangaroo_render_remote_turn_conf "$WORKSPACE_DIR" "$COTURN_OUTPUT_DIR/turnserver.conf"
    social_cangaroo_success "✓ social-cangaroo-init rendered local TURN config"
    exit 0
fi

social_cangaroo_success "✓ social-cangaroo-init no-op for current profile"
