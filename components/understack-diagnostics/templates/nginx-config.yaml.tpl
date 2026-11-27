apiVersion: v1
kind: ConfigMap
metadata:
  name: diagnostics-nginx
data:
  nginx.conf: |
    worker_processes 2;
    error_log /dev/stderr warn;
    pid /var/cache/nginx/nginx.pid;

    events {
        worker_connections 1024;
    }

    http {
        include       /etc/nginx/mime.types;
        default_type  application/octet-stream;
        access_log    /dev/stdout;
        sendfile      on;

        # Temporary upload bodies must sit on the same filesystem as the
        # final files so the finished file is renamed, not copied. The
        # leading dot hides it from listings.
        client_body_temp_path /data/.tmp;

        # Uploads: PUT /diagnostics/<kind>/<node-uuid>/<file> -> /data/<kind>/...
        # Only the internal gateway route targets this listener. It has no
        # credentials: anything that can reach it can upload or overwrite.
        server {
            listen 8080;

            location = /healthz {
                access_log off;
                default_type text/plain;
                return 200 "ok\n";
            }

            # Reject hidden path segments such as /.tmp/.
            location ~ /\. { return 404; }

            location /diagnostics/ {
                if ($request_method != PUT) { return 405; }
                if ($is_args != "") { return 400; }
                if ($content_length = "") { return 411; }

                alias /data/;
                client_max_body_size 2g;
                client_body_timeout 300s;
                dav_methods PUT;
                create_full_put_path on;
            }

            location / { return 404; }
        }

        # Reads: GET /archives/<kind>/<node-uuid>/ with basic auth.
        # The route must be HTTPS only.
        server {
            listen 8081;

            location ~ /\. { return 404; }

            location /archives/ {
                limit_except GET { deny all; }
                auth_basic "Diagnostics archives";
                auth_basic_user_file /etc/nginx/auth/htpasswd;

                alias /data/;
                autoindex on;
                autoindex_format json;
                add_header Cache-Control "private, no-store" always;
                add_header X-Content-Type-Options nosniff always;
            }

            location / { return 404; }
        }
    }
