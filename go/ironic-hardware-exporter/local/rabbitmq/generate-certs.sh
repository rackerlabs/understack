#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/certs"
FORCE="${1:-}"

mkdir -p "${CERT_DIR}"

if [[ -f "${CERT_DIR}/ca.pem" && -f "${CERT_DIR}/server.pem" && "${FORCE}" != "--force" ]]; then
  echo "TLS certs already exist in ${CERT_DIR}. Use --force to regenerate."
  exit 0
fi

rm -f \
  "${CERT_DIR}/ca.pem" \
  "${CERT_DIR}/ca-key.pem" \
  "${CERT_DIR}/ca.srl" \
  "${CERT_DIR}/server.pem" \
  "${CERT_DIR}/server-key.pem" \
  "${CERT_DIR}/server.csr" \
  "${CERT_DIR}/client.pem" \
  "${CERT_DIR}/client-key.pem" \
  "${CERT_DIR}/client.csr" \
  "${CERT_DIR}/server-ext.cnf"

openssl req \
  -x509 \
  -newkey rsa:4096 \
  -days 3650 \
  -nodes \
  -subj "/CN=ironic-hardware-exporter-local-ca" \
  -keyout "${CERT_DIR}/ca-key.pem" \
  -out "${CERT_DIR}/ca.pem"

openssl req \
  -newkey rsa:2048 \
  -nodes \
  -subj "/CN=localhost" \
  -keyout "${CERT_DIR}/server-key.pem" \
  -out "${CERT_DIR}/server.csr"

cat > "${CERT_DIR}/server-ext.cnf" <<'EOF'
subjectAltName=DNS:localhost,DNS:rabbitmq.local,DNS:rabbitmq-tls
extendedKeyUsage=serverAuth
EOF

openssl x509 \
  -req \
  -in "${CERT_DIR}/server.csr" \
  -CA "${CERT_DIR}/ca.pem" \
  -CAkey "${CERT_DIR}/ca-key.pem" \
  -CAcreateserial \
  -days 3650 \
  -sha256 \
  -extfile "${CERT_DIR}/server-ext.cnf" \
  -out "${CERT_DIR}/server.pem"

rm -f \
  "${CERT_DIR}/server.csr" \
  "${CERT_DIR}/server-ext.cnf" \
  "${CERT_DIR}/ca.srl"

# Local-only harness: make the mounted files readable by the RabbitMQ container.
chmod 644 \
  "${CERT_DIR}/ca.pem" \
  "${CERT_DIR}/ca-key.pem" \
  "${CERT_DIR}/server.pem" \
  "${CERT_DIR}/server-key.pem"

echo "Generated local CA and server certs in ${CERT_DIR}"
