#!/usr/bin/env bash
# Back up, verify and restore the compose stack's data.
#
# There was no backup of any kind before this: Postgres, Redis and MinIO live
# in local Docker volumes on one host, and the documented "rollback" only
# restores config files. Losing the host lost every agent, call, credential and
# recording.
#
# Redis is deliberately NOT backed up. It holds the ARQ queue, rate-limit
# counters and call-transfer state -- all rebuildable, none of it a source of
# truth. Backing it up would restore stale in-flight jobs on top of a restored
# database, which is worse than losing them.
#
#   ./scripts/backup.sh backup            dump postgres + archive the minio volume
#   ./scripts/backup.sh verify <dir>      prove a backup restores, in a throwaway container
#   ./scripts/backup.sh restore <dir>     restore INTO THE LIVE STACK (destructive)
#
# Env:
#   BACKUP_DIR         where backups go              (default ./backups)
#   BACKUP_KEEP_DAYS   prune older than this         (default 14)
#   BACKUP_POST_HOOK   run after a good backup, gets the backup dir as $1.
#                      This is the offsite step, deliberately left to you so no
#                      provider or credential is baked in here. e.g.
#                      BACKUP_POST_HOOK='rclone copy "$1" r2:aicall-backups/'
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
PG_IMAGE="pgvector/pgvector:pg17"   # must match docker-compose.yaml: the dump
                                    # contains `CREATE EXTENSION vector`
die() { echo "error: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

# A dump that is short, or does not start with the custom-format magic, is a
# truncated file or an error message -- the usual failure when postgres was not
# reachable. Checked on every backup so a broken one is never silently kept.
assert_dump_sane() {
    local f=$1 size
    [ -f "$f" ] || die "no dump written at $f"
    size=$(wc -c <"$f")
    [ "$size" -gt 1024 ] || die "dump is only ${size} bytes -- postgres almost certainly errored"
    [ "$(head -c 5 "$f")" = "PGDMP" ] || die "dump does not start with PGDMP; it is not a valid custom-format dump"
    echo "  postgres.dump ok (${size} bytes, PGDMP header present)"
}

minio_cid() { docker compose ps -q minio 2>/dev/null || true; }

cmd_backup() {
    have docker
    local stamp out
    stamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
    out="$BACKUP_DIR/$stamp"
    mkdir -p "$out"

    echo "==> postgres"
    # -Fc (custom format) so pg_restore can list it, restore selectively, and
    # run in parallel. Plain SQL would rule all three out.
    docker compose exec -T postgres pg_dump -U postgres -Fc postgres >"$out/postgres.dump" \
        || die "pg_dump failed -- is the stack up?"
    assert_dump_sane "$out/postgres.dump"

    echo "==> minio"
    local cid
    cid=$(minio_cid)
    if [ -z "$cid" ]; then
        echo "  minio container not running, skipping object storage"
    else
        # --volumes-from inherits minio's own mount, so we never have to guess
        # the project-prefixed volume name (which COMPOSE_PROJECT_NAME changes).
        docker run --rm --volumes-from "$cid" -v "$(pwd)/$out:/backup" alpine \
            tar czf /backup/minio-data.tgz -C /data . || die "minio archive failed"
        echo "  minio-data.tgz ok ($(wc -c <"$out/minio-data.tgz") bytes)"
    fi

    # Record what this was taken from, so a restore is not guesswork.
    { echo "taken_utc=$stamp"; echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)";
      echo "pg_image=$PG_IMAGE"; } >"$out/MANIFEST"

    if [ -n "${BACKUP_POST_HOOK:-}" ]; then
        echo "==> post hook"
        bash -c "$BACKUP_POST_HOOK" _ "$out" || die "post hook failed -- backup is local-only"
    else
        echo "  no BACKUP_POST_HOOK set: this backup exists only on this host."
    fi

    # ponytail: prune by mtime, not by parsing the stamp. Ceiling: a clock jump
    # backwards keeps extra backups, which is the harmless direction.
    find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$BACKUP_KEEP_DAYS" -exec rm -rf {} + 2>/dev/null || true
    echo "==> done: $out"
}

# The only thing that turns a backup into something you can rely on. Restores
# into a throwaway container and counts what came back -- never touches the
# live database.
cmd_verify() {
    have docker
    local dir=${1:?usage: backup.sh verify <dir>}
    assert_dump_sane "$dir/postgres.dump"

    local name="aicall-verify-$$"
    echo "==> starting throwaway $PG_IMAGE"
    docker run -d --rm --name "$name" -e POSTGRES_PASSWORD=verify "$PG_IMAGE" >/dev/null
    # shellcheck disable=SC2064
    trap "docker rm -f '$name' >/dev/null 2>&1 || true" EXIT

    local i
    for i in $(seq 30); do
        docker exec "$name" pg_isready -U postgres >/dev/null 2>&1 && break
        [ "$i" = 30 ] && die "throwaway postgres never became ready"
        sleep 1
    done

    echo "==> restoring"
    docker exec -i "$name" pg_restore -U postgres -d postgres --no-owner <"$dir/postgres.dump" \
        || die "pg_restore failed: this backup is NOT restorable"

    local tables rows
    tables=$(docker exec "$name" psql -U postgres -tAc \
        "select count(*) from information_schema.tables where table_schema='public'")
    rows=$(docker exec "$name" psql -U postgres -tAc \
        "select coalesce(sum(n_live_tup),0) from pg_stat_user_tables")
    echo "  restored $tables tables, ~$rows rows"
    [ "$tables" -gt 10 ] || die "only $tables tables restored -- that is not this schema"
    echo "==> VERIFIED: $dir restores cleanly"
}

cmd_restore() {
    have docker
    local dir=${1:?usage: backup.sh restore <dir>}
    assert_dump_sane "$dir/postgres.dump"
    echo "This OVERWRITES the live database and object storage from $dir."
    read -r -p "Type 'restore' to continue: " confirm
    [ "$confirm" = "restore" ] || die "aborted"

    echo "==> postgres"
    docker compose exec -T postgres psql -U postgres -d postgres -c \
        "drop schema public cascade; create schema public;" >/dev/null
    docker compose exec -T postgres pg_restore -U postgres -d postgres --no-owner <"$dir/postgres.dump"

    if [ -f "$dir/minio-data.tgz" ]; then
        echo "==> minio"
        local cid; cid=$(minio_cid)
        [ -n "$cid" ] || die "minio container is not running"
        docker run --rm --volumes-from "$cid" -v "$(pwd)/$dir:/backup" alpine \
            sh -c 'rm -rf /data/* /data/..?* 2>/dev/null; tar xzf /backup/minio-data.tgz -C /data'
    fi
    echo "==> restored. Restart the stack so the api reconnects."
}

case "${1:-}" in
    backup)  shift; cmd_backup "$@" ;;
    verify)  shift; cmd_verify "$@" ;;
    restore) shift; cmd_restore "$@" ;;
    *) sed -n '2,24p' "$0" | sed 's/^# \?//'; exit 1 ;;
esac
