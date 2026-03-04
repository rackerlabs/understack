apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config
  namespace: understack-cdn
data:
  nginx.conf: |
    worker_processes auto;
    error_log /var/log/nginx/error.log warn;
    pid /var/cache/nginx/nginx.pid;

    # Tune for large file serving
    worker_rlimit_nofile 65535;

    events {
        worker_connections 4096;
        use epoll;
        multi_accept on;
    }

    http {
        include       /etc/nginx/mime.types;
        default_type  application/octet-stream;

        log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                        '$status $body_bytes_sent "$http_referer" '
                        '"$http_user_agent" "$http_x_forwarded_for" '
                        'cache=$upstream_cache_status';

        access_log /var/log/nginx/access.log main;

        # Large file optimisations
        sendfile           on;
        tcp_nopush         on;
        tcp_nodelay        on;
        keepalive_timeout  65;

        # Proxy cache zone configuration:
        # keys_zone=cdn_cache:50m  — 50MB for cache keys/metadata (~400k keys)
        # max_size=50g             — on-disk cache (adjust to your PVC size)
        # inactive=30d             — evict if not accessed in this time
        # use_temp_path=off        — write directly to cache dir (avoids extra copy)
        proxy_cache_path /var/cache/nginx/cdn
            levels=1:2
            keys_zone=cdn_cache:50m
            max_size={{ .Values.cdn.cacheSize }}
            inactive={{ .Values.cdn.inactive }}
            use_temp_path=off;

        # Don't buffer large files to disk before sending — stream them
        proxy_buffering          on;
        proxy_request_buffering  off;

        # Increase timeouts for large file transfers
        proxy_connect_timeout    10s;
        proxy_send_timeout       300s;
        proxy_read_timeout       300s;
        send_timeout             300s;

        # Hide upstream headers we don't want to leak
        proxy_hide_header x-amz-request-id;
        proxy_hide_header x-amz-id-2;

        include /etc/nginx/conf.d/*.conf;
    }
  default.conf: |
    upstream s3_origin {
        server {{ .Values.cdn.objectStorageServerHostname }}:443;
        keepalive 32;
    }

    server {
        listen 8080;
        server_name _;

        # TLS — cert mounted from a k8s secret via ingress or directly
        #ssl_certificate     /etc/nginx/tls/tls.crt;
        #ssl_certificate_key /etc/nginx/tls/tls.key;
        #ssl_protocols       TLSv1.2 TLSv1.3;
        #ssl_ciphers         HIGH:!aNULL:!MD5;

        proxy_cache            cdn_cache;
        proxy_cache_valid      200 206 7d;   # Cache 200 and partial content
        proxy_cache_valid      404     1m;   # Don't cache 404s for long
        proxy_cache_use_stale  error timeout updating http_500 http_502 http_503;
        proxy_cache_lock       on;           # Collapse simultaneous requests for the same file
        proxy_cache_lock_timeout 10s;

        proxy_cache_key "$scheme$proxy_host$uri";

        add_header X-Cache-Status $upstream_cache_status always;
        add_header X-Served-By    $hostname always;

        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;

        proxy_cache_revalidate on;
        proxy_cache_bypass 0;
        proxy_no_cache 0;
        proxy_ignore_headers Cache-Control Expires Set-Cookie;

        location /{{ .Values.cdn.bucketName }}/ {
            # Forward to Object Storage.
            # S3-compatible API expects requests in the form: /bucket-name/key
            # Our clients are using URL paths in the exact same format.
            proxy_pass https://s3_origin$request_uri;

            proxy_http_version 1.1;
            proxy_set_header Connection "";           # keepalive to upstream
            proxy_set_header Host             rook-ceph-rgw-ceph-objectstore.rook-ceph.svc;
            proxy_set_header X-Real-IP        $remote_addr;
            proxy_set_header X-Forwarded-For  $proxy_add_x_forwarded_for;

            # Don't forward auth headers downstream
            proxy_set_header Authorization "";

            # SSL settings for upstream connection
            proxy_ssl_server_name on;
            proxy_ssl_protocols TLSv1.2 TLSv1.3;

            # Tell clients files are immutable — they should cache forever
            add_header Cache-Control "public, max-age=31536000, immutable" always;

            # Support resumable downloads
            proxy_force_ranges on;

            # Stream large files rather than buffering defeats the cache, so keep buffering on:
            proxy_buffering on;
        }

        # Health check endpoint (used by k8s liveness/readiness probes)
        location /healthz {
            access_log off;
            return 200 "ok\n";
            add_header Content-Type text/plain;
        }

        # Expose basic cache stats (restrict to internal)
        location /nginx_status {
            stub_status;
            allow 10.0.0.0/8;
            allow 172.16.0.0/12;
            allow 192.168.0.0/16;
            deny all;
        }
    }
