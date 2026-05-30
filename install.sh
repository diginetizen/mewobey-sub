#!/bin/bash
# ══════════════════════════════════════════════
#  gitsub installer v2
#  Installs to /opt/xui-subsync
# ══════════════════════════════════════════════

set -e

INSTALL_DIR="/opt/xui-subsync"
SERVICE_SYNC="xui-subsync"
SERVICE_UI="xui-webui"
NGINX_CONF="/etc/nginx/sites-available/xui-webui"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${CYAN}[info]${RESET} $*"; }
success() { echo -e "${GREEN}[ok]${RESET}   $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET} $*"; }
error()   { echo -e "${RED}[err]${RESET}  $*"; }

echo ""
echo -e "${CYAN}══════════════════════════════════════════${RESET}"
echo -e "${CYAN}   gitsub — XUI Subscription Sync         ${RESET}"
echo -e "${CYAN}══════════════════════════════════════════${RESET}"
echo ""

# ─────────────────────────────────────────
# 1. Panel info
# ─────────────────────────────────────────

echo -e "${YELLOW}── Panel ─────────────────────────────${RESET}"
read -rp "  Panel URL (e.g. https://panel.example.com): " PANEL_URL
read -rp "  API Bearer Token: " API_TOKEN

# ─────────────────────────────────────────
# 2. GitHub repo
# ─────────────────────────────────────────

echo ""
echo -e "${YELLOW}── GitHub Repository ─────────────────${RESET}"
read -rp "  GitHub username: " GITHUB_USER
read -rp "  GitHub repo name: " GITHUB_REPO
read -rp "  Default branch (default: main): " GITHUB_BRANCH
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

# ─────────────────────────────────────────
# 3. Deploy method
# ─────────────────────────────────────────

echo ""
echo -e "${YELLOW}── Deploy Method ─────────────────────${RESET}"
echo "  How should gitsub push to GitHub?"
echo "  [1] Personal Access Token (HTTPS)  — easiest"
echo "  [2] SSH Key                        — no token stored"
echo ""
read -rp "  Choose [1/2]: " DEPLOY_CHOICE

DEPLOY_METHOD="token"
GITHUB_TOKEN=""
SSH_KEY_PATH="$HOME/.ssh/gitsub_deploy"

if [ "$DEPLOY_CHOICE" = "2" ]; then
    DEPLOY_METHOD="ssh"
    echo ""
    echo -e "${YELLOW}── SSH Deploy Key ────────────────────${RESET}"
    echo "  Do you already have an SSH key for this repo?"
    read -rp "  [y/n]: " HAS_KEY

    if [ "$HAS_KEY" = "y" ]; then
        read -rp "  Path to private key (default: ~/.ssh/id_rsa): " SSH_KEY_PATH
        SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"
        if [ ! -f "$SSH_KEY_PATH" ]; then
            error "Key not found at $SSH_KEY_PATH"
            exit 1
        fi
        success "Using existing key: $SSH_KEY_PATH"
    else
        info "Generating new ED25519 deploy key..."
        ssh-keygen -t ed25519 -C "gitsub-deploy" -f "$SSH_KEY_PATH" -N ""
        success "Key created: $SSH_KEY_PATH"
        echo ""
        echo -e "${YELLOW}══ ACTION REQUIRED ════════════════════════════════${RESET}"
        echo "  Add this public key to your GitHub repo as a Deploy Key:"
        echo "  (Settings → Deploy keys → Add deploy key → Allow write access)"
        echo ""
        echo -e "${CYAN}  Public key:${RESET}"
        echo "  ┌──────────────────────────────────────────────────"
        cat "$SSH_KEY_PATH.pub" | sed 's/^/  │ /'
        echo "  └──────────────────────────────────────────────────"
        echo ""
        echo -e "  Deploy key page:"
        echo -e "  ${CYAN}https://github.com/$GITHUB_USER/$GITHUB_REPO/settings/keys/new${RESET}"
        echo ""
        read -rp "  Press ENTER once you've added the key to GitHub..."
    fi

    # Configure SSH to use this key for github.com
    SSH_CONFIG="$HOME/.ssh/config"
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"

    # Check if config for gitsub already exists
    if ! grep -q "Host github-gitsub" "$SSH_CONFIG" 2>/dev/null; then
        cat >> "$SSH_CONFIG" <<EOF

