#!/bin/bash
# ══════════════════════════════════════════════
#  gitsub installer v4
#  Installs to /opt/xui-subsync
# ══════════════════════════════════════════════
set -e

# Show * for each character typed — for passwords and tokens
masked_input() {
    local prompt="$1"
    local result=""
    local char
    printf "%s" "$prompt" >&2
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' || "$char" == $'\b' ]]; then
            if [[ -n "$result" ]]; then
                result="${result%?}"
                printf '\b \b' >&2
            fi
        else
            result+="$char"
            printf '*' >&2
        fi
    done
    printf '\n' >&2
    printf '%s' "$result"
}

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
ACCESS_MODE="1"
DOMAIN=""
SSL_MODE="none"
SSL_CERT=""
SSL_KEY=""
SSL_EMAIL=""

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    read -rp "  Web UI port [2086]: " UI_PORT
    UI_PORT="${UI_PORT:-2086}"

    echo ""
    echo -e "${YELLOW}── Login ──────────────────────────────────${RESET}"
    read -rp "  Dashboard username [admin]: " UI_USER
    UI_USER="${UI_USER:-admin}"
    UI_PASS=$(masked_input "  Dashboard password: ")
    echo ""
    echo ""

    echo -e "${YELLOW}── Access Mode ────────────────────────────${RESET}"
    echo "  How do you want to reach the dashboard?"
    echo "  All options use port ${UI_PORT} only."
    echo ""
    echo "  [1] IP only          http://IP:${UI_PORT}"
    echo "  [2] IP + domain      http://IP:${UI_PORT}  +  http://domain:${UI_PORT}"
    echo "  [3] IP + domain + HTTPS  (all of the above + https://domain:${UI_PORT})"
    echo "  [4] IP + HTTPS via cert files   https://IP:${UI_PORT}"
    echo ""
    read -rp "  Choose [1-4] (default 1): " ACCESS_MODE
    ACCESS_MODE="${ACCESS_MODE:-1}"
    echo ""

    if [[ "$ACCESS_MODE" =~ ^[23]$ ]]; then
        echo -e "${YELLOW}── Domain ─────────────────────────────────${RESET}"
        read -rp "  Domain name (e.g. sub.example.com): " DOMAIN
        [ -z "$DOMAIN" ] && error "Domain name required for this access mode"
        echo ""
    fi

    if [ "$ACCESS_MODE" = "3" ]; then
        echo -e "${YELLOW}── SSL Certificate ────────────────────────${RESET}"
        echo "  How do you want to get the SSL certificate?"
        echo "  [1] Certbot / Let's Encrypt  (auto, free)"
        echo "  [2] I have cert files already"
        echo "  [3] I'll add SSL later"
        echo ""
        read -rp "  Choose [1-3] (default 1): " SSL_SRC
        SSL_SRC="${SSL_SRC:-1}"
        echo ""

        if [ "$SSL_SRC" = "1" ]; then
            SSL_MODE="certbot"
            read -rp "  Email for Let's Encrypt notices [admin@${DOMAIN}]: " SSL_EMAIL
            SSL_EMAIL="${SSL_EMAIL:-admin@${DOMAIN}}"
        elif [ "$SSL_SRC" = "2" ]; then
            SSL_MODE="manual"
            read -rp "  Path to certificate (fullchain.pem): " SSL_CERT
            read -rp "  Path to private key  (privkey.pem): " SSL_KEY
            [ ! -f "$SSL_CERT" ] && error "Certificate not found: $SSL_CERT"
            [ ! -f "$SSL_KEY"  ] && error "Key not found: $SSL_KEY"
            success "Cert files accepted"
        else
            SSL_MODE="later"
            warn "SSL skipped — you can add it later from the gitsub menu (option 8)"
        fi
    fi

    if [ "$ACCESS_MODE" = "4" ]; then
        echo -e "${YELLOW}── SSL Certificate ────────────────────────${RESET}"
        echo "  [1] Cert files (path on this server)"
        echo "  [2] Paste/copy cert content now"
        echo ""
        read -rp "  Choose [1/2] (default 1): " CERT_SRC
        CERT_SRC="${CERT_SRC:-1}"
        echo ""

        if [ "$CERT_SRC" = "2" ]; then
            mkdir -p "$INSTALL_DIR"
            SSL_CERT="$INSTALL_DIR/ssl/cert.pem"
            SSL_KEY="$INSTALL_DIR/ssl/key.pem"
            mkdir -p "$INSTALL_DIR/ssl"
            echo "  Paste your certificate (fullchain.pem). Press Ctrl+D when done:"
            echo ""
            cat > "$SSL_CERT"
            echo ""
            echo "  Paste your private key (privkey.pem). Press Ctrl+D when done:"
            echo ""
            cat > "$SSL_KEY"
            chmod 600 "$SSL_KEY"
            success "Cert saved to $INSTALL_DIR/ssl/"
        else
            read -rp "  Path to certificate (fullchain.pem): " SSL_CERT
            read -rp "  Path to private key  (privkey.pem): " SSL_KEY
            [ ! -f "$SSL_CERT" ] && error "Certificate not found: $SSL_CERT"
            [ ! -f "$SSL_KEY"  ] && error "Key not found: $SSL_KEY"
            success "Cert files accepted"
        fi
        SSL_MODE="manual"
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
    case "$ACCESS_MODE" in
        1) echo "   Access      : IP only (http)" ;;
        2) echo "   Access      : IP + domain ($DOMAIN) — HTTP" ;;
        3) echo "   Access      : IP + domain ($DOMAIN) + HTTPS ($SSL_MODE)" ;;
        4) echo "   Access      : IP with HTTPS (cert files)" ;;
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
# nginx needed for domain access or certbot
[[ "$ACCESS_MODE" =~ ^[23]$ ]] && PKGS="$PKGS nginx"
[ "$SSL_MODE" = "certbot" ] && PKGS="$PKGS certbot python3-certbot-nginx"
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
  "domain":         "$DOMAIN",
  "access_mode":    "$ACCESS_MODE",
  "ssl_mode":       "$SSL_MODE",
  "ssl_cert":       "$SSL_CERT",
  "ssl_key":        "$SSL_KEY",
  "ssl_email":      "$SSL_EMAIL",

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

