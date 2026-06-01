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

G="\033[0;32m"; Y="\033[1;33m"; C="\033[0;36m"; R="\033[0;31m"; B="\033[1m"; RS="\033[0m"
info()    { echo -e "${C}[info]${RS} $*"; }
ok()      { echo -e "${G}[ ok]${RS} $*"; }
warn()    { echo -e "${Y}[warn]${RS} $*"; }
err()     { echo -e "${R}[ err]${RS} $*"; exit 1; }
section() { echo ""; echo -e "${Y}── $* $(printf '─%.0s' $(seq 1 $((42-${#1}))))${RS}"; echo ""; }
hint()    { echo -e "  ${B}→${RS} $*"; }

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
    hint "Create a token at: https://github.com/settings/tokens"
    hint "Required scope: repo  (full repository access)"
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
DOMAIN=""; SSL_MODE="none"; SSL_CERT=""; SSL_KEY=""; SSL_EMAIL=""; CERTBOT_PORT="80"

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
    hint "Choose how users will reach the dashboard."
    hint "All modes serve the dashboard on port ${UI_PORT} only."
    echo ""
    echo "  [1] IP address only"
    echo "      → http://YOUR_IP:${UI_PORT}"
    echo ""
    echo "  [2] IP address  +  custom domain  (HTTP)"
    echo "      → http://YOUR_IP:${UI_PORT}"
    echo "      → http://your.domain:${UI_PORT}"
    echo ""
    echo "  [3] IP address  +  domain  +  HTTPS  (recommended for production)"
    echo "      → http://YOUR_IP:${UI_PORT}"
    echo "      → http://your.domain:${UI_PORT}"
    echo "      → https://your.domain"
    echo ""
    echo "  [4] IP address with HTTPS via cert files"
    echo "      → https://YOUR_IP:${UI_PORT}"
    echo ""
    read -rp "  Choose [1-4] (default 1): " ACCESS_MODE
    ACCESS_MODE="${ACCESS_MODE:-1}"; echo ""

    if [[ "$ACCESS_MODE" =~ ^[23]$ ]]; then
        section "Domain Name"
        hint "The domain must already point to this server's IP via DNS."
        hint "Example: sub.example.com  (A record → your server IP)"
        read -rp "  Domain name: " DOMAIN
        [ -z "$DOMAIN" ] && err "Domain name required for this access mode"
        echo ""
    fi

    if [ "$ACCESS_MODE" = "3" ]; then
        section "SSL Certificate"
        hint "How do you want to get the HTTPS certificate?"
        echo "  [1] Let's Encrypt via Certbot  — free, automatic, recommended"
        echo "  [2] I have cert files on this server"
        echo "  [3] Skip SSL for now — I'll add it later"
        echo ""
        read -rp "  Choose [1-3] (default 1): " SSL_SRC
        SSL_SRC="${SSL_SRC:-1}"; echo ""

        if [ "$SSL_SRC" = "1" ]; then
            SSL_MODE="certbot"
            hint "Certbot will request a certificate from Let's Encrypt."
            hint "It needs to briefly listen on a port for domain verification."
            read -rp "  Certbot challenge port [80]: " CERTBOT_PORT
            CERTBOT_PORT="${CERTBOT_PORT:-80}"
            read -rp "  Your email for Let's Encrypt notices [admin@${DOMAIN}]: " SSL_EMAIL
            SSL_EMAIL="${SSL_EMAIL:-admin@${DOMAIN}}"
        elif [ "$SSL_SRC" = "2" ]; then
            SSL_MODE="manual"
            hint "Provide paths to your existing certificate files."
            read -rp "  Certificate file path (fullchain.pem): " SSL_CERT
            read -rp "  Private key file path  (privkey.pem): " SSL_KEY
            [ ! -f "$SSL_CERT" ] && err "Certificate not found: $SSL_CERT"
            [ ! -f "$SSL_KEY"  ] && err "Key not found: $SSL_KEY"
            ok "Certificate files accepted"
        else
            SSL_MODE="later"
            warn "SSL skipped — add it later from the gitsub menu (option 8)"
        fi
    fi

    if [ "$ACCESS_MODE" = "4" ]; then
        section "SSL Certificate for IP"
        hint "Flask will serve HTTPS directly on port ${UI_PORT}."
        hint "You need a certificate file (fullchain.pem) and a key file (privkey.pem)."
        echo ""
        echo "  [1] Enter the file paths"
        echo "  [2] Paste certificate content"
        echo ""
        read -rp "  Choose [1/2] (default 1): " CERT_SRC
        CERT_SRC="${CERT_SRC:-1}"; echo ""

        if [ "$CERT_SRC" = "2" ]; then
            mkdir -p "$INSTALL_DIR/ssl"
            SSL_CERT="$INSTALL_DIR/ssl/cert.pem"; SSL_KEY="$INSTALL_DIR/ssl/key.pem"
            info "Paste certificate (fullchain.pem), Ctrl+D when done:"; echo ""
            cat > "$SSL_CERT"; echo ""
            info "Paste private key (privkey.pem), Ctrl+D when done:"; echo ""
            cat > "$SSL_KEY"; chmod 600 "$SSL_KEY"
            ok "Cert saved to $INSTALL_DIR/ssl/"
        else
            read -rp "  Certificate path (fullchain.pem): " SSL_CERT
            read -rp "  Private key path  (privkey.pem): " SSL_KEY
            [ ! -f "$SSL_CERT" ] && err "Certificate not found: $SSL_CERT"
            [ ! -f "$SSL_KEY"  ] && err "Key not found: $SSL_KEY"
            ok "Certificate files accepted"
        fi
        SSL_MODE="manual"
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
        2) echo "   Access         : IP + domain $DOMAIN (HTTP)" ;;
        3) echo "   Access         : IP + domain $DOMAIN + HTTPS ($SSL_MODE)" ;;
        4) echo "   Access         : IP with HTTPS (cert files)" ;;
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
[[ "$ACCESS_MODE" =~ ^[23]$ ]] && PKGS="$PKGS nginx"
[ "$SSL_MODE" = "certbot" ]    && PKGS="$PKGS certbot python3-certbot-nginx"
apt-get install -y $PKGS -qq
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
ssl/
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
  "ssl_mode":       "$SSL_MODE",
  "ssl_cert":       "$SSL_CERT",
  "ssl_key":        "$SSL_KEY",
  "ssl_email":      "$SSL_EMAIL",
  "certbot_port":   "$CERTBOT_PORT",

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
cd $INSTALL_DIR
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/update.py "\$@"
EOF
chmod +x /usr/local/bin/gitsub
ok "gitsub command ready"

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

