#!/usr/bin/env bash
# Send nightly backups offsite, to a Cloudflare R2 bucket, ENCRYPTED.
#
# Run this yourself, on the server, once. It asks for the R2 credentials and an
# encryption passphrase and types nothing anywhere else: the values go to the
# rclone config (mode 600) and nowhere else. Nobody else needs to see them.
#
#   ./scripts/setup_offsite_backup.sh
#
# Before you run it, in the Cloudflare dashboard (R2):
#   1. Create a bucket, e.g. aicall-backups.
#   2. R2 -> Manage API Tokens -> Create token, permission "Object Read & Write",
#      scoped to that ONE bucket. It shows an Access Key ID and a Secret Access
#      Key once. Your Account ID is on the R2 overview page.
#
# Why encrypted: a backup holds every user's password hash and every API key an
# organisation has stored. A bucket is one leaked token away from public, and the
# Cloudflare account is a different trust boundary from this server. rclone
# `crypt` encrypts file contents AND file names, so even the bucket listing
# reveals nothing.
#
# THE PASSPHRASE IS THE ONLY KEY. Lose it and every offsite backup is
# unreadable, permanently. Put it in your password manager now, not later.
#
# Non-interactive (testing / automation): set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
# R2_SECRET_ACCESS_KEY, R2_BUCKET and BACKUP_CRYPT_PASSPHRASE, and optionally
# RCLONE_CONFIG and BACKUP_ENV_FILE to write somewhere else.
set -euo pipefail

cd "$(dirname "$0")/.."

RETAIN_DAYS="${OFFSITE_RETAIN_DAYS:-30}"
ENV_FILE="${BACKUP_ENV_FILE:-./backup.env}"
export RCLONE_CONFIG="${RCLONE_CONFIG:-$HOME/.config/rclone/rclone.conf}"

die() { echo "error: $*" >&2; exit 1; }

ask() {   # ask VAR "prompt" [secret]
    local var=$1 prompt=$2 secret=${3:-}
    if [ -n "${!var:-}" ]; then return; fi
    if [ "$secret" = secret ]; then
        read -r -s -p "$prompt: " "$var"; echo
    else
        read -r -p "$prompt: " "$var"
    fi
    [ -n "${!var}" ] || die "$var is required"
}

if ! command -v rclone >/dev/null 2>&1; then
    echo "==> installing rclone"
    sudo apt-get update -qq && sudo apt-get install -y -qq rclone \
        || die "could not install rclone; install it and re-run"
fi

# R2_ENDPOINT exists so the whole script can be exercised against any S3
# compatible store (the server's own MinIO, in the self-test) without touching a
# real account. Leave it unset for R2.
PASSPHRASE_PROVIDED=${BACKUP_CRYPT_PASSPHRASE:+yes}

if [ -z "${R2_ENDPOINT:-}" ]; then ask R2_ACCOUNT_ID "R2 Account ID"; fi
ask R2_ACCESS_KEY_ID      "R2 Access Key ID"
ask R2_SECRET_ACCESS_KEY  "R2 Secret Access Key (hidden)" secret
ask R2_BUCKET             "R2 bucket name"
ask BACKUP_CRYPT_PASSPHRASE "Encryption passphrase (hidden; SAVE IT SOMEWHERE ELSE)" secret

# A typo in a passphrase you will never see again means a backup you can never
# read. Confirmed only when it was typed; one passed in by the environment is
# not a typo risk.
if [ -z "$PASSPHRASE_PROVIDED" ]; then
    read -r -s -p "Type the passphrase again: " CONFIRM; echo
    [ "$CONFIRM" = "$BACKUP_CRYPT_PASSPHRASE" ] || die "passphrases did not match; nothing was written"
fi
[ "${#BACKUP_CRYPT_PASSPHRASE}" -ge 12 ] || die "use a passphrase of at least 12 characters"

