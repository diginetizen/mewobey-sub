#!/bin/bash
# ══════════════════════════════════════════════
#  gitsub installer v4
#  Installs to /opt/xui-subsync
# ══════════════════════════════════════════════
set -e

INSTALL_DIR="/opt/xui-subsync"
SERVICE_SYNC="xui-subsync"
SERVICE_UI="xui-webui"
NGINX_CONF="/etc/nginx/sites-available/xui-webui"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; CYAN="\033[0;36m"
RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"
info()    { echo -e "${CYAN}[info]${RESET} $*"; }
success() { echo -e "${GREEN}[ ok]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET} $*"; }
error()   { echo -e "${RED}[ err]${RESET} $*"; exit 1; }

clear
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}║   gitsub — XUI Subscription Sync v4      ║${RESET}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Panel ──────────────────────────────────
echo -e "${YELLOW}── Panel ─────────────────────────────────${RESET}"
echo "  Full URL of your 3x-ui panel, including port."
echo "  Examples:  https://panel.example.com:2053"
echo "             http://1.2.3.4:54321"
echo ""
read -rp "  Panel API base URL: " PANEL_API_URL
API_TOKEN=$(masked_input "  API Bearer Token: ")
echo ""

# ── 2. GitHub ──────────────────────────────────
echo -e "${YELLOW}── GitHub Repository ─────────────────────${RESET}"
read -rp "  GitHub username: " GITHUB_USER
read -rp "  GitHub repo name: " GITHUB_REPO
read -rp "  Branch [main]: " GITHUB_BRANCH
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
echo ""

# ── 3. Deploy method ───────────────────────────
echo -e "${YELLOW}── Deploy Method ─────────────────────────${RESET}"
echo "  [1] Personal Access Token (HTTPS) — easiest"
echo "  [2] SSH Deploy Key                — more secure"
echo ""
read -rp "  Choose [1/2] (default 1): " DEPLOY_CHOICE
DEPLOY_CHOICE="${DEPLOY_CHOICE:-1}"
echo ""

DEPLOY_METHOD="token"
GITHUB_TOKEN=""
SSH_KEY_PATH="/root/.ssh/gitsub_deploy"
SHOW_PUBKEY="n"

if [ "$DEPLOY_CHOICE" = "2" ]; then
    DEPLOY_METHOD="ssh"
    echo -e "${YELLOW}── SSH Key ───────────────────────────────${RESET}"
    echo "  [1] I already have a key added to this repo"
    echo "  [2] Generate a new key for me"
    echo ""
    read -rp "  Choose [1/2] (default 2): " HAS_KEY
    HAS_KEY="${HAS_KEY:-2}"

    if [ "$HAS_KEY" = "1" ]; then
        echo ""
        echo "  [1] Enter the file path to my key"
        echo "  [2] Paste the private key content"
        echo ""
        read -rp "  Choose [1/2] (default 1): " KEY_INPUT_METHOD
        KEY_INPUT_METHOD="${KEY_INPUT_METHOD:-1}"

        if [ "$KEY_INPUT_METHOD" = "2" ]; then
            info "Paste your private key. Press Ctrl+D on an empty line when done."
            echo ""
            mkdir -p /root/.ssh && chmod 700 /root/.ssh
            cat > "$SSH_KEY_PATH"
            chmod 600 "$SSH_KEY_PATH"
            ssh-keygen -y -f "$SSH_KEY_PATH" > "$SSH_KEY_PATH.pub" 2>/dev/null || true
            success "Key saved to $SSH_KEY_PATH"
        else
            read -rp "  Key path [/root/.ssh/id_rsa]: " SSH_KEY_PATH
            SSH_KEY_PATH="${SSH_KEY_PATH:-/root/.ssh/id_rsa}"
            [ ! -f "$SSH_KEY_PATH" ] && error "Key not found: $SSH_KEY_PATH"
            chmod 600 "$SSH_KEY_PATH"
            success "Using key: $SSH_KEY_PATH"
        fi
        # User says key is already on GitHub — no need to show public key
        SHOW_PUBKEY="n"
    else
        info "Generating new ED25519 deploy key..."
        mkdir -p /root/.ssh && chmod 700 /root/.ssh
        rm -f "$SSH_KEY_PATH" "$SSH_KEY_PATH.pub"
        ssh-keygen -t ed25519 -C "gitsub@$(hostname)" -f "$SSH_KEY_PATH" -N ""
        success "Key generated: $SSH_KEY_PATH"
        SHOW_PUBKEY="y"
    fi

    # Write ~/.ssh/config alias so git uses this specific key
    SSH_CONFIG="/root/.ssh/config"
    grep -q "Host github-gitsub" "$SSH_CONFIG" 2>/dev/null && \
        sed -i '/Host github-gitsub/,+5d' "$SSH_CONFIG"
    cat >> "$SSH_CONFIG" <<SSHEOF

