#!/usr/bin/env bash
# Install script for the TikTok Auto Uploader API on Ubuntu/Debian hosts.
set -euo pipefail
IFS=$'\n\t'

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEFAULT_REPO_DIR="$(realpath "$SCRIPT_DIR/..")"
readonly NODE_SETUP_URL="https://deb.nodesource.com/setup_18.x"
readonly APT_PACKAGES=(
  python3
  python3-pip
  python3-venv
  git
  ffmpeg
  curl
  ca-certificates
  lsb-release
  gnupg
  apt-transport-https
  openssl
  build-essential
)

API_USER="tiktokapi"
API_HOME="/var/lib/tiktokapi"
SERVICE_UNIT_NAME="tiktok-uploader-api.service"
SERVICE_FILE_DEFAULT="/etc/systemd/system/$SERVICE_UNIT_NAME"
ENV_FILE_DEFAULT="/etc/tiktok-uploader-api.env"

REPO_DIR="$DEFAULT_REPO_DIR"
SERVICE_FILE="$SERVICE_FILE_DEFAULT"
ENV_FILE="$ENV_FILE_DEFAULT"
SKIP_SYSTEMD=0
UPLOAD_SECRET_OVERRIDE=""
VENV_DIR=""

usage() {
  cat <<'EOF'
Usage: install-ubuntu-api.sh [options]

Options:
  --repo-dir DIR          Repository root (defaults to script parent).
  --env-file FILE         Env file path (default: /etc/tiktok-uploader-api.env).
  --service-file FILE     systemd unit file (default: /etc/systemd/system/tiktok-uploader-api.service).
  --upload-secret SECRET  Supply your own UPLOAD_SECRET instead of generating one.
  --skip-systemd          Configure files but skip reloading/enabling the service.
  --help                  Show this help text.
EOF
}

log() {
  printf '==> %s\n' "$*"
}

fatal() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    fatal "This script must be run as root (e.g., sudo)."
  fi
}

run_as_api() {
  local cmd="$1"
  sudo -u "$API_USER" -H bash -c "$cmd"
}

parse_args() {
  while [ "${#}" -gt 0 ]; do
    case "${1:-}" in
      --repo-dir)
        REPO_DIR="$2"
        shift 2
        ;;
      --env-file)
        ENV_FILE="$2"
        shift 2
        ;;
      --service-file)
        SERVICE_FILE="$2"
        shift 2
        ;;
      --upload-secret)
        UPLOAD_SECRET_OVERRIDE="$2"
        shift 2
        ;;
      --skip-systemd)
        SKIP_SYSTEMD=1
        shift
        ;;
      --help)
        usage
        exit 0
        ;;
      *)
        fatal "Unknown argument: $1"
        ;;
    esac
  done
}

ensure_repo() {
  REPO_DIR="$(realpath "$REPO_DIR")"
  VENV_DIR="$REPO_DIR/.venv"
  if [ ! -f "$REPO_DIR/api.py" ]; then
    fatal "Cannot locate api.py in $REPO_DIR. Run this script from the repository root or pass --repo-dir."
  fi
}

setup_python_venv() {
  if [ -z "$VENV_DIR" ]; then
    fatal "Virtualenv directory is not set."
  fi
  log "Creating Python virtualenv at $VENV_DIR"
  if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
  else
    log "Virtualenv already exists; reusing $VENV_DIR"
  fi
  chown -R "$API_USER:$API_USER" "$VENV_DIR"
}

install_packages() {
  log "Updating APT cache and upgrading existing packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get upgrade -y
  log "Installing base packages: ${APT_PACKAGES[*]}"
  apt-get install -y "${APT_PACKAGES[@]}"
}

install_node() {
  log "Installing Node.js 18 via the NodeSource setup script"
  curl -fsSL "$NODE_SETUP_URL" | bash -
  apt-get install -y nodejs
  log "Node version: $(node -v)"
  log "npm version: $(npm -v)"
}

ensure_user() {
  if id -u "$API_USER" >/dev/null 2>&1; then
    log "User $API_USER already exists"
    local current_home
    current_home="$(getent passwd "$API_USER" | cut -d: -f6)"
    if [ "$current_home" != "$API_HOME" ]; then
      log "Updating home directory of $API_USER to $API_HOME"
      usermod -d "$API_HOME" "$API_USER"
    fi
    local current_shell
    current_shell="$(getent passwd "$API_USER" | cut -d: -f7)"
    if [ "$current_shell" != "/bin/bash" ]; then
      log "Setting login shell for $API_USER to /bin/bash"
      usermod -s /bin/bash "$API_USER"
    fi
  else
    log "Creating dedicated system user '$API_USER' with home $API_HOME"
    mkdir -p "$API_HOME"
    useradd -r -M -d "$API_HOME" -s /bin/bash -U "$API_USER"
  fi
  mkdir -p "$API_HOME"
  chown "$API_USER:$API_USER" "$API_HOME"
}

