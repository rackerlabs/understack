#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
CERT_DIR="${SCRIPT_DIR}/certs"
LOG_DIR="${SCRIPT_DIR}/logs"
EXPORTER_PORT="${EXPORTER_PORT:-19608}"
RABBIT_USER="${RABBITMQ_LOCAL_USER:-ironic}"
RABBIT_PASS="${RABBITMQ_LOCAL_PASSWORD:-ironic-secret}"
KEEP_UP="${KEEP_UP:-false}"

RUN_ID="${RUN_ID:-$(date +%s)}"
EXPORTER_PID=""
EXPORTER_LOG=""

SAMPLE_HARDWARE="${PROJECT_ROOT}/internal/parser/testdata/metric.json"
SAMPLE_STATE="${PROJECT_ROOT}/internal/parser/testdata/baremetal_node_provision_set.json"

usage() {
  cat <<'EOF'
usage: ./local/rabbitmq/smoke.sh <case>

cases:
  plain
  tls
  tls-sni-override
  tls-bad-ca
  tls-wrong-server-name
  all
  cleanup

optional env:
  KEEP_UP=true      leave RabbitMQ containers running after the script exits
  EXPORTER_PORT=NNN run the exporter on a different local port (default 19608)
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required command not found: $1" >&2
    exit 1
  }
}

cleanup() {
  stop_exporter

  if [[ "${KEEP_UP}" != "true" ]]; then
    docker compose -f "${COMPOSE_FILE}" down >/dev/null 2>&1 || true
  fi
}

stop_exporter() {
  if [[ -n "${EXPORTER_PID}" ]] && kill -0 "${EXPORTER_PID}" >/dev/null 2>&1; then
    kill "${EXPORTER_PID}" >/dev/null 2>&1 || true
    wait "${EXPORTER_PID}" >/dev/null 2>&1 || true
  fi
  EXPORTER_PID=""
}

trap cleanup EXIT

wait_for_management() {
  local port="$1"
  for _ in $(seq 1 30); do
    if curl -fsS -u "${RABBIT_USER}:${RABBIT_PASS}" "http://localhost:${port}/api/overview" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "RabbitMQ management API did not become ready on port ${port}" >&2
  return 1
}

