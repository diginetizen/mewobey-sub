#!/bin/bash

echo "====================================="
echo " XUI SUBSYNC UNINSTALLER"
echo "====================================="

read -p "Are you sure? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

echo "[1] Stopping services..."
systemctl stop xui-subsync 2>/dev/null
systemctl stop xui-webui 2>/dev/null

echo "[2] Disabling services..."
systemctl disable xui-subsync 2>/dev/null
systemctl disable xui-webui 2>/dev/null

echo "[3] Removing systemd files..."
rm -f /etc/systemd/system/xui-subsync.service
rm -f /etc/systemd/system/xui-webui.service
systemctl daemon-reload

echo "[4] Removing nginx config..."
rm -f /etc/nginx/sites-enabled/xui-webui
rm -f /etc/nginx/sites-available/xui-webui
systemctl restart nginx 2>/dev/null

echo "[5] Removing project files..."
read -p "Delete /opt/xui-subsync? (yes/no): " DEL

if [ "$DEL" = "yes" ]; then
    rm -rf /opt/xui-subsync
    echo "Deleted"
else
    echo "Kept project"
fi

echo "DONE"
