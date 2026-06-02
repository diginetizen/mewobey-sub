#!/bin/bash
# ══════════════════════════════════════════════
#  gitsub installer v5
# ══════════════════════════════════════════════
set -e

# ── masked input: shows * per character ────────
masked_input() {
    local prompt="$1" result="" char
    printf "%s" "$prompt" >&2
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then break
        elif [[ "$char" == $'\x7f' || "$char" == $'\b' ]]; then
            if [[ -n "$result" ]]; then result="${result%?}"; printf '\b \b' >&2; fi
        else result+="$char"; printf '*' >&2; fi
    done
    printf '\n' >&2; printf '%s' "$result"
}

# ── confirm: returns 0 on y/Y/enter ────────────
confirm() {
    local prompt="${1:-Continue?}" ans
    read -rp "  $prompt [y/n] (default y): " ans
    ans="${ans:-y}"
    [[ "$ans" =~ ^[Yy] ]]
}

INSTALL_DIR="/opt/xui-subsync"
SERVICE_SYNC="xui-subsync"
SERVICE_UI="xui-webui"
NGINX_CONF="/etc/nginx/sites-available/xui-webui"

G="\033[0;32m"; Y="\033[1;33m"; C="\033[0;36m"; R="\033[0;31m"
B="\033[1m"; D="\033[2m"; RS="\033[0m"
info()    { echo -e "${C}[info]${RS} $*"; }
ok()      { echo -e "${G}[ ok]${RS} $*"; }
warn()    { echo -e "${Y}[warn]${RS} $*"; }
err()     { echo -e "${R}[ err]${RS} $*"; exit 1; }
section() { echo ""; echo -e "${Y}── $* $(printf '─%.0s' $(seq 1 $((42-${#1}))))${RS}"; echo ""; }
hint()    { echo -e "  ${G}→${RS} $*"; }       # green hints — clearly visible guidance
example() { echo -e "  ${D}   e.g. $*${RS}"; }  # dim indented examples

clear
echo ""
echo -e "${C}╔══════════════════════════════════════════╗${RS}"
echo -e "${C}║        gitsub  —  XUI Sub Sync v5        ║${RS}"
echo -e "${C}╚══════════════════════════════════════════╝${RS}"
echo ""

# ════════════════════════════════════════
# 1. PANEL
# ════════════════════════════════════════
section "3x-ui Panel"
echo "  Enter your panel's base URL in this format:"
echo ""
echo "    domain:port/pathurl     →  https://panel.example.com:2053/xPaTh"
echo "    domain:port             →  https://panel.example.com:2053"
echo "    ip:port/pathurl         →  http://1.2.3.4:54321/xPaTh"
echo "    ip:port                 →  http://1.2.3.4:54321"
echo ""
echo "  If your panel URL has a path after the port, include it."
echo "  If it doesn't, just use domain:port or ip:port."
echo ""
read -rp "  Panel base URL: " PANEL_API_URL
echo ""
hint "API token: Panel → Settings → Authentication → API token"
API_TOKEN=$(masked_input "  API token: ")
echo ""

# ════════════════════════════════════════
# 2. GITHUB
# ════════════════════════════════════════
section "GitHub Repository"
hint "Subscription files will be pushed here as raw text files."
hint "GitHub username: your account name, e.g. johndoe"
read -rp "  GitHub username: " GITHUB_USER
echo ""
hint "Repo name: the repository to push subscription files into."
hint "⚠  The repo MUST be public. If it is private, your users cannot"
hint "   download their subscription links — they will get a 404 error."
hint "Create one at: https://github.com/new  (set visibility to Public)"
read -rp "  Repository name: " GITHUB_REPO
echo ""
read -rp "  Branch [main]: " GITHUB_BRANCH
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
echo ""