wait_for_tcp_port() {
  local host="$1"
  local port="$2"
  for _ in $(seq 1 30); do
    if (echo >"/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "TCP listener did not become ready on ${host}:${port}" >&2
  return 1
}

ensure_exchange() {
  local port="$1"
  curl -fsS \
    -u "${RABBIT_USER}:${RABBIT_PASS}" \
    -H "content-type: application/json" \
    -X PUT \
    -d '{"type":"topic","durable":true,"auto_delete":false,"internal":false,"arguments":{}}' \
    "http://localhost:${port}/api/exchanges/ironic/ironic" >/dev/null
}

wait_for_http() {
  local url="$1"
  for _ in $(seq 1 30); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "HTTP endpoint did not become ready: ${url}" >&2
  return 1
}

start_broker() {
  local service="$1"
  local management_port="$2"
  local amqp_port="$3"
  "${SCRIPT_DIR}/generate-certs.sh"
  docker compose -f "${COMPOSE_FILE}" up -d "${service}" >/dev/null
  wait_for_management "${management_port}"
  wait_for_tcp_port "localhost" "${amqp_port}"
  ensure_exchange "${management_port}"
}

start_exporter() {
  local case_name="$1"
  shift

  stop_exporter

  mkdir -p "${LOG_DIR}"
  EXPORTER_LOG="${LOG_DIR}/exporter-${case_name}.log"
  rm -f "${EXPORTER_LOG}"

  (
    cd "${PROJECT_ROOT}"
    env \
      SERVER_PORT="${EXPORTER_PORT}" \
      RABBITMQ_PASSWORD="${RABBIT_PASS}" \
      RABBITMQ_USERNAME="${RABBIT_USER}" \
      RABBITMQ_VHOST="ironic" \
      RABBITMQ_EXCHANGE="ironic" \
      RABBITMQ_QUEUE="smoke-${case_name}-${RUN_ID}" \
      RABBITMQ_STATES_QUEUE="smoke-${case_name}-states-${RUN_ID}" \
      "$@" \
      go run ./cmd/main.go
  ) >"${EXPORTER_LOG}" 2>&1 &

  EXPORTER_PID=$!
  wait_for_http "http://localhost:${EXPORTER_PORT}/health"
}

assert_metrics() {
  local metrics=""
  for _ in $(seq 1 20); do
    metrics="$(curl -fsS "http://localhost:${EXPORTER_PORT}/metrics" || true)"
    if grep -q 'ironic_node_temperature_celsius' <<<"${metrics}" &&
      grep -q 'ironic_node_provision_state' <<<"${metrics}" &&
      grep -q 'Dell-24GSW04' <<<"${metrics}"; then
      return 0
    fi
    sleep 1
  done

  echo "expected metrics not found in exporter output" >&2
  return 1
}

publish_samples() {
  local management_port="$1"
  "${SCRIPT_DIR}/publish-sample.sh" "notifications.info" "${SAMPLE_HARDWARE}" "${management_port}" >/dev/null
  "${SCRIPT_DIR}/publish-sample.sh" "ironic_versioned_notifications.info" "${SAMPLE_STATE}" "${management_port}" >/dev/null
}

run_positive_case() {
  local case_name="$1"
  local service="$2"
  local management_port="$3"
  local amqp_port="$4"
  shift 4

  start_broker "${service}" "${management_port}" "${amqp_port}"
  start_exporter "${case_name}" "$@"
  curl -fsS "http://localhost:${EXPORTER_PORT}/ready" >/dev/null
  publish_samples "${management_port}"
  assert_metrics
  stop_exporter
  echo "PASS: ${case_name}"
}

run_negative_startup_case() {
  local case_name="$1"
  shift
  mkdir -p "${LOG_DIR}"
  local log_file="${LOG_DIR}/${case_name}.log"
  rm -f "${log_file}"

  if (
    cd "${PROJECT_ROOT}"
    env \
      SERVER_PORT="${EXPORTER_PORT}" \
      RABBITMQ_PASSWORD="${RABBIT_PASS}" \
      RABBITMQ_USERNAME="${RABBIT_USER}" \
      RABBITMQ_VHOST="ironic" \
      RABBITMQ_EXCHANGE="ironic" \
      RABBITMQ_QUEUE="smoke-${case_name}-${RUN_ID}" \
      RABBITMQ_STATES_QUEUE="smoke-${case_name}-states-${RUN_ID}" \
      "$@" \
      go run ./cmd/main.go
  ) >"${log_file}" 2>&1; then
    echo "expected ${case_name} to fail, but exporter started successfully" >&2
    return 1
  fi

  echo "PASS: ${case_name} failed as expected"
}

run_plain() {
  run_positive_case \
    "plain" \
    "rabbitmq-tls" \
    "15672" \
    "5672" \
    RABBITMQ_HOST=localhost \
    RABBITMQ_PORT=5672 \
    RABBITMQ_TLS_ENABLED=false
}

run_tls() {
  run_positive_case \
    "tls" \
    "rabbitmq-tls" \
    "15672" \
    "5671" \
    RABBITMQ_HOST=localhost \
    RABBITMQ_PORT=5671 \
    RABBITMQ_TLS_ENABLED=true \
    RABBITMQ_CA_CERT_PATH="${CERT_DIR}/ca.pem"
}

run_tls_sni_override() {
  run_positive_case \
    "tls-sni-override" \
    "rabbitmq-tls" \
    "15672" \
    "5671" \
    RABBITMQ_HOST=127.0.0.1 \
    RABBITMQ_PORT=5671 \
    RABBITMQ_TLS_ENABLED=true \
    RABBITMQ_CA_CERT_PATH="${CERT_DIR}/ca.pem" \
    RABBITMQ_TLS_SERVER_NAME=localhost
}

run_tls_bad_ca() {
  start_broker "rabbitmq-tls" "15672" "5671"
  run_negative_startup_case \
    "tls-bad-ca" \
    RABBITMQ_HOST=localhost \
    RABBITMQ_PORT=5671 \
    RABBITMQ_TLS_ENABLED=true \
    RABBITMQ_CA_CERT_PATH="${CERT_DIR}/server.pem"
}

run_tls_wrong_server_name() {
  start_broker "rabbitmq-tls" "15672" "5671"
  run_negative_startup_case \
    "tls-wrong-server-name" \
    RABBITMQ_HOST=localhost \
    RABBITMQ_PORT=5671 \
    RABBITMQ_TLS_ENABLED=true \
    RABBITMQ_CA_CERT_PATH="${CERT_DIR}/ca.pem" \
    RABBITMQ_TLS_SERVER_NAME=wrong.local
}

run_all() {
  run_plain
  run_tls
  run_tls_sni_override
  run_tls_bad_ca
  run_tls_wrong_server_name
}

main() {
  local case_name="${1:-}"
  if [[ -z "${case_name}" ]]; then
    usage
    exit 1
  fi

  require_cmd docker
  require_cmd curl
  require_cmd go
  require_cmd openssl
  require_cmd python3

  case "${case_name}" in
    plain) run_plain ;;
    tls) run_tls ;;
    tls-sni-override) run_tls_sni_override ;;
    tls-bad-ca) run_tls_bad_ca ;;
    tls-wrong-server-name) run_tls_wrong_server_name ;;
    all) run_all ;;
    cleanup)
      docker compose -f "${COMPOSE_FILE}" down
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
