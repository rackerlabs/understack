# Integration tests

## Initial setup

## Usage

```shell
docker run --rm --env-file dev.env ghcr.io/rackerlabs/understack-tests run-scenario build_a_single_server.yaml
```

### Available scenarios

- `build_a_single_server.yaml` - boots a simple Ubuntu GP2.SMALL server with a plain networking setup. The network is automatically created and removed.
- `floating_ips.yaml` - build a network, server, router and associate and dissociate floating IP