# ════════════════════════════════════════
# 3. DEPLOY METHOD
# ════════════════════════════════════════
section "GitHub Deploy Method"
hint "How gitsub will push changes to your repository."
echo "  [1] Personal Access Token  — paste a token, easiest setup"
echo "  [2] SSH Deploy Key         — key-based, no token stored"
echo ""
read -rp "  Choose [1/2] (default 1): " DEPLOY_CHOICE
DEPLOY_CHOICE="${DEPLOY_CHOICE:-1}"
echo ""

DEPLOY_METHOD="token"; GITHUB_TOKEN=""; SSH_KEY_PATH="/root/.ssh/gitsub_deploy"; SHOW_PUBKEY="n"

if [ "$DEPLOY_CHOICE" = "2" ]; then
    DEPLOY_METHOD="ssh"
    section "SSH Deploy Key"
    echo "  [1] I already have a key added to this repo"
    echo "  [2] Generate a new key for me"
    echo ""
    read -rp "  Choose [1/2] (default 2): " HAS_KEY
    HAS_KEY="${HAS_KEY:-2}"

    if [ "$HAS_KEY" = "1" ]; then
        echo ""
        echo "  [1] Enter the file path"
        echo "  [2] Paste the key content"
        echo ""
        read -rp "  Choose [1/2] (default 1): " KEY_INPUT
        KEY_INPUT="${KEY_INPUT:-1}"
        if [ "$KEY_INPUT" = "2" ]; then
            mkdir -p /root/.ssh && chmod 700 /root/.ssh
            info "Paste your private key. Press Ctrl+D on an empty line when done."
            echo ""
            cat > "$SSH_KEY_PATH"; chmod 600 "$SSH_KEY_PATH"
            ssh-keygen -y -f "$SSH_KEY_PATH" > "$SSH_KEY_PATH.pub" 2>/dev/null || true
            ok "Key saved to $SSH_KEY_PATH"
        else
            read -rp "  Key path [/root/.ssh/id_rsa]: " SSH_KEY_PATH
            SSH_KEY_PATH="${SSH_KEY_PATH:-/root/.ssh/id_rsa}"
            [ ! -f "$SSH_KEY_PATH" ] && err "Key not found: $SSH_KEY_PATH"
            chmod 600 "$SSH_KEY_PATH"; ok "Using key: $SSH_KEY_PATH"
        fi
        SHOW_PUBKEY="n"
    else
        info "Generating new ED25519 deploy key..."
        mkdir -p /root/.ssh && chmod 700 /root/.ssh
        rm -f "$SSH_KEY_PATH" "$SSH_KEY_PATH.pub"
        ssh-keygen -t ed25519 -C "gitsub@$(hostname)" -f "$SSH_KEY_PATH" -N ""
        ok "Key generated: $SSH_KEY_PATH"; SHOW_PUBKEY="y"
    fi

    # SSH config alias
    SSH_CONFIG="/root/.ssh/config"
    grep -q "Host github-gitsub" "$SSH_CONFIG" 2>/dev/null && sed -i '/Host github-gitsub/,+5d' "$SSH_CONFIG"
    cat >> "$SSH_CONFIG" <<SSHEOF

Host github-gitsub
    HostName github.com
    User git
    IdentityFile $SSH_KEY_PATH
    IdentitiesOnly yes
    StrictHostKeyChecking no
