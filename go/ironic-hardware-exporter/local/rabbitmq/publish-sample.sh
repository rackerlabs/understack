#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <routing-key> <json-file> [management-port]" >&2
  exit 1
fi

ROUTING_KEY="$1"
JSON_FILE="$2"
MANAGEMENT_PORT="${3:-15672}"

RABBIT_USER="${RABBITMQ_LOCAL_USER:-ironic}"
RABBIT_PASS="${RABBITMQ_LOCAL_PASSWORD:-ironic-secret}"
RABBIT_VHOST="${RABBITMQ_LOCAL_VHOST:-ironic}"
RABBIT_EXCHANGE="${RABBITMQ_LOCAL_EXCHANGE:-ironic}"

if [[ ! -f "${JSON_FILE}" ]]; then
  echo "json file not found: ${JSON_FILE}" >&2
  exit 1
fi

PAYLOAD_JSON="$(python3 - "${JSON_FILE}" <<'PY'
import json
import pathlib
import sys

print(json.dumps(pathlib.Path(sys.argv[1]).read_text()))
PY
)"

RESPONSE="$(curl -fsS \
  -u "${RABBIT_USER}:${RABBIT_PASS}" \
  -H "content-type: application/json" \
  -d "{\"properties\":{},\"routing_key\":\"${ROUTING_KEY}\",\"payload\":${PAYLOAD_JSON},\"payload_encoding\":\"string\"}" \
  "http://localhost:${MANAGEMENT_PORT}/api/exchanges/${RABBIT_VHOST}/${RABBIT_EXCHANGE}/publish")"

echo "${RESPONSE}"
