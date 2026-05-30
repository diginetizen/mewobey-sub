#!/bin/bash
# ══════════════════════════════════════════════
#  gitsub installer v3
#  Installs to /opt/xui-subsync
# ══════════════════════════════════════════════

set -e

INSTALL_DIR="/opt/xui-subsync"
SERVICE_SYNC="xui-subsync"
SERVICE_UI="xui-webui"
NGINX_CONF="/etc/nginx/sites-available/xui-webui"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; CYAN="\033[0;36m"; RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"
info()    { echo -e "${CYAN}[info]${RESET} $*"; }
success() { echo -e "${GREEN}[ok]${RESET}   $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET} $*"; }
error()   { echo -e "${RED}[err]${RESET}  $*"; exit 1; }
ask()     { echo -e "${BOLD}$*${RESET}"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}║   gitsub — XUI Subscription Sync v3      ║${RESET}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ─────────────────────────────────────────
# 1. Panel
# ─────────────────────────────────────────
echo -e "${YELLOW}── 3x-ui Panel ───────────────────────────${RESET}"
echo "  Enter your 3x-ui panel's base URL including port."
echo "  This is the URL you open in a browser to reach the panel."
echo "  Example: https://panel.example.com:2053"
echo "           http://1.2.3.4:54321"
echo ""
read -rp "  Panel API base URL: " PANEL_API_URL
read -rp "  API Bearer Token: " API_TOKEN
echo ""

# ─────────────────────────────────────────
# 2. GitHub repo
# ─────────────────────────────────────────
echo -e "${YELLOW}── GitHub Repository ─────────────────────${RESET}"
read -rp "  GitHub username: " GITHUB_USER
read -rp "  GitHub repo name: " GITHUB_REPO
read -rp "  Branch (default: main): " GITHUB_BRANCH
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
echo ""

# ─────────────────────────────────────────
# 3. Deploy method
# ─────────────────────────────────────────
echo -e "${YELLOW}── Deploy Method ─────────────────────────${RESET}"
echo "  How should gitsub push to GitHub?"
echo "  [1] Personal Access Token (HTTPS)  — easiest"
echo "  [2] SSH Deploy Key                 — more secure, no token stored"
echo ""
read -rp "  Choose [1/2] (default: 1): " DEPLOY_CHOICE
DEPLOY_CHOICE="${DEPLOY_CHOICE:-1}"

DEPLOY_METHOD="token"
GITHUB_TOKEN=""
SSH_KEY_PATH="/root/.ssh/gitsub_deploy"

if [ "$DEPLOY_CHOICE" = "2" ]; then
    DEPLOY_METHOD="ssh"
    echo ""
    echo -e "${YELLOW}── SSH Deploy Key ─────────────────────────${RESET}"
    echo "  Do you already have an SSH key added to this repo?"
    echo "  [1] Yes — I have a key already"
    echo "  [2] No  — generate one for me"
    echo ""
    read -rp "  Choose [1/2] (default: 2): " HAS_KEY
    HAS_KEY="${HAS_KEY:-2}"

    if [ "$HAS_KEY" = "1" ]; then
        echo "  How do you want to provide your existing key?"
        echo "  [1] Give the file path  (e.g. /root/.ssh/id_rsa)"
        echo "  [2] Paste the private key content now"
        echo ""
        read -rp "  Choose [1/2] (default: 1): " KEY_INPUT_METHOD
        KEY_INPUT_METHOD="${KEY_INPUT_METHOD:-1}"

        if [ "$KEY_INPUT_METHOD" = "2" ]; then
            info "Paste your private key below. Press Ctrl+D on an empty line when done."
            echo ""
            mkdir -p /root/.ssh && chmod 700 /root/.ssh
            cat > "$SSH_KEY_PATH"
            chmod 600 "$SSH_KEY_PATH"
            ssh-keygen -y -f "$SSH_KEY_PATH" > "$SSH_KEY_PATH.pub" 2>/dev/null || true
            success "Key stored at $SSH_KEY_PATH"
        else
            read -rp "  Path to private key (default: /root/.ssh/id_rsa): " SSH_KEY_PATH
            SSH_KEY_PATH="${SSH_KEY_PATH:-/root/.ssh/id_rsa}"
            [ ! -f "$SSH_KEY_PATH" ] && error "Key not found at $SSH_KEY_PATH"
            chmod 600 "$SSH_KEY_PATH"
            success "Using existing key: $SSH_KEY_PATH"
        fi
        SHOW_PUBKEY="n"
    else
        info "Generating new ED25519 deploy key at $SSH_KEY_PATH ..."
        mkdir -p /root/.ssh && chmod 700 /root/.ssh
        rm -f "$SSH_KEY_PATH" "$SSH_KEY_PATH.pub"
        ssh-keygen -t ed25519 -C "gitsub-deploy@$(hostname)" -f "$SSH_KEY_PATH" -N ""
        success "Key generated: $SSH_KEY_PATH"
        SHOW_PUBKEY="y"
    fi

    # Write SSH config so git uses this specific key for github.com
    SSH_CONFIG="/root/.ssh/config"
    mkdir -p /root/.ssh && chmod 700 /root/.ssh

    if grep -q "Host github-gitsub" "$SSH_CONFIG" 2>/dev/null; then
        sed -i '/Host github-gitsub/,+5d' "$SSH_CONFIG"
    fi

    cat >> "$SSH_CONFIG" <<SSHEOF