SSHEOF
    chmod 600 "$SSH_CONFIG"; ok "SSH config alias written"

    if [ "$SHOW_PUBKEY" = "y" ]; then
        echo ""
        echo -e "${Y}╔══ ACTION REQUIRED ═══════════════════════════╗${RS}"
        echo -e "${Y}║  Add the public key below to your GitHub repo  ║${RS}"
        echo -e "${Y}║  Repo → Settings → Deploy keys → Add key       ║${RS}"
        echo -e "${Y}║  ✓ Check: Allow write access                   ║${RS}"
        echo -e "${Y}╚═══════════════════════════════════════════════╝${RS}"
        echo ""
        echo -e "  ${C}Public key:${RS}"
        echo "  ┌───────────────────────────────────────────────"
        cat "$SSH_KEY_PATH.pub" | sed 's/^/  │ /'
        echo "  └───────────────────────────────────────────────"
        echo ""
        echo -e "  ${C}Direct link to add it:${RS}"
        echo "  https://github.com/$GITHUB_USER/$GITHUB_REPO/settings/keys/new"
        echo ""
        read -rp "  Press ENTER once you have added the key with write access..."
    fi

    info "Testing SSH connection to GitHub..."
    set +e; SSH_TEST=$(ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no -T git@github.com 2>&1); set -e
    if echo "$SSH_TEST" | grep -q "successfully authenticated"; then ok "SSH to GitHub: OK"
    else warn "SSH test: $SSH_TEST"; read -rp "  Press ENTER to continue anyway, or Ctrl+C to abort..."; fi
    echo ""
else
    section "GitHub Token"
    hint "Create one at: https://github.com/settings/tokens"
    hint "Select scope: repo  (gives full repository access)"
    example "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    GITHUB_TOKEN=$(masked_input "  Personal Access Token: ")
    echo ""; echo ""
fi

# ════════════════════════════════════════
# 4. SUBSCRIPTION FILES
# ════════════════════════════════════════
section "Subscription Files"
hint "Each user's links are stored as a text file in a folder in your repo."
read -rp "  Folder name in repo [subs]: " SUBS_DIR_NAME
SUBS_DIR_NAME="${SUBS_DIR_NAME:-subs}"
echo ""

hint "Filename style: 'random' = secure random string | 'email' = user's email"
hint "Random is more secure (hides who the file belongs to)."
echo "  [1] Random string  (e.g. xK9mPqL2...txt)  — recommended"
echo "  [2] Email-based    (e.g. user_at_example_com.txt)"
echo ""
read -rp "  Choose [1/2] (default 1): " FN_CHOICE
FILENAME_MODE="random"; [ "${FN_CHOICE:-1}" = "2" ] && FILENAME_MODE="email"
echo ""

# ════════════════════════════════════════
# 5. WEB DASHBOARD
# ════════════════════════════════════════
section "Web Dashboard"
read -rp "  Enable web dashboard? [y/n] (default y): " ENABLE_UI
ENABLE_UI="${ENABLE_UI:-y}"; echo ""

UI_PORT=2086; UI_USER="admin"; UI_PASS=""; ACCESS_MODE="1"
DOMAIN=""

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    hint "The dashboard will run only on this port. No other port is used."
    read -rp "  Dashboard port [2086]: " UI_PORT
    UI_PORT="${UI_PORT:-2086}"; echo ""

    section "Dashboard Login"
    read -rp "  Username [admin]: " UI_USER
    UI_USER="${UI_USER:-admin}"
    UI_PASS=$(masked_input "  Password: ")
    echo ""; echo ""

    section "Access Mode"
    hint "How do you want to reach the dashboard?"
    echo ""
    echo "  [1] IP address only"
    example "http://YOUR_IP:${UI_PORT}"
    echo ""
    echo "  [2] Domain name via nginx  (HTTP proxy)"
    example "http://YOUR_IP:${UI_PORT}  and  http://your.domain:${UI_PORT}"
    echo ""
    read -rp "  Choose [1/2] (default 1): " ACCESS_MODE
    ACCESS_MODE="${ACCESS_MODE:-1}"; echo ""

    NGINX_HTTP_PORT="$UI_PORT"
    if [[ "$ACCESS_MODE" =~ ^[2]$ ]]; then
        section "Domain Name"
        hint "The domain must point to this server's IP in DNS (A record)."
        example "sub.example.com  →  your server IP"
        read -rp "  Domain name: " DOMAIN
        [ -z "$DOMAIN" ] && err "Domain name required for this mode"
        echo ""

        # Domain uses same port as the dashboard — no port 80 involved
        NGINX_HTTP_PORT="$UI_PORT"
    fi