# ── Domain / nginx / SSL setup ─────────────────
# Helper: write nginx config that proxies domain to UI_PORT (never touches port 80 for dashboard)
write_nginx_conf() {
    local domain="$1"
    # Remove conflicting configs for this domain
    CONFLICTS=$(grep -rl "server_name.*${domain}" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v xui-webui || true)
    [ -n "$CONFLICTS" ] && echo "$CONFLICTS" | xargs rm -f && info "Removed conflicting nginx configs"

    cat > "$NGINX_CONF" <<NGINXEOF
server {
    listen 80;
    server_name ${domain};

    location / {
        proxy_pass           http://127.0.0.1:${UI_PORT};
        proxy_set_header     Host \$host;
        proxy_set_header     X-Real-IP \$remote_addr;
        proxy_set_header     X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header     X-Forwarded-Proto \$scheme;
        proxy_read_timeout   60;
        proxy_http_version   1.1;
        proxy_buffering      off;
    }
}
NGINXEOF
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/xui-webui
    nginx -t -q && systemctl reload nginx
    success "Nginx: domain ${domain} → port ${UI_PORT}"
}

# Mode 2: domain with HTTP only — just nginx, no SSL
if [ "$ACCESS_MODE" = "2" ] && [ -n "$DOMAIN" ]; then
    info "Setting up nginx for $DOMAIN (HTTP)..."
    write_nginx_conf "$DOMAIN"
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow 80/tcp --comment "gitsub nginx" >/dev/null 2>&1 || true
    fi
fi

# Mode 3: domain with HTTPS
if [ "$ACCESS_MODE" = "3" ] && [ -n "$DOMAIN" ]; then
    info "Setting up nginx + SSL for $DOMAIN..."
    write_nginx_conf "$DOMAIN"

    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow 80/tcp  --comment "gitsub nginx"   >/dev/null 2>&1 || true
        ufw allow 443/tcp --comment "gitsub nginx ssl" >/dev/null 2>&1 || true
    fi

    if [ "$SSL_MODE" = "certbot" ]; then
        certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$SSL_EMAIL"             && success "SSL certificate installed — https://${DOMAIN} active"             || warn "Certbot failed — run manually: certbot --nginx -d $DOMAIN"
        # Ensure proxy headers survived certbot editing the config
        grep -q "X-Forwarded-Proto" "$NGINX_CONF" ||             sed -i "s|proxy_pass.*127.*|&
        proxy_set_header X-Forwarded-Proto \$scheme;|" "$NGINX_CONF" 2>/dev/null || true
        nginx -t -q && systemctl reload nginx 2>/dev/null || true

    elif [ "$SSL_MODE" = "manual" ]; then
        # Add SSL server block (443) to existing nginx config
        cat >> "$NGINX_CONF" <<SSLEOF

server {
    listen 443 ssl;
    server_name ${DOMAIN};
    ssl_certificate     ${SSL_CERT};
    ssl_certificate_key ${SSL_KEY};

    location / {
        proxy_pass           http://127.0.0.1:${UI_PORT};
        proxy_set_header     Host \$host;
        proxy_set_header     X-Real-IP \$remote_addr;
        proxy_set_header     X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header     X-Forwarded-Proto https;
        proxy_read_timeout   60;
        proxy_http_version   1.1;
        proxy_buffering      off;
    }
}
SSLEOF
        nginx -t -q && systemctl reload nginx
        success "SSL configured via cert files for $DOMAIN"
    fi
fi

# Mode 4: HTTPS directly on UI_PORT via Flask SSL — no nginx
# (webui.py reads ssl_cert/ssl_key from config and starts with ssl_context)
[ "$ACCESS_MODE" = "4" ] && [ -n "$SSL_CERT" ] && success "SSL cert configured — webui will serve HTTPS on port $UI_PORT"

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
    echo -e "  ${CYAN}Web UI — all URLs that work:${RESET}"
    # IP direct — always available
    if [ "$ACCESS_MODE" = "4" ] && [ -n "$SSL_CERT" ]; then
        echo -e "    https://${SERVER_IP}:${UI_PORT}    (IP, HTTPS)"
    else
        echo -e "    http://${SERVER_IP}:${UI_PORT}     (IP, HTTP)"
    fi
    # Domain HTTP — modes 2 and 3
    if [[ "$ACCESS_MODE" =~ ^[23]$ ]] && [ -n "$DOMAIN" ]; then
        echo -e "    http://${DOMAIN}:${UI_PORT}   (domain, HTTP)"
    fi
    # Domain HTTPS — mode 3 with SSL
    if [ "$ACCESS_MODE" = "3" ] && [ -n "$DOMAIN" ] && [ "$SSL_MODE" != "later" ]; then
        echo -e "    https://${DOMAIN}             (domain, HTTPS via port 443)"
    fi
    echo ""
fi

echo -e "  Type ${CYAN}gitsub${RESET} for the interactive menu."
echo ""