Host github-gitsub
    HostName github.com
    User git
    IdentityFile $SSH_KEY_PATH
    IdentitiesOnly yes
    StrictHostKeyChecking no
SSHEOF
    chmod 600 "$SSH_CONFIG"
    success "SSH config alias written"

    # Only show the ACTION REQUIRED block for newly generated keys
    if [ "$SHOW_PUBKEY" = "y" ]; then
        echo ""
        echo -e "${YELLOW}╔══ ACTION REQUIRED ═══════════════════════════╗${RESET}"
        echo -e "${YELLOW}║  Add this public key to your GitHub repo       ║${RESET}"
        echo -e "${YELLOW}║  Settings → Deploy keys → Add deploy key       ║${RESET}"
        echo -e "${YELLOW}║  ✓ Allow write access                          ║${RESET}"
        echo -e "${YELLOW}╚═══════════════════════════════════════════════╝${RESET}"
        echo ""
        echo -e "  ${CYAN}Public key:${RESET}"
        echo "  ┌───────────────────────────────────────────────"
        cat "$SSH_KEY_PATH.pub" | sed 's/^/  │ /'
        echo "  └───────────────────────────────────────────────"
        echo ""
        echo -e "  ${CYAN}Direct link:${RESET}"
        echo "  https://github.com/$GITHUB_USER/$GITHUB_REPO/settings/keys/new"
        echo ""
        read -rp "  Press ENTER once you have added the key with write access..."
    fi

    # Test the connection
    info "Testing SSH connection to GitHub..."
    set +e
    SSH_TEST=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no -T git@github.com 2>&1)
    set -e
    if echo "$SSH_TEST" | grep -q "successfully authenticated"; then
        success "SSH to GitHub: OK"
    else
        warn "SSH test: $SSH_TEST"
        read -rp "  Press ENTER to continue anyway, or Ctrl+C to abort..."
    fi
    echo ""

else
    GITHUB_TOKEN=$(masked_input "  GitHub Personal Access Token (repo scope): ")
    echo ""
fi

# ── 4. Web UI ──────────────────────────────────
echo -e "${YELLOW}── Web Dashboard ─────────────────────────${RESET}"
read -rp "  Enable web dashboard? [Y/n]: " ENABLE_UI
ENABLE_UI="${ENABLE_UI:-y}"
echo ""

UI_PORT=2086
UI_USER="admin"
UI_PASS=""
HAS_SSL="n"
SSL_CERT=""
SSL_KEY=""

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    read -rp "  Web UI port [2086]: " UI_PORT
    UI_PORT="${UI_PORT:-2086}"

    echo ""
    echo -e "${YELLOW}── Login Credentials ─────────────────────${RESET}"
    read -rp "  Dashboard username [admin]: " UI_USER
    UI_USER="${UI_USER:-admin}"
    UI_PASS=$(masked_input "  Dashboard password: ")
    echo ""

    echo -e "${YELLOW}── SSL (optional) ────────────────────────${RESET}"
    echo "  Do you want HTTPS for the dashboard?"
    echo "  [1] No  — plain HTTP on port $UI_PORT"
    echo "  [2] Yes — I have cert files (cert.pem + key.pem)"
    echo "  [3] Yes — install via Certbot (needs a domain + nginx)"
    echo ""
    read -rp "  Choose [1/2/3] (default 1): " SSL_CHOICE
    SSL_CHOICE="${SSL_CHOICE:-1}"
    echo ""

    if [ "$SSL_CHOICE" = "2" ]; then
        HAS_SSL="manual"
        read -rp "  Path to certificate file (fullchain.pem): " SSL_CERT
        read -rp "  Path to private key file (privkey.pem): " SSL_KEY
        [ ! -f "$SSL_CERT" ] && error "Certificate not found: $SSL_CERT"
        [ ! -f "$SSL_KEY" ]  && error "Key not found: $SSL_KEY"
        success "SSL cert files accepted"
    elif [ "$SSL_CHOICE" = "3" ]; then
        HAS_SSL="certbot"
        read -rp "  Domain name (e.g. sub.example.com): " SSL_DOMAIN
        [ -z "$SSL_DOMAIN" ] && error "Domain name required for Certbot"
        read -rp "  Email for Let's Encrypt notices: " SSL_EMAIL
        SSL_EMAIL="${SSL_EMAIL:-admin@$SSL_DOMAIN}"
    fi