fi

# ════════════════════════════════════════
# 6. SYNC INTERVAL
# ════════════════════════════════════════
section "Sync Schedule"
hint "How often gitsub fetches from the panel and pushes changes to GitHub."
echo "  [1] Every 6 hours    — recommended for production"
echo "  [2] Every 1 hour"
echo "  [3] Every 5 minutes  — good for testing"
echo "  [4] Custom (enter seconds)"
echo ""
read -rp "  Choose [1-4] (default 1): " ICHOICE
case "${ICHOICE:-1}" in
    2) INTERVAL=3600  ;;
    3) INTERVAL=300   ;;
    4) read -rp "  Interval in seconds: " INTERVAL ;;
    *) INTERVAL=21600 ;;
esac
echo ""

# ════════════════════════════════════════
# SUMMARY + CONFIRM
# ════════════════════════════════════════
echo ""
echo -e "${C}── Summary ────────────────────────────────${RS}"
echo ""
echo "   Panel URL      : $PANEL_API_URL"
echo "   GitHub repo    : $GITHUB_USER/$GITHUB_REPO  (branch: $GITHUB_BRANCH)"
echo "   Deploy via     : $DEPLOY_METHOD"
echo "   Subs folder    : $SUBS_DIR_NAME"
echo "   Filename mode  : $FILENAME_MODE"
echo "   Sync every     : ${INTERVAL}s"
if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    echo "   Dashboard port : $UI_PORT"
    case "$ACCESS_MODE" in
        1) echo "   Access         : IP only (HTTP)" ;;
        2) echo "   Access         : IP + domain $DOMAIN (both on port $UI_PORT)" ;;
        *) echo "   Access         : IP only" ;;
    esac
fi
echo ""
confirm "Proceed with installation?" || { echo "Aborted."; exit 0; }
echo ""

# ════════════════════════════════════════
# INSTALL
# ════════════════════════════════════════
info "Installing system packages..."
apt-get update -qq

PKGS="python3 python3-venv python3-pip git"
[ "$ACCESS_MODE" = "2" ] && PKGS="$PKGS nginx"

# If nginx will be installed, purge any 443/SSL configs BEFORE apt runs.
# apt-get post-install runs "systemctl start nginx" immediately — if any
# existing config has "listen 443" and that port is taken, the whole install fails.
if [ "$ACCESS_MODE" = "2" ]; then
    info "Pre-cleaning nginx configs to prevent port 443 conflict..."
    for conf in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
        [ -f "$conf" ] && grep -q "listen.*443" "$conf" 2>/dev/null && \
            rm -f "$conf" && info "  Removed old 443 config: $conf"
    done
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
fi

# DEBIAN_FRONTEND=noninteractive prevents dpkg from auto-starting nginx
# during install, which would fail if configs are still being set up
DEBIAN_FRONTEND=noninteractive apt-get install -y $PKGS -qq
ok "Packages installed"

info "Setting up $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/$SUBS_DIR_NAME" "$INSTALL_DIR/logs"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in update.py webui.py requirements.txt uninstall.sh; do
    [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
done
ok "Files copied"

info "Creating Python venv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
ok "Python venv ready"

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
git fetch origin "$GITHUB_BRANCH" --quiet 2>/tmp/gitsub_git_err; FETCH_OK=$?
set -e
if [ $FETCH_OK -eq 0 ]; then
    git reset --hard "origin/$GITHUB_BRANCH" --quiet; ok "Synced with remote"
else
    warn "Could not fetch (new repo or no commits yet) — OK"
    touch "$INSTALL_DIR/$SUBS_DIR_NAME/.gitkeep"
    git add "$SUBS_DIR_NAME/" 2>/dev/null || true
fi
ok "Git configured"

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

  "subs_dir":        "$SUBS_DIR_NAME",
  "filename_length": 32,
  "filename_mode":   "$FILENAME_MODE",
  "sync_interval":   $INTERVAL
}
EOF
chmod 600 "$INSTALL_DIR/config.json"
ok "config.json written (chmod 600)"

