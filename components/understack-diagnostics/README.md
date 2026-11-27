# understack-diagnostics

NGINX that accepts diagnostic files uploaded by BMCs over HTTP PUT onto its own
volume, and serves them to NodeDash with basic auth. Each kind of file gets its
own top-level directory; Dell SupportAssist collections use `supportassist`.

| Port | Use | Access |
|---|---|---|
| 8080 | `PUT /diagnostics/<kind>/<node-uuid>/<file>` | internal gateway only, no credentials |
| 8081 | `GET /archives/<kind>/<node-uuid>/` | HTTPS only, basic auth |

Values: `storageClassName` and `storageSize`. Requires the Secret
`diagnostics-download-auth` (key `htpasswd`) in the namespace.

Setup steps, routes and operations are in
[docs/deploy-guide/components/diagnostics.md](../../docs/deploy-guide/components/diagnostics.md).
