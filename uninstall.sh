#!/bin/bash

echo "=================================="
echo "  XUI SUB SYNC UNINSTALLER"
echo "=================================="

read -p "Are you sure you want to uninstall? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo "[1/6] Stopping services..."
systemctl stop xui-subsync 2>/dev/null
systemctl stop xui-webui 2>/dev/null

echo "[2/6] Disabling services..."
systemctl disable xui-subsync 2>/dev/null
systemctl disable xui-webui 2>/dev/null

echo "[3/6] Removing systemd files..."
rm -f /etc/systemd/system/xui-subsync.service
rm -f /etc/systemd/system/xui-webui.service
systemctl daemon-reload

echo "[4/6] Removing nginx config (if exists)..."
rm -f /etc/nginx/sites-enabled/xui-webui
rm -f /etc/nginx/sites-available/xui-webui
systemctl restart nginx 2>/dev/null

echo "[5/6] Removing virtual environment..."
rm -rf venv

echo "[6/6] OPTIONAL cleanup"

read -p "Remove project folder /opt/xui-subsync? (yes/no): " REMOVE

if [ "$REMOVE" = "yes" ]; then
    rm -rf /opt/xui-subsync
    echo "Project deleted."
else
    echo "Project kept."
fi

echo "=================================="
echo "Uninstall completed."
echo "=================================="