fi

# ── 5. Sync interval ───────────────────────────
echo -e "${YELLOW}── Sync Interval ─────────────────────────${RESET}"
echo "  [1] 6 hours  — production"
echo "  [2] 1 hour"
echo "  [3] 5 minutes — testing"
echo "  [4] Custom"
echo ""
read -rp "  Choose [1-4] (default 1): " ICHOICE
case "${ICHOICE:-1}" in
    2) INTERVAL=3600  ;;
    3) INTERVAL=300   ;;
    4) read -rp "  Seconds: " INTERVAL ;;
    *) INTERVAL=21600 ;;
esac
echo ""

# ── Summary ────────────────────────────────────
info "Summary:"
echo "   Panel URL   : $PANEL_API_URL"
echo "   GitHub      : $GITHUB_USER/$GITHUB_REPO ($GITHUB_BRANCH)"
echo "   Deploy via  : $DEPLOY_METHOD"
if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    echo "   Web UI port : $UI_PORT"
    case "$HAS_SSL" in
        manual)  echo "   SSL         : manual cert" ;;
        certbot) echo "   SSL         : Certbot ($SSL_DOMAIN)" ;;
        *)       echo "   SSL         : none (HTTP only)" ;;
    esac
fi
echo "   Sync every  : ${INTERVAL}s"
echo ""
read -rp "  Proceed? [Y/n]: " GO
[[ "${GO:-y}" =~ ^[Nn] ]] && echo "Aborted." && exit 0
echo ""

# ── Install packages ───────────────────────────
info "Installing packages..."
apt-get update -qq
PKGS="python3 python3-venv python3-pip git"
[ "$HAS_SSL" = "certbot" ] && PKGS="$PKGS nginx certbot python3-certbot-nginx"
apt-get install -y $PKGS -qq
success "Packages ready"