Host github-gitsub
    HostName github.com
    User git
    IdentityFile $SSH_KEY_PATH
    IdentitiesOnly yes
EOF
        success "SSH config updated: $SSH_CONFIG"
    fi

    # Test SSH connection
    info "Testing SSH connection to GitHub..."
    set +e
    ssh -o StrictHostKeyChecking=no -T git@github.com 2>&1 | grep -q "successfully authenticated"
    SSH_OK=$?
    set -e
    if [ $SSH_OK -eq 0 ]; then
        success "SSH connection OK"
    else
        warn "Could not verify SSH connection. Check your deploy key."
    fi

else
    echo ""
    read -rp "  GitHub Personal Access Token: " GITHUB_TOKEN
fi

# ─────────────────────────────────────────
# 4. Git identity
# ─────────────────────────────────────────

echo ""
echo -e "${YELLOW}── Git Identity (for commits) ────────${RESET}"
read -rp "  Git commit email: " GIT_EMAIL
read -rp "  Git commit name (default: gitsub-bot): " GIT_NAME
GIT_NAME="${GIT_NAME:-gitsub-bot}"

# ─────────────────────────────────────────
# 5. Web UI
# ─────────────────────────────────────────

echo ""
echo -e "${YELLOW}── Web UI ────────────────────────────${RESET}"
read -rp "  Enable Web Dashboard? [y/n] (default: y): " ENABLE_UI
ENABLE_UI="${ENABLE_UI:-y}"

UI_PORT=2086
ENABLE_NGINX="n"
DOMAIN=""

if [ "$ENABLE_UI" = "y" ]; then
    read -rp "  Web UI port (default: 2086): " UI_PORT
    UI_PORT="${UI_PORT:-2086}"

    read -rp "  Set up Nginx reverse proxy? [y/n] (default: n): " ENABLE_NGINX
    if [ "$ENABLE_NGINX" = "y" ]; then
        read -rp "  Domain name (e.g. sub.example.com): " DOMAIN
    fi
fi

# ─────────────────────────────────────────
# 6. Sync interval
# ─────────────────────────────────────────

echo ""
echo -e "${YELLOW}── Sync Interval ─────────────────────${RESET}"
echo "  Common values: 21600=6h  3600=1h  300=5m  120=2m"
read -rp "  Interval in seconds (default: 21600): " INTERVAL
INTERVAL="${INTERVAL:-21600}"

# ─────────────────────────────────────────
# 7. Install system packages
# ─────────────────────────────────────────

echo ""
info "Installing system packages..."
apt-get update -qq
PKGS="python3 python3-venv python3-pip git"
[ "$ENABLE_NGINX" = "y" ] && PKGS="$PKGS nginx"
apt-get install -y $PKGS -qq
success "System packages installed"

# ─────────────────────────────────────────
# 8. Copy project files
# ─────────────────────────────────────────

info "Setting up $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/subs" "$INSTALL_DIR/logs"

