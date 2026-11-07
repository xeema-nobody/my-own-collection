#!/usr/bin/env bash
# Phone scanning gate (Tailscale). Never reads or prints .env; secrets live in lan/lan.env (gitignored).
#   scripts/lan.sh setup <tailnet-host> <tailscale-login>   write lan/lan.env (e.g. mac.tail1234.ts.net you@example.com)
#   scripts/lan.sh up       build the phone page, start the gate, print the tailscale command + URL
#   scripts/lan.sh down     stop the gate (the app keeps running)
#   scripts/lan.sh status
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=lan/lan.env

# value of KEY in lan.env ("" when the file or key is missing; must not fail under set -e / pipefail)
val() { { grep -E "^$1=" "$ENV_FILE" 2>/dev/null || true; } | head -1 | cut -d= -f2-; }

case "${1:-}" in
  setup)
    host="${2:?usage: lan.sh setup <tailnet-host> <tailscale-login>}"; login="${3:?usage: lan.sh setup <tailnet-host> <tailscale-login>}"
    [[ "$host" =~ ^[A-Za-z0-9.-]+\.ts\.net$ ]] || { echo "host must look like name.tailnet.ts.net"; exit 1; }
    secret="$(val MOC_GATE_SECRET)"; [[ -n "$secret" ]] || secret="$(openssl rand -hex 32)"
    umask 077
    cat > "$ENV_FILE" <<EOT
MOC_GATE_SECRET=$secret
LAN_GATE_SECRET=$secret
LAN_ORIGIN=https://$host
LAN_LOGIN=$login
MOC_TS_LOGIN=$login
ALLOWED_HOSTS=localhost,127.0.0.1,$host
EOT
    echo "wrote $ENV_FILE. Restart the app so it reads it: docker compose up -d app"
    ;;
  up)
    [[ -f "$ENV_FILE" ]] || { echo "run: scripts/lan.sh setup <tailnet-host> <tailscale-login>"; exit 1; }
    docker compose up -d app
    docker compose run --rm -e VITE_API_URL= web sh -c "npm install --no-audit --no-fund && npm run build"
    docker compose --profile lan up -d lan
    host="$(val LAN_ORIGIN)"
    echo; echo "Gate running on 127.0.0.1:5443. Now (once) expose it on your tailnet:"
    echo "  tailscale serve --bg --https=443 http://127.0.0.1:5443"
    echo "Open on the phone (Tailscale on):  $host/scan"
    ;;
  down) docker compose --profile lan stop lan ;;
  status)
    [[ -f "$ENV_FILE" ]] && echo "configured: $(val LAN_ORIGIN) (login $(val LAN_LOGIN))" || echo "not configured"
    docker compose --profile lan ps lan 2>/dev/null || true
    command -v tailscale >/dev/null && tailscale serve status || echo "tailscale CLI not found"
    ;;
  *) sed -n 2,7p "$0"; exit 1 ;;
esac
