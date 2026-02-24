# Poor-man's CDN for serving firmware images

Images are stored in Object Store

Cacheing reverse-proxies at each fabric will fetch the images from Object Store
and make them available via HTTPS.

This allows a device to access firmware images via an HTTPS request to a
cluster-local tendot IP address.

## Proxy configuration

The proxy edge service caches files locally on a persistent volume.

Nginx configuration contains:
- the service address for rook-ceph
- the name of our bucket

All files are proxied to that object bucket.  Anonymous credentials are used,
therefore we need to make the files in our bucket readable by anonymous if they
are to be accessible via HTTP.

## Uploading file to object storage

Our credentials and bucket info is in a secret and a configmap both named after
the bucketclaim:

``` sh
KEY_ID=`kubectl -n cdn get secrets firmware-images -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d`
KEY=`kubectl -n cdn get secrets firmware-images -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d`
```

I was able to manage the bucket using the minio CLI client called "mc".

I was testing this without direct access to the object store because there was
no ingress for it at the time of writing.  Therefore I configured a port forward
so I could upload files from my laptop.  I also had to mess with DNS resolution
because RGW is looking at the "host" header:

``` sh
kubectl -n rook-ceph port-forward svc/rook-ceph-rgw-ceph-objectstore 8081:80 &
echo "127.0.0.1  rook-ceph-rgw-ceph-objectstore.rook-ceph.svc" | sudo tee -a /etc/hosts
mc alias set myrook http://rook-ceph-rgw-ceph-objectstore.rook-ceph.svc:8081 $KEY_ID $KEY
mc anonymous set download myrook/firmware-images
mc cp DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE myrook/firmware-images/DELL/R7615/
mc anonymous set download myrook/firmware-images/DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE
```

## Testing with curl

curl https://cdn.dev.undercloud.rackspace.net/DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE | sha256sum

## See nginx logs to check that it is Cacheing

``` sh
⇒ kubectl -n cdn logs deployments/cdn-edge
Defaulted container "nginx" out of: nginx, cache-dir-init (init)
/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
/docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
/docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)
/docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
/docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
/docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
/docker-entrypoint.sh: Configuration complete; ready for start up
10.64.49.118 - - [26/Feb/2026:12:36:47 +0000] "GET /DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE HTTP/1.1" 200 2523429 "-" "curl/8.14.1" "10.64.50.136" cache=EXPIRED
10.64.49.118 - - [26/Feb/2026:12:36:56 +0000] "GET /DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE HTTP/1.1" 200 32591328 "-" "curl/8.14.1" "10.64.50.136" cache=HIT
10.64.49.118 - - [26/Feb/2026:12:45:18 +0000] "GET /DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE HTTP/1.1" 200 32591328 "-" "curl/8.14.1" "10.64.50.136" cache=HIT
```