install_python_deps() {
  if [ -z "$VENV_DIR" ] || [ ! -d "$VENV_DIR" ]; then
    fatal "Virtualenv missing at $VENV_DIR"
  fi
  log "Installing Python dependencies into $VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
  "$VENV_DIR/bin/pip" install --no-cache-dir -r "$REPO_DIR/requirements.txt"
  chown -R "$API_USER:$API_USER" "$VENV_DIR"
}

install_node_deps() {
  local signature_dir="$REPO_DIR/tiktok_uploader/tiktok-signature"
  if [ ! -d "$signature_dir" ]; then
    fatal "Missing signature helper directory at $signature_dir"
  fi
  log "Installing Node.js dependencies"
  run_as_api "set -euo pipefail && cd '$signature_dir' && npm ci --no-audit --prefer-offline"
  mkdir -p "$signature_dir/.playwright-browsers"
  chown -R "$API_USER:$API_USER" "$signature_dir/.playwright-browsers"
  log "Installing Playwright Chromium binaries"
  run_as_api "set -euo pipefail && cd '$signature_dir' && PLAYWRIGHT_BROWSERS_PATH='$signature_dir/.playwright-browsers' npx playwright install chromium"
}

ensure_env_file() {
  if [ -f "$ENV_FILE" ]; then
    log "$ENV_FILE already exists; keeping current upload secret."
    return
  fi
  mkdir -p "$(dirname "$ENV_FILE")"
  local secret="${UPLOAD_SECRET_OVERRIDE:-}"
  if [ -z "$secret" ]; then
    secret="$(openssl rand -hex 32)"
  fi
  log "Writing upload secret to $ENV_FILE"
  cat <<EOF >"$ENV_FILE"
UPLOAD_SECRET=$secret
EOF
  chmod 600 "$ENV_FILE"
  chown root:root "$ENV_FILE"
  log "Exported UPLOAD_SECRET (keep this value for X-Upload-Auth): $secret"
}

write_service() {
  mkdir -p "$(dirname "$SERVICE_FILE")"
  local python_bin
  python_bin="$VENV_DIR/bin/python"
  local playwright_path="$REPO_DIR/tiktok_uploader/tiktok-signature/.playwright-browsers"
  log "Writing systemd unit to $SERVICE_FILE"
  cat <<EOF >"$SERVICE_FILE"
[Unit]
Description=TikTok Uploader API Service
After=network.target

[Service]
User=$API_USER
Group=$API_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENV_FILE
Environment="PLAYWRIGHT_BROWSERS_PATH=$playwright_path"
ExecStart=/bin/bash -c "PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin $python_bin -m uvicorn api:app --host 0.0.0.0 --port 8000"
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=tiktok-uploader-api

[Install]
WantedBy=multi-user.target
EOF
  chmod 644 "$SERVICE_FILE"
  chown root:root "$SERVICE_FILE"
}

deploy_systemd() {
  if [ "$SKIP_SYSTEMD" -ne 0 ]; then
    log "Skipping systemd reload/enable because --skip-systemd was passed."
    return
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    fatal "systemctl is unavailable; skip service setup manually."
  fi
  log "Reloading systemd daemon"
  systemctl daemon-reload
  local service_unit="${SERVICE_UNIT_NAME:-$(basename "$SERVICE_FILE")}"
  log "Enabling and restarting $service_unit"
  systemctl enable "$service_unit"
  systemctl restart "$service_unit"
  log "API service started; use 'systemctl status $service_unit' to inspect logs."
}

main() {
  parse_args "$@"
  SERVICE_UNIT_NAME="$(basename "$SERVICE_FILE")"
  require_root
  ensure_repo
  install_packages
  install_node
  ensure_user
  log "Ensuring repository files are owned by $API_USER"
  chown -R "$API_USER:$API_USER" "$REPO_DIR"
  setup_python_venv
  install_python_deps
  install_node_deps
  ensure_env_file
  write_service
  deploy_systemd
  log "Installation complete. Remember to point your uploader client at the server's /upload endpoint and include X-Upload-Auth."
}

main "$@"
