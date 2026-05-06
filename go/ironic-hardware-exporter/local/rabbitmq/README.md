# Local RabbitMQ TLS Harness

This directory gives you a repeatable way to test the exporter against a real RabbitMQ broker locally before you trust it in dev or prod.

What it covers:
- plain AMQP on `5672`
- TLS on `5671`
- TLS failure with the wrong CA
- TLS failure with the wrong server name
- SNI override with `RABBITMQ_TLS_SERVER_NAME`
- end-to-end exporter validation by publishing real sample Oslo notifications and checking `/metrics`

## Files

- `docker-compose.yml`: local RabbitMQ services
- `config/rabbitmq.conf`: plain + TLS broker
- `generate-certs.sh`: generates a local CA and server cert
- `publish-sample.sh`: publishes sample Oslo notifications through RabbitMQ management API
- `smoke.sh`: runs the end-to-end smoke cases

The smoke runner creates the `ironic` topic exchange through the management API after the broker is up, so the harness does not depend on RabbitMQ definitions imports.

## Prerequisites

- Docker / Docker Compose
- Go
- `openssl`
- `curl`
- `python3`

## Quick Start

From the exporter repo:

```bash
./local/rabbitmq/smoke.sh tls
```

Run the full matrix:

```bash
./local/rabbitmq/smoke.sh all
```

Leave the RabbitMQ containers running after the smoke test:

```bash
KEEP_UP=true ./local/rabbitmq/smoke.sh tls
```

Clean up local RabbitMQ containers:

```bash
./local/rabbitmq/smoke.sh cleanup
```

## Case Matrix

- `plain`
  Verifies the exporter can connect over plain AMQP and consume/publish metrics.

- `tls`
  Verifies CA-validated TLS over `amqps://`.

- `tls-sni-override`
  Verifies `RABBITMQ_TLS_SERVER_NAME` works when the connect host differs from the certificate hostname.

- `tls-bad-ca`
  Verifies startup fails when the CA is wrong.

- `tls-wrong-server-name`
  Verifies startup fails when the TLS server name does not match the certificate.

## Notes

- The smoke script runs the exporter on local port `19608` by default so it does not collide with a copy you may already be running on `9608`.
- Generated certs live under `local/rabbitmq/certs/` and are ignored by git.
- The script publishes sample files from `internal/parser/testdata/`:
  - `metric.json`
  - `baremetal_node_provision_set.json`

If you want to inspect the broker manually after `KEEP_UP=true`, the management UI is:

- TLS broker: `http://localhost:15672`

Default local credentials:

- user: `ironic`
- password: `ironic-secret`
