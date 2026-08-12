#!/usr/bin/env bash
set -euo pipefail

readonly PROXY_VERSION="2.18.2"
readonly CONNECTION_NAME="chloe-tutoring-bot:asia-southeast1:amath-postgres"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl docker.io google-cloud-cli
systemctl enable --now docker

curl --fail --location --silent --show-error \
  "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v${PROXY_VERSION}/cloud-sql-proxy.linux.amd64" \
  --output /usr/local/bin/cloud-sql-proxy
chmod 0755 /usr/local/bin/cloud-sql-proxy

cat >/etc/systemd/system/cloud-sql-proxy.service <<EOF
[Unit]
Description=Cloud SQL Auth Proxy for A-Math bot
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/cloud-sql-proxy --address 127.0.0.1 --port 5432 ${CONNECTION_NAME}
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cloud-sql-proxy
install -d -m 0700 /var/lib/amath-bot