Host github-gitsub
    HostName github.com
    User git
    IdentityFile $SSH_KEY_PATH
    IdentitiesOnly yes
    StrictHostKeyChecking no
SSHEOF
    chmod 600 "$SSH_CONFIG"
    success "SSH config written: $SSH_CONFIG"

    # Only show deploy key instructions for newly generated keys
    if [ "$SHOW_PUBKEY" = "y" ]; then
        echo ""
        echo -e "${YELLOW}╔══ ACTION REQUIRED ═══════════════════════════════════╗${RESET}"
        echo -e "${YELLOW}║  Add this public key to your GitHub repo              ║${RESET}"
        echo -e "${YELLOW}║  → Settings → Deploy keys → Add deploy key            ║${RESET}"
        echo -e "${YELLOW}║  → Check: Allow write access                          ║${RESET}"
        echo -e "${YELLOW}╚══════════════════════════════════════════════════════╝${RESET}"
        echo ""
        echo -e "${CYAN}  Public key to paste:${RESET}"
        echo "  ┌─────────────────────────────────────────────────────"
        cat "$SSH_KEY_PATH.pub" | sed 's/^/  │ /'
        echo "  └─────────────────────────────────────────────────────"
        echo ""
        echo -e "  ${CYAN}Click here to add it:${RESET}"
        echo -e "  https://github.com/$GITHUB_USER/$GITHUB_REPO/settings/keys/new"
        echo ""
        read -rp "  Press ENTER after you've added the key to GitHub and enabled write access..."
    fi

    # Test SSH connection
    info "Testing SSH connection to GitHub..."
    set +e
    SSH_TEST=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no -T git@github.com 2>&1)
    SSH_OK=$?
    set -e
    if echo "$SSH_TEST" | grep -q "successfully authenticated"; then
        success "SSH connection to GitHub: OK"
    else
        warn "SSH test: $SSH_TEST"
        warn "If this fails, ensure the key has write access on GitHub."
        read -rp "  Press ENTER to continue anyway, or Ctrl+C to abort..."
    fi

else
    echo ""
    read -rp "  GitHub Personal Access Token (needs repo scope): " GITHUB_TOKEN
fi

echo ""

# ─────────────────────────────────────────
# 4. Web UI
# ─────────────────────────────────────────
echo -e "${YELLOW}── Web Dashboard ─────────────────────────${RESET}"
read -rp "  Enable web dashboard? [y/n] (default: y): " ENABLE_UI
ENABLE_UI="${ENABLE_UI:-y}"

UI_PORT=2086
ENABLE_NGINX="n"
DOMAIN=""
INSTALL_CERT="n"
UI_USER=""
UI_PASS=""

if [ "$ENABLE_UI" = "y" ]; then
    read -rp "  Web UI port (default: 2086): " UI_PORT
    UI_PORT="${UI_PORT:-2086}"

    echo ""
    echo -e "${YELLOW}── Web UI Login ───────────────────────────${RESET}"
    read -rp "  Dashboard username: " UI_USER
    read -rsp "  Dashboard password: " UI_PASS
    echo ""

    echo ""
    echo -e "${YELLOW}── Nginx + Domain (optional) ─────────────${RESET}"
    read -rp "  Set up Nginx reverse proxy with a domain? [y/n] (default: n): " ENABLE_NGINX
    ENABLE_NGINX="${ENABLE_NGINX:-n}"

    if [ "$ENABLE_NGINX" = "y" ]; then
        read -rp "  Domain name (e.g. sub.example.com): " DOMAIN
        read -rp "  Also install SSL certificate with Certbot? [y/n] (default: y): " INSTALL_CERT
        INSTALL_CERT="${INSTALL_CERT:-y}"
    fi
fi

echo ""