# ── nginx / SSL ─────────────────────────────────
write_nginx_conf() {
    local domain="$1"
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
    nginx -t -q && systemctl is-active nginx &>/dev/null && systemctl reload nginx || systemctl start nginx
    ok "Nginx: $domain → port $UI_PORT"
}

if [ "$ACCESS_MODE" = "2" ] && [ -n "$DOMAIN" ]; then
    write_nginx_conf "$DOMAIN"
    command -v ufw &>/dev/null && ufw status | grep -q "active" && \
        ufw allow 80/tcp --comment "gitsub nginx" >/dev/null 2>&1 || true
fi

if [ "$ACCESS_MODE" = "3" ] && [ -n "$DOMAIN" ]; then
    write_nginx_conf "$DOMAIN"
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw allow 80/tcp  >/dev/null 2>&1 || true
        ufw allow 443/tcp >/dev/null 2>&1 || true
    fi

    if [ "$SSL_MODE" = "certbot" ]; then
        info "Running Certbot for $DOMAIN (challenge port: $CERTBOT_PORT)..."
        CERTBOT_ARGS="--nginx -d $DOMAIN --non-interactive --agree-tos -m $SSL_EMAIL"
        [ "$CERTBOT_PORT" != "80" ] && CERTBOT_ARGS="$CERTBOT_ARGS --http-01-port $CERTBOT_PORT"
        # shellcheck disable=SC2086
        certbot $CERTBOT_ARGS \
            && ok "SSL certificate installed — https://$DOMAIN is live" \
            || warn "Certbot failed. Run manually: certbot --nginx -d $DOMAIN"
        grep -q "X-Forwarded-Proto" "$NGINX_CONF" || \
            sed -i "s|proxy_pass.*127.*|&\n        proxy_set_header X-Forwarded-Proto \$scheme;|" "$NGINX_CONF" 2>/dev/null || true
        nginx -t -q && systemctl reload nginx 2>/dev/null || true

    elif [ "$SSL_MODE" = "manual" ]; then
        cat >> "$NGINX_CONF" <<SSLEOF

server {
    listen 443 ssl;
    server_name ${DOMAIN};
    ssl_certificate     ${SSL_CERT};
    ssl_certificate_key ${SSL_KEY};
    location / {
        proxy_pass           http://127.0.0.1:${UI_PORT};
        proxy_set_header     Host \$host;
        proxy_set_header     X-Forwarded-Proto https;
        proxy_read_timeout   60;
        proxy_http_version   1.1;
    }
}
SSLEOF
        nginx -t -q && systemctl reload nginx
        ok "SSL configured via cert files for $DOMAIN"
    fi
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
    # Mode 4 = HTTPS on IP
    if [ "$ACCESS_MODE" = "4" ] && [ -n "$SSL_CERT" ]; then
        echo "    https://$SERVER_IP:$UI_PORT"
    else
        echo "    http://$SERVER_IP:$UI_PORT"
    fi
    # Domain HTTP — modes 2 and 3
    if [[ "$ACCESS_MODE" =~ ^[23]$ ]] && [ -n "$DOMAIN" ]; then
        echo "    http://$DOMAIN:$UI_PORT"
    fi
    # Domain HTTPS — mode 3 with SSL active
    if [ "$ACCESS_MODE" = "3" ] && [ -n "$DOMAIN" ] && [ "$SSL_MODE" != "later" ]; then
        echo "    https://$DOMAIN"
    fi
    echo ""
fi

echo -e "  Type ${C}gitsub${RS} for the interactive menu."
echo ""