info "Installing gitsub CLI..."
cat > /usr/local/bin/gitsub <<EOF
#!/bin/bash
# gitsub CLI — opens interactive menu when run with no arguments
cd $INSTALL_DIR
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/update.py "\$@"
EOF
chmod +x /usr/local/bin/gitsub
# Verify it works
/usr/local/bin/gitsub help > /dev/null 2>&1 && ok "gitsub command ready" || warn "gitsub test failed — check $INSTALL_DIR/update.py"

info "Creating systemd services..."
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

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
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
systemctl enable "$SERVICE_SYNC" && systemctl start "$SERVICE_SYNC"
if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    systemctl enable "$SERVICE_UI" && systemctl start "$SERVICE_UI"
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow "$UI_PORT/tcp" --comment "gitsub webui" >/dev/null 2>&1 || true
        info "Firewall: opened port $UI_PORT"
    fi
fi
ok "Services started"

# ── nginx (HTTP only, no SSL) ─────────────────────
write_nginx_conf() {
    local domain="$1"
    # Remove default Ubuntu nginx site
    rm -f /etc/nginx/sites-enabled/default

    # Remove ALL existing configs that use port 443 — leftover SSL blocks from old installs
    # This is what causes "bind() to 0.0.0.0:443 failed"
    for conf in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
        [ -f "$conf" ] && grep -q "listen.*443" "$conf" 2>/dev/null && \
            { rm -f "$conf"; info "Removed old 443 config: $conf"; }
    done
    rm -f /etc/nginx/sites-enabled/xui-webui /etc/nginx/sites-available/xui-webui

    # Remove any other config already using this domain
    CONFLICTS=$(grep -rl "server_name.*${domain}" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v xui-webui || true)
    [ -n "$CONFLICTS" ] && echo "$CONFLICTS" | xargs rm -f && info "Removed conflicting nginx configs"

    # Write clean HTTP-only config — no SSL, no 443, just port 80 proxy
    cat > "$NGINX_CONF" <<NGINXEOF
server {
    listen ${UI_PORT};
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
    systemctl enable nginx --quiet 2>/dev/null || true

    # Test config BEFORE starting — show exact error if bad
    if ! nginx -t 2>/tmp/nginx_test_err; then
        warn "Nginx config test failed:"
        cat /tmp/nginx_test_err
        return 1
    fi

    # Start or reload
    if systemctl is-active nginx --quiet; then
        systemctl reload nginx
    else
        systemctl start nginx
    fi
    ok "Nginx: http://$domain:$UI_PORT  (domain alias for same port)"
}

if [ "$ACCESS_MODE" = "2" ] && [ -n "$DOMAIN" ]; then
    write_nginx_conf "$DOMAIN"
    command -v ufw &>/dev/null && ufw status | grep -q "active" && \
        ufw allow 80/tcp --comment "gitsub nginx" >/dev/null 2>&1 || true
fi


# ── Done ────────────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${G}╔══════════════════════════════════════════╗${RS}"
echo -e "${G}║        Install complete!                  ║${RS}"
echo -e "${G}╚══════════════════════════════════════════╝${RS}"
echo ""
echo -e "  ${C}Installed to:${RS}  $INSTALL_DIR"
echo ""

if [[ "$ENABLE_UI" =~ ^[Yy] ]]; then
    echo -e "  ${C}Dashboard URLs:${RS}"
    echo "    http://$SERVER_IP:$UI_PORT"
    # Domain HTTP — modes 2 and 3
    if [ "$ACCESS_MODE" = "2" ] && [ -n "$DOMAIN" ]; then
        echo "    http://$DOMAIN:$UI_PORT    (domain)"
    fi

    echo ""
fi

echo -e "  Type ${C}gitsub${RS} for the interactive menu."
echo ""