if [ -n "${R2_ENDPOINT:-}" ]; then
    ENDPOINT=$R2_ENDPOINT; PROVIDER=Other
else
    ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"; PROVIDER=Cloudflare
fi

mkdir -p "$(dirname "$RCLONE_CONFIG")"
( umask 077; : >"$RCLONE_CONFIG.new" )

# Two remotes: `r2` is the raw bucket, `aicall-backup` wraps it in encryption.
# Only the wrapper is ever written to by the hook.
#
# ponytail: no separate salt (password2). rclone allows omitting it; it only
# hardens against precomputed attacks on a weak passphrase, and a 12+ character
# passphrase is required above. Adding it would mean a SECOND secret to lose.
OBSCURED=$(rclone obscure "$BACKUP_CRYPT_PASSPHRASE")
{
    echo "[r2]"
    echo "type = s3"
    echo "provider = $PROVIDER"
    echo "access_key_id = $R2_ACCESS_KEY_ID"
    echo "secret_access_key = $R2_SECRET_ACCESS_KEY"
    echo "endpoint = $ENDPOINT"
    echo "acl = private"
    # A token scoped to one bucket cannot list or create buckets.
    echo "no_check_bucket = true"
    echo
    echo "[aicall-backup]"
    echo "type = crypt"
    echo "remote = r2:${R2_BUCKET}"
    echo "filename_encryption = standard"
    echo "directory_name_encryption = true"
    echo "password = $OBSCURED"
} >>"$RCLONE_CONFIG.new"
chmod 600 "$RCLONE_CONFIG.new"
# Keep a copy of any config we are replacing; it may hold other remotes.
[ -f "$RCLONE_CONFIG" ] && cp -p "$RCLONE_CONFIG" "$RCLONE_CONFIG.bak.$(date +%s)"
mv "$RCLONE_CONFIG.new" "$RCLONE_CONFIG"
echo "==> wrote $RCLONE_CONFIG (mode 600)"

echo "==> testing: upload, list and read back through the encrypted remote"
PROBE="probe-$(date +%s)"
echo "offsite backup probe" | rclone rcat "aicall-backup:$PROBE" \
    || die "upload failed. Check the account id, the token's bucket scope, and the bucket name."
GOT=$(rclone cat "aicall-backup:$PROBE") || die "uploaded but could not read back"
[ "$GOT" = "offsite backup probe" ] || die "read back different content"
RAW=$(rclone lsf "r2:${R2_BUCKET}" | head -5)
rclone deletefile "aicall-backup:$PROBE"
case "$RAW" in
    *probe*) die "the bucket shows the plain file name: encryption is NOT active" ;;
esac
echo "  ok -- and the name in the bucket is scrambled, so encryption is active"

# The hook is what backup.sh runs after each good backup. The retention line
# deletes offsite copies older than $RETAIN_DAYS days so the bucket does not
# grow forever; `|| true` there because failing to prune must not mark a backup
# that DID upload as failed.
cat >"$ENV_FILE" <<EOF
# Written by scripts/setup_offsite_backup.sh. Contains no secrets: the keys live
# in the rclone config (mode 600), referenced by RCLONE_CONFIG below.
export RCLONE_CONFIG='$RCLONE_CONFIG'
BACKUP_POST_HOOK='rclone copy "\$1" "aicall-backup:\$(basename "\$1")" && { rclone delete aicall-backup: --min-age ${RETAIN_DAYS}d --rmdirs || true; }'
EOF
chmod 600 "$ENV_FILE"
echo "==> wrote $ENV_FILE"

echo
echo "Done. The next nightly backup (03:00) will be uploaded encrypted."
echo "To prove it now:   ./scripts/backup.sh backup"
echo "To restore later:  rclone copy aicall-backup:<STAMP> ./restore && ./scripts/backup.sh verify ./restore"
echo
echo "REMINDER: the passphrase is the only key to these backups. Store it elsewhere."
