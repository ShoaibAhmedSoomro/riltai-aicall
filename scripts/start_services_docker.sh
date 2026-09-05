#!/usr/bin/env bash
set -e

###############################################################################
### CONFIGURATION
###############################################################################

BASE_DIR="$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)"
ENV_FILE="$BASE_DIR/api/.env"

ARQ_WORKERS=${ARQ_WORKERS:-1}
FASTAPI_WORKERS=${FASTAPI_WORKERS:-1}
UVICORN_BASE_PORT=${UVICORN_BASE_PORT:-8000}

cd "$BASE_DIR"
echo "Starting AICall Services (DOCKER) at $(date) in BASE_DIR: ${BASE_DIR}"

###############################################################################
### 1) Load env file if mounted (env normally comes from docker-compose)
###############################################################################

if [[ -f "$ENV_FILE" ]]; then
  set -a && . "$ENV_FILE" && set +a
fi

# The drain below polls /health/active-calls, which returns 503 unless a devops
# secret is configured -- and no setup script has ever written one, so on every
# compose install the drain would be dead on arrival. Mint an ephemeral one here
# instead of asking six setup scripts to generate a key: we export it before the
# uvicorns fork, so the workers and the poller agree by construction, and every
# existing install gets a working drain with no operator action.
#
# An operator who wants to poll the endpoint from OUTSIDE the container still
# sets RILT_DEVOPS_SECRET in .env -- an ephemeral value changes on every restart
# and is deliberately useless to anyone but this process tree.
if [[ -z "${RILT_DEVOPS_SECRET:-}" ]]; then
  RILT_DEVOPS_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  echo "RILT_DEVOPS_SECRET not set; using an ephemeral one for in-container drain only."
fi
export RILT_DEVOPS_SECRET

###############################################################################
### 2) Run migrations
###############################################################################

alembic -c "$BASE_DIR/api/alembic.ini" upgrade head

###############################################################################
### 3) Signal handling — forward TERM/INT to children for clean docker stop
###############################################################################

pids=()

DRAIN_MAX_WAIT=${DRAIN_MAX_WAIT:-300}
DRAIN_POLL_INTERVAL=${DRAIN_POLL_INTERVAL:-5}

# Wait for in-flight calls to finish before the workers are killed. uvicorn
# force-closes live call WebSockets (close code 1012) on SIGTERM, so without
# this a deploy cuts every conversation mid-sentence.
#
# Each uvicorn keeps its own in-process count, so EVERY worker port has to be
# polled -- polling only the base port reports zero while workers on 8001+ are
# still on calls. Written in python because the runtime image has no curl and
# no wget (the compose healthcheck uses urllib for the same reason).
#
# Note the honest limit: compose runs one api container, so there is nowhere to
# shift traffic to. Draining holds the last instance open to finish existing
# calls; NEW calls fail for that window. Finishing conversations beats cutting
# them, but this is not zero-downtime -- that needs a second replica.
drain() {
  echo "Draining: waiting up to ${DRAIN_MAX_WAIT}s for in-flight calls to finish..."
  python - "$UVICORN_BASE_PORT" "$FASTAPI_WORKERS" "$DRAIN_MAX_WAIT" "$DRAIN_POLL_INTERVAL" <<'PY' || true
import json, os, sys, time, urllib.error, urllib.request

base, workers, max_wait, interval = (int(a) for a in sys.argv[1:5])
secret = os.environ.get("RILT_DEVOPS_SECRET", "")


def busy(port):
    """In-flight calls on one worker. Unknown counts as busy, never as drained."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/health/active-calls",
        headers={"X-Rilt-Devops-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return int(json.load(r)["active_calls"])
    except urllib.error.HTTPError as e:
        # 403/503 means we cannot measure at all. Hanging for the full timeout
        # on every deploy is worse than saying so and moving on -- but never
        # print "drained", because that would be a lie in the deploy log.
        print(f"  cannot read worker {port}: HTTP {e.code} -- skipping drain", flush=True)
        raise SystemExit(0)
    except Exception as e:
        # ONE decision, so there is no second path to leave untested: a refused
        # connection means no listener and therefore no calls; everything else
        # (timeout, reset, black hole) is a live worker we failed to read, and
        # assuming it is idle would SIGTERM it mid-call. Note a read timeout
        # arrives as a bare TimeoutError, not wrapped in URLError, which is why
        # this catches broadly rather than matching URLError alone.
        return 0 if isinstance(getattr(e, "reason", None), ConnectionRefusedError) else 1


deadline = time.monotonic() + max_wait
while True:
    total = sum(busy(base + i) for i in range(workers))
    if total == 0:
        print("  drained: no calls in flight", flush=True)
        break
    left = deadline - time.monotonic()
    if left <= 0:
        print(f"  drain timed out with {total} call(s) still active; stopping anyway", flush=True)
        break
    print(f"  {total} call(s) in flight, {int(left)}s left", flush=True)
    time.sleep(min(interval, max(left, 1)))
PY
}

shutdown() {
  # Only the signal path drains. `wait -n` below also calls this when a child
  # CRASHES, and there we want the container to restart immediately -- draining
  # then would leave it sitting for minutes while restart: unless-stopped waits.
  if [[ "${1:-}" == "drain" ]]; then
    drain
  fi
  echo "Stopping services..."
  for pid in "${pids[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  wait
  exit 0
}

trap 'shutdown drain' TERM INT

start() {
  local name=$1
  shift
  echo "→ Starting $name"
  "$@" &
  pids+=($!)
  echo "  $name PID $!"
}

###############################################################################
### 4) Start services (logs go to stdout for `docker logs`)
###############################################################################

# ari_manager and campaign_orchestrator are optional; each defaults to on and
# can be turned off (e.g. for an API/worker-only replica) by setting the flag to
# "false" in the container env / docker-compose .env.
ENABLE_ARI_MANAGER=${ENABLE_ARI_MANAGER:-true}
ENABLE_CAMPAIGN_ORCHESTRATOR=${ENABLE_CAMPAIGN_ORCHESTRATOR:-true}

if [[ "$ENABLE_ARI_MANAGER" == "true" ]]; then
  start ari_manager           python -m api.services.telephony.ari_manager
else
  echo "ari_manager disabled (ENABLE_ARI_MANAGER=$ENABLE_ARI_MANAGER)"
fi

if [[ "$ENABLE_CAMPAIGN_ORCHESTRATOR" == "true" ]]; then
  start campaign_orchestrator python -m api.services.campaign.campaign_orchestrator
else
  echo "campaign_orchestrator disabled (ENABLE_CAMPAIGN_ORCHESTRATOR=$ENABLE_CAMPAIGN_ORCHESTRATOR)"
fi

# Spawn FASTAPI_WORKERS independent uvicorn processes on consecutive ports
# starting at UVICORN_BASE_PORT. nginx upstream (configured in setup_remote.sh)
# balances across them with least_conn — better than uvicorn --workers for
# long-lived WebSocket connections, which would otherwise stick to whichever
# worker accepted them first.
for ((i=0; i<FASTAPI_WORKERS; i++)); do
  port=$((UVICORN_BASE_PORT + i))
  start "uvicorn$i" uvicorn api.app:app --host 0.0.0.0 --port "$port" --workers 1
done

for ((i=1; i<=ARQ_WORKERS; i++)); do
  start "arq$i" python -m arq api.tasks.arq.WorkerSettings --custom-log-dict api.tasks.arq.LOG_CONFIG
done

###############################################################################
### 5) Wait — if any service exits, tear the container down so docker restarts
###############################################################################

wait -n
echo "A service exited; tearing down container."
shutdown