# ─────────────────────────────────────────
# 5. Sync interval
# ─────────────────────────────────────────
echo -e "${YELLOW}── Sync Interval ─────────────────────────${RESET}"
echo "  How often to sync with the panel?"
echo "  [1] 6 hours  (21600s) — recommended for production"
echo "  [2] 1 hour   (3600s)"
echo "  [3] 5 minutes (300s)  — good for testing"
echo "  [4] Custom"
echo ""
read -rp "  Choose [1/2/3/4] (default: 1): " INTERVAL_CHOICE
INTERVAL_CHOICE="${INTERVAL_CHOICE:-1}"

case "$INTERVAL_CHOICE" in
    1) INTERVAL=21600 ;;
    2) INTERVAL=3600  ;;
    3) INTERVAL=300   ;;
    4) read -rp "  Enter interval in seconds: " INTERVAL ;;
    *) INTERVAL=21600 ;;
esac

echo ""
info "Summary:"
echo "   Panel API URL : $PANEL_API_URL"
echo "   GitHub repo : $GITHUB_USER/$GITHUB_REPO ($GITHUB_BRANCH)"
echo "   Deploy via  : $DEPLOY_METHOD"
echo "   Web UI      : $ENABLE_UI (port $UI_PORT)"
[ -n "$DOMAIN" ] && echo "   Domain      : $DOMAIN"
echo "   Sync every  : ${INTERVAL}s"
echo ""
read -rp "  Proceed with installation? [y/n] (default: y): " PROCEED
PROCEED="${PROCEED:-y}"
[ "$PROCEED" != "y" ] && echo "Aborted." && exit 0

echo ""

# ─────────────────────────────────────────
# 6. System packages
# ─────────────────────────────────────────
info "Installing system packages..."
apt-get update -qq
PKGS="python3 python3-venv python3-pip git"
[ "$ENABLE_NGINX" = "y" ] && PKGS="$PKGS nginx"
[ "$INSTALL_CERT" = "y" ] && PKGS="$PKGS certbot python3-certbot-nginx"
apt-get install -y $PKGS -qq
success "Packages installed"

# ─────────────────────────────────────────
# 7. Copy project files
# ─────────────────────────────────────────
info "Setting up $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR/subs" "$INSTALL_DIR/logs"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in update.py webui.py requirements.txt uninstall.sh; do
    [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
done
[ -d "$SCRIPT_DIR/subs" ] && cp -n "$SCRIPT_DIR/subs/"* "$INSTALL_DIR/subs/" 2>/dev/null || true
success "Files copied to $INSTALL_DIR"

# ─────────────────────────────────────────
# 8. Python venv
# ─────────────────────────────────────────
info "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
success "Python venv ready"

# ─────────────────────────────────────────
# 9. Git setup
# ─────────────────────────────────────────
info "Configuring git..."
# Use GitHub username as git identity — no need to ask user separately
git config --global user.email "${GITHUB_USER}@users.noreply.github.com"
git config --global user.name "$GITHUB_USER"
# Suppress branch name warning — always use the branch the user specified
git config --global init.defaultBranch "$GITHUB_BRANCH"

cd "$INSTALL_DIR"

if [ ! -d .git ]; then
    git init -q
    git branch -M "$GITHUB_BRANCH" 2>/dev/null || true
fi

# Set remote URL
if [ "$DEPLOY_METHOD" = "ssh" ]; then
    REMOTE_URL="git@github-gitsub:$GITHUB_USER/$GITHUB_REPO.git"
else
    REMOTE_URL="https://${GITHUB_TOKEN}@github.com/$GITHUB_USER/$GITHUB_REPO.git"
fi

git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

# .gitignore — keep secrets, runtime files, and OS junk out of repo
cat > .gitignore <<'GITIGNORE'
# gitsub secrets & runtime — NEVER push these
config.json
submap.json

# Python
venv/
.venv/
*.pyc
*.pyo
*.pyd
__pycache__/
*.egg-info/
dist/
build/
.eggs/
pip-wheel-metadata/

# Logs
logs/
*.log

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
Thumbs.db
desktop.ini

# Editor
.vscode/
.idea/
*.swp
*.swo
*~
.env
.env.*
GITIGNORE

# Try to sync with remote
info "Connecting to GitHub..."
set +e
git fetch origin "$GITHUB_BRANCH" --quiet 2>/tmp/gitsub_fetch_err
FETCH_OK=$?
set -e

if [ $FETCH_OK -eq 0 ]; then
    git reset --hard "origin/$GITHUB_BRANCH" --quiet
    success "Synced with remote repo"
else
    FETCH_ERR=$(cat /tmp/gitsub_fetch_err)
    warn "Could not fetch from remote: $FETCH_ERR"
    warn "This is OK for a new/empty repo — will push on first sync."
    touch "$INSTALL_DIR/subs/.gitkeep"
    git add subs/ 2>/dev/null || true
fi

success "Git configured"

# ─────────────────────────────────────────
# 10. Write config.json
# ─────────────────────────────────────────
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

  "filename_length": 32,
  "sync_interval":   $INTERVAL
}
EOF
chmod 600 "$INSTALL_DIR/config.json"
success "config.json written (chmod 600)"