# Copy files (works whether run from clone or extracted archive)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in update.py webui.py requirements.txt uninstall.sh; do
    [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
done

# Copy existing subs if any
[ -d "$SCRIPT_DIR/subs" ] && cp -n "$SCRIPT_DIR/subs/"* "$INSTALL_DIR/subs/" 2>/dev/null || true

# ─────────────────────────────────────────
# 9. Python venv
# ─────────────────────────────────────────

info "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
success "Python venv ready"

# ─────────────────────────────────────────
# 10. Git init / config
# ─────────────────────────────────────────

info "Configuring git..."
git config --global user.email "$GIT_EMAIL"
git config --global user.name "$GIT_NAME"

cd "$INSTALL_DIR"

if [ ! -d .git ]; then
    git init
    git branch -M "$GITHUB_BRANCH"
fi

# Set remote
if [ "$DEPLOY_METHOD" = "ssh" ]; then
    REMOTE_URL="git@github-gitsub:$GITHUB_USER/$GITHUB_REPO.git"
else
    REMOTE_URL="https://$GITHUB_TOKEN@github.com/$GITHUB_USER/$GITHUB_REPO.git"
fi

git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

# Try initial fetch
info "Fetching from GitHub..."
set +e
git fetch origin "$GITHUB_BRANCH" --quiet 2>/dev/null
FETCH_OK=$?
set -e

if [ $FETCH_OK -eq 0 ]; then
    git reset --hard "origin/$GITHUB_BRANCH" --quiet
    success "Synced with remote branch"
else
    warn "Could not fetch remote (new repo or no commits yet). Will push on first sync."
    # Ensure subs dir is tracked
    touch "$INSTALL_DIR/subs/.gitkeep"
    git add subs/ 2>/dev/null || true
fi

# Add .gitignore
cat > .gitignore <<'GITIGNORE'
config.json
submap.json
venv/
logs/
*.pyc
__pycache__/
GITIGNORE

success "Git configured"

# ─────────────────────────────────────────
# 11. Config file
# ─────────────────────────────────────────

info "Writing config.json..."
cat > "$INSTALL_DIR/config.json" <<EOF
{
  "panel_url":      "$PANEL_URL",
  "api_token":      "$API_TOKEN",

  "github_user":    "$GITHUB_USER",
  "github_repo":    "$GITHUB_REPO",
  "github_branch":  "$GITHUB_BRANCH",

  "deploy_method":  "$DEPLOY_METHOD",
  "github_token":   "$GITHUB_TOKEN",

  "filename_length": 32,
  "sync_interval":   $INTERVAL
}
EOF
chmod 600 "$INSTALL_DIR/config.json"
success "config.json written (permissions: 600)"

# ─────────────────────────────────────────
# 12. gitsub CLI command
# ─────────────────────────────────────────

info "Installing 'gitsub' CLI command..."
cat > /usr/local/bin/gitsub <<EOF
#!/bin/bash
cd $INSTALL_DIR
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/update.py "\$@"
EOF
chmod +x /usr/local/bin/gitsub
success "CLI ready: type 'gitsub' anywhere"

# ─────────────────────────────────────────
# 13. Systemd — sync daemon
# ─────────────────────────────────────────

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

# ─────────────────────────────────────────
# 14. Systemd — web UI
# ─────────────────────────────────────────

if [ "$ENABLE_UI" = "y" ]; then
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
systemctl start "$SERVICE_SYNC"

if [ "$ENABLE_UI" = "y" ]; then
    systemctl enable "$SERVICE_UI"
    systemctl start "$SERVICE_UI"
fi

success "Systemd services started"

# ─────────────────────────────────────────
# 15. Nginx
# ─────────────────────────────────────────

if [ "$ENABLE_NGINX" = "y" ] && [ -n "$DOMAIN" ]; then
    info "Configuring Nginx for $DOMAIN..."
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass         http://127.0.0.1:$UI_PORT;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60;
    }
}
EOF
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/xui-webui
    nginx -t && systemctl reload nginx
    success "Nginx configured for $DOMAIN"
    echo ""
    echo -e "  ${CYAN}Optional: get SSL with certbot:${RESET}"
    echo -e "  apt install certbot python3-certbot-nginx"
    echo -e "  certbot --nginx -d $DOMAIN"
fi

# ─────────────────────────────────────────
# Done
# ─────────────────────────────────────────

echo ""
echo -e "${GREEN}══════════════════════════════════════════${RESET}"
echo -e "${GREEN}   Install complete!                       ${RESET}"
echo -e "${GREEN}══════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${CYAN}Installed to:${RESET}  $INSTALL_DIR"
echo -e "  ${CYAN}CLI command:${RESET}   gitsub help"
echo ""
echo -e "  ${CYAN}Quick commands:${RESET}"
echo "   gitsub sync              — run sync now"
echo "   gitsub status            — list all users"
echo "   gitsub lookup <email>    — find a user"
echo "   gitsub rotate <email>    — rotate URL"
echo ""
if [ "$ENABLE_UI" = "y" ]; then
    SERVER_IP=$(hostname -I | awk '{print $1}')
    if [ "$ENABLE_NGINX" = "y" ] && [ -n "$DOMAIN" ]; then
        echo -e "  ${CYAN}Web UI:${RESET}  http://$DOMAIN"
    else
        echo -e "  ${CYAN}Web UI:${RESET}  http://$SERVER_IP:$UI_PORT"
    fi
    echo ""
fi
echo -e "  ${CYAN}Logs:${RESET}"
echo "   journalctl -u $SERVICE_SYNC -f"
echo "   tail -f $INSTALL_DIR/logs/sync.log"
echo ""