# ── Copy files ─────────────────────────────────
info "Setting up $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/subs" "$INSTALL_DIR/logs"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in update.py webui.py requirements.txt uninstall.sh; do
    [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
done
[ -d "$SCRIPT_DIR/subs" ] && cp -n "$SCRIPT_DIR/subs/"* "$INSTALL_DIR/subs/" 2>/dev/null || true
success "Files copied"

# ── Python venv ────────────────────────────────
info "Creating Python venv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
success "Python venv ready"

# ── Git ────────────────────────────────────────
info "Configuring git..."
git config --global user.email "${GITHUB_USER}@users.noreply.github.com"
git config --global user.name  "$GITHUB_USER"
git config --global init.defaultBranch "$GITHUB_BRANCH"
cd "$INSTALL_DIR"
[ ! -d .git ] && git init -q
git branch -M "$GITHUB_BRANCH" 2>/dev/null || true

[ "$DEPLOY_METHOD" = "ssh" ] \
    && REMOTE_URL="git@github-gitsub:$GITHUB_USER/$GITHUB_REPO.git" \
    || REMOTE_URL="https://${GITHUB_TOKEN}@github.com/$GITHUB_USER/$GITHUB_REPO.git"

git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

cat > .gitignore <<'GITIGNORE'
config.json
submap.json
venv/
.venv/
logs/
*.pyc
*.pyo
__pycache__/
*.egg-info/
dist/
build/
.DS_Store
Thumbs.db
.vscode/
.idea/
*.swp
*~
.env
.env.*
GITIGNORE

set +e
git fetch origin "$GITHUB_BRANCH" --quiet 2>/tmp/gitsub_git_err
FETCH_OK=$?
set -e
if [ $FETCH_OK -eq 0 ]; then
    git reset --hard "origin/$GITHUB_BRANCH" --quiet
    success "Synced with remote"
else
    warn "Could not fetch ($(cat /tmp/gitsub_git_err | head -1)) — OK for new repos"
    touch "$INSTALL_DIR/subs/.gitkeep"
    git add subs/ 2>/dev/null || true
fi
success "Git configured"

# ── config.json ────────────────────────────────
info "Writing config.json..."
cat > "$INSTALL_DIR/config.json" <<EOF
{
  "panel_api_url":  "$PANEL_API_URL",
  "api_token":      "$API_TOKEN",

  "github_user":    "$GITHUB_USER",
  "github_repo":    "$GITHUB_REPO",
  "github_branch":  "$GITHUB_BRANCH",

  "deploy_method":  "$DEPLOY_METHOD",
  "github_token":   "$GITHUB_TOKEN",
  "ssh_key_path":   "$SSH_KEY_PATH",

  "ui_user":        "$UI_USER",
  "ui_pass":        "$UI_PASS",
  "ui_port":        $UI_PORT,
  "ssl_cert":       "$SSL_CERT",
  "ssl_key":        "$SSL_KEY",

  "filename_length": 32,
  "filename_mode":   "random",
  "sync_interval":   $INTERVAL
}
EOF
chmod 600 "$INSTALL_DIR/config.json"
success "config.json written (chmod 600)"

# ── gitsub CLI ─────────────────────────────────
info "Installing gitsub CLI..."
cat > /usr/local/bin/gitsub <<EOF
#!/bin/bash
cd $INSTALL_DIR
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/update.py "\$@"
EOF
chmod +x /usr/local/bin/gitsub
success "gitsub command ready"

# ── Systemd: sync daemon ───────────────────────
info "Creating systemd service: $SERVICE_SYNC..."
cat > "/etc/systemd/system/$SERVICE_SYNC.service" <<EOF
[Unit]
Description=gitsub XUI Subscription Sync Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/update.py daemon --interval $INTERVAL
Restart=always
RestartSec=30
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── Systemd: web UI ────────────────────────────
if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    info "Creating systemd service: $SERVICE_UI..."
    cat > "/etc/systemd/system/$SERVICE_UI.service" <<EOF
[Unit]
Description=gitsub Web Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PORT=$UI_PORT
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/webui.py
Restart=always
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
systemctl enable "$SERVICE_SYNC"
systemctl start  "$SERVICE_SYNC"

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    systemctl enable "$SERVICE_UI"
    systemctl start  "$SERVICE_UI"
    # Open firewall for chosen port only — NOT port 80
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow "$UI_PORT/tcp" --comment "gitsub webui" >/dev/null 2>&1 || true
        info "Firewall: opened port $UI_PORT"
    fi
fi
success "Services started"

# ── Certbot / nginx ────────────────────────────
if [ "$HAS_SSL" = "certbot" ]; then
    info "Configuring nginx + Certbot for $SSL_DOMAIN..."

    # Remove any conflicting nginx config for this domain
    CONFLICTS=$(grep -rl "server_name.*$SSL_DOMAIN" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v xui-webui || true)
    [ -n "$CONFLICTS" ] && echo "$CONFLICTS" | xargs rm -f && info "Removed conflicting nginx configs"

    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name $SSL_DOMAIN;

    location / {
        proxy_pass           http://127.0.0.1:$UI_PORT;
        proxy_set_header     Host \$host;
        proxy_set_header     X-Real-IP \$remote_addr;
        proxy_set_header     X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header     X-Forwarded-Proto \$scheme;
        proxy_read_timeout   60;
        proxy_http_version   1.1;
        proxy_buffering      off;
    }
}
EOF
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/xui-webui
    nginx -t -q && systemctl reload nginx
    success "Nginx configured"

    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow 80/tcp  --comment "gitsub certbot" >/dev/null 2>&1 || true
        ufw allow 443/tcp --comment "gitsub ssl"     >/dev/null 2>&1 || true
    fi

    certbot --nginx -d "$SSL_DOMAIN" --non-interactive --agree-tos -m "$SSL_EMAIL" \
        && success "SSL certificate installed" \
        || warn "Certbot failed — run: certbot --nginx -d $SSL_DOMAIN"

    # Restore proxy headers if certbot dropped them
    grep -q "X-Forwarded-Proto" "$NGINX_CONF" || \
        sed -i 's|proxy_pass.*http://127.*|&\n        proxy_set_header     X-Forwarded-Proto $scheme;|' "$NGINX_CONF" 2>/dev/null || true
    nginx -t -q && systemctl reload nginx 2>/dev/null || true

    # Save domain to config for status display
    python3 -c "
import json
with open('$INSTALL_DIR/config.json') as f: c=json.load(f)
c['ssl_domain']='$SSL_DOMAIN'
with open('$INSTALL_DIR/config.json','w') as f: json.dump(c,f,indent=2)
" 2>/dev/null || true
fi

# ── Done ───────────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║   Install complete!                       ║${RESET}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${CYAN}Installed to:${RESET}  $INSTALL_DIR"
echo ""

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    echo -e "  ${CYAN}Web UI access:${RESET}"
    echo -e "    http://${SERVER_IP}:${UI_PORT}"
    [ -n "$SSL_DOMAIN" ] && echo -e "    http://${SSL_DOMAIN}:${UI_PORT}    (domain)"
    echo ""
fi

echo -e "  Type ${CYAN}gitsub${RESET} for the interactive menu."
echo ""
