#!/bin/bash
# gitsub uninstaller

INSTALL_DIR="/opt/xui-subsync"
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; CYAN="\033[0;36m"; RED="\033[0;31m"; RESET="\033[0m"
info()    { echo -e "${CYAN}[info]${RESET} $*"; }
success() { echo -e "${GREEN}[ok]${RESET}   $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET} $*"; }

echo ""
echo -e "${YELLOW}══════════════════════════════════════════${RESET}"
echo -e "${YELLOW}   gitsub Uninstaller                     ${RESET}"
echo -e "${YELLOW}══════════════════════════════════════════${RESET}"
echo ""
read -rp "  Are you sure you want to uninstall? [yes/no]: " CONFIRM
[ "$CONFIRM" != "yes" ] && echo "Cancelled." && exit 0

info "Stopping services..."
systemctl stop xui-subsync 2>/dev/null || true
systemctl stop xui-webui   2>/dev/null || true

info "Disabling services..."
systemctl disable xui-subsync 2>/dev/null || true
systemctl disable xui-webui   2>/dev/null || true

info "Removing systemd files..."
rm -f /etc/systemd/system/xui-subsync.service
rm -f /etc/systemd/system/xui-webui.service
systemctl daemon-reload

info "Removing nginx config..."
rm -f /etc/nginx/sites-enabled/xui-webui
rm -f /etc/nginx/sites-available/xui-webui
systemctl reload nginx 2>/dev/null || true

info "Removing CLI command..."
rm -f /usr/local/bin/gitsub

echo ""
read -rp "  Delete project files at $INSTALL_DIR? [yes/no]: " DEL
if [ "$DEL" = "yes" ]; then
    rm -rf "$INSTALL_DIR"
    success "Project files deleted"
else
    warn "Kept project files at $INSTALL_DIR"
fi

echo ""
success "Uninstall complete."
