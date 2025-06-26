# OpenStack Logging

## How to interpret this OpenStack logging message

To interpret the OpenStack logging message:

```text
2025-06-25 13:22:40.999 7 ERROR ironic.common.policy [None req-e75fced6-3a9c-4d8d-aa85-aea5398d5c9e 5f9179b7e200cd85c55e8a26400e266c6b4f7209f6d3fb2adc3cf8e1113c378c 32e02632f4f04415bab5895d1e7247b7 - - 1f75c3b20fcb41ec924a71be83a5ee94 7f46f53fcb3c4625a343eaa35b5e0d04] sometext
```

## Structure of the Log Message

### Timestamp and Process Info

- `2025-06-25 13:22:40.999`: Date and time (with milliseconds) when the log entry was created.
- `7`: The process ID (PID) of the process emitting the log. Note that this is PID in container namespace.

### Log Level and Source**

- `ERROR`: Severity level of the log.
- `ironic.common.policy`: Python module or component where the error originated. Here, it is the policy engine of the Ironic service (bare metal provisioning).

### Contextual Information (in brackets)

This bracketed section contains various IDs and context fields, typically in this order:

- `None`: Sometimes a placeholder for a missing field (could be project or domain).
- `req-e75fced6-3a9c-4d8d-aa85-aea5398d5c9e`: The request ID, useful for tracing this request across different logs and services.
- `5f9179b7e200cd85c55e8a26400e266c6b4f7209f6d3fb2adc3cf8e1113c378c`: User ID.
- `32e02632f4f04415bab5895d1e7247b7`: Tenant or project ID.
- `- -`: Placeholders for domain and user domain (may be empty if not set).
- `1f75c3b20fcb41ec924a71be83a5ee94`: User domain ID or project domain ID.
- `7f46f53fcb3c4625a343eaa35b5e0d04`: Project domain ID or similar.

These IDs can be looked up with:

#### User ID lookup

```text
❯ openstack user show 5f9179b7e200cd85c55e8a26400e266c6b4f7209f6d3fb2adc3cf8e1113c378c
+---------------------+------------------------------------------------------------------+
| Field               | Value                                                            |
+---------------------+------------------------------------------------------------------+
| default_project_id  | None                                                             |
| domain_id           | 1f75c3b20fcb41ec924a71be83a5ee94                                 |
| email               | marek.skrobacki@rackspace.co.uk                                  |
| enabled             | True                                                             |
| id                  | 5f9179b7e200cd85c55e8a26400e266c6b4f7209f6d3fb2adc3cf8e1113c378c |
| name                | Marek.Skrobacki@rackspace.co.uk                                  |
| description         | None                                                             |
| password_expires_at | None                                                             |
+---------------------+------------------------------------------------------------------+
```

#### Project ID lookup

```text
❯ openstack project show 32e02632f4f04415bab5895d1e7247b7
+-------------+----------------------------------+
| Field       | Value                            |
+-------------+----------------------------------+
| description | Ironic Resources                 |
| domain_id   | 7f46f53fcb3c4625a343eaa35b5e0d04 |
| enabled     | True                             |
| id          | 32e02632f4f04415bab5895d1e7247b7 |
| is_domain   | False                            |
| name        | baremetal                        |
| options     | {}                               |
| parent_id   | 7f46f53fcb3c4625a343eaa35b5e0d04 |
| tags        | []                               |
+-------------+----------------------------------+
```

#### Domain lookup

```text
❯ openstack domain show 1f75c3b20fcb41ec924a71be83a5ee94
+-------------+----------------------------------+
| Field       | Value                            |
+-------------+----------------------------------+
| description | SSO to dex                       |
| enabled     | True                             |
| id          | 1f75c3b20fcb41ec924a71be83a5ee94 |
| name        | sso                              |
| options     | {}                               |
| tags        | []                               |
+-------------+----------------------------------+
```