# ─────────────────────────────────────────
# 11. gitsub CLI
# ─────────────────────────────────────────
info "Installing 'gitsub' CLI command..."
cat > /usr/local/bin/gitsub <<EOF
#!/bin/bash
cd $INSTALL_DIR
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/update.py "\$@"
EOF
chmod +x /usr/local/bin/gitsub
success "CLI ready — type 'gitsub' from anywhere"

# ─────────────────────────────────────────
# 12. Systemd — sync daemon
# ─────────────────────────────────────────
info "Creating systemd service: $SERVICE_SYNC ..."
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

# ─────────────────────────────────────────
# 13. Systemd — web UI
# ─────────────────────────────────────────
if [ "$ENABLE_UI" = "y" ]; then
    info "Creating systemd service: $SERVICE_UI ..."
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

if [ "$ENABLE_UI" = "y" ]; then
    systemctl enable "$SERVICE_UI"
    systemctl start  "$SERVICE_UI"
    # Open firewall port if ufw is active
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow "$UI_PORT/tcp" --comment "gitsub webui" >/dev/null 2>&1 || true
        info "Firewall: opened port $UI_PORT"
    fi
fi

success "Systemd services started"

# ─────────────────────────────────────────
# 14. Nginx
# ─────────────────────────────────────────
if [ "$ENABLE_NGINX" = "y" ] && [ -n "$DOMAIN" ]; then
    info "Configuring Nginx for $DOMAIN ..."

    # Check for conflicting nginx configs that already use this domain name
    # This is what causes: "conflicting server name" warnings
    CONFLICT_FILES=$(grep -rl "server_name.*$DOMAIN" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v "xui-webui" || true)
    if [ -n "$CONFLICT_FILES" ]; then
        warn "Found existing nginx config(s) with server_name '$DOMAIN':"
        echo "$CONFLICT_FILES" | while read -r f; do warn "  $f"; done
        echo ""
        read -rp "  Remove conflicting config(s) to avoid warning? [y/n] (default: y): " REMOVE_CONFLICT
        REMOVE_CONFLICT="${REMOVE_CONFLICT:-y}"
        if [ "$REMOVE_CONFLICT" = "y" ]; then
            echo "$CONFLICT_FILES" | while read -r f; do
                rm -f "$f"
                info "Removed: $f"
            done
        fi
    fi
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass             http://127.0.0.1:$UI_PORT;
        proxy_set_header       Host \$host;
        proxy_set_header       X-Real-IP \$remote_addr;
        proxy_set_header       X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header       X-Forwarded-Proto \$scheme;
        proxy_read_timeout     60;
        proxy_http_version     1.1;
        proxy_set_header       Upgrade \$http_upgrade;
        proxy_set_header       Connection keep-alive;
    }
}
EOF
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/xui-webui
    nginx -t && systemctl reload nginx
    success "Nginx configured for $DOMAIN"

    # Open HTTP/HTTPS in firewall
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow 80/tcp  --comment "gitsub nginx" >/dev/null 2>&1 || true
        ufw allow 443/tcp --comment "gitsub nginx ssl" >/dev/null 2>&1 || true
    fi

    if [ "$INSTALL_CERT" = "y" ]; then
        info "Getting SSL certificate for $DOMAIN ..."
        certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" || \
            warn "Certbot failed — you can run it manually: certbot --nginx -d $DOMAIN"
        success "SSL certificate installed"
    fi
fi

# ─────────────────────────────────────────
# Done
# ─────────────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║   Install complete!                      ║${RESET}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${CYAN}Installed to:${RESET}   $INSTALL_DIR"
echo ""

if [ "$ENABLE_UI" = "y" ]; then
    if [ "$ENABLE_NGINX" = "y" ] && [ -n "$DOMAIN" ]; then
        echo -e "  ${CYAN}Web UI:${RESET}   http://${SERVER_IP}:${UI_PORT}"
        echo -e "            https://${DOMAIN}"
        echo -e "            http://${DOMAIN}"
    else
        echo -e "  ${CYAN}Web UI:${RESET}   http://${SERVER_IP}:${UI_PORT}"
        echo -e "            http://${SERVER_IP}"
    fi
    echo ""
fi

echo "  Type 'gitsub' for the interactive menu."
echo ""
