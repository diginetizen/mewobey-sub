#!/bin/bash

read -p "FULL REMOVE? (yes/no): " c

if [ "$c" != "yes" ]; then exit; fi

systemctl stop xui-subsync
systemctl stop xui-webui

systemctl disable xui-subsync
systemctl disable xui-webui

rm -f /etc/systemd/system/xui-*
rm -rf /opt/xui-subsync

systemctl daemon-reload

echo "REMOVED"
