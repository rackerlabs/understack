# Poor-man's CDN for serving firmware images

Images are stored in Object Store

Caching reverse-proxies at each fabric will fetch the images from Object Store
and make them available via HTTPS.

When enabled, the same pod also accepts SupportAssist HTTP uploads into a
dedicated `supportassist` PVC.

This allows a device to access firmware images via an HTTPS request to a
cluster-local tendot IP address.

## SupportAssist uploads

Enable `supportassist.enabled` in the site's CDN values to provision a dedicated
`supportassist` PVC. It defaults to `40Gi` on `openebs-lvm`; set
`supportassist.storageSize` and `supportassist.storageClassName` for the site.
Diagnostic archives are separate from the firmware cache and object bucket.

Route `/supportassist/` to Service `cdn-edge`, port **8081**, using an HTTPRoute
attached only to the internal gateway. The existing firmware Service port 80
does not expose uploads. Sites own this route; the CDN chart does not choose
a gateway or address. For iad3-dev, the share URL is
`http://10.46.100.83/supportassist/`. The IP-based route supports iDRACs without
DNS servers configured. Use the IP URL: the existing CDN hostname routes to
the firmware listener.

iDRAC appends the collection filename and sends a PUT with Content-Length and
the raw ZIP body. NGINX WebDAV writes the body to a temporary file on the same
PVC, then renames it into `/var/lib/nginx/supportassist/`. Only PUT beneath
`/supportassist/` is allowed; query strings are rejected. HTTP download,
listing and deletion are not exposed on this listener. Clients that can reach this
credential-free internal listener can upload or overwrite archives.

### Authenticated archive reads

With SupportAssist enabled, the chart requires a Secret named
`supportassist-download-auth` in the CDN namespace, with an `htpasswd` key
containing an NGINX-compatible password file. The pod does not start until it
exists. This exposes `/supportassist-archives/` on the existing
firmware listener (Service port 80). Use the existing HTTPS gateway hostname;
do not expose this password-protected endpoint over plain HTTP.

Authenticated GET/HEAD requests can list archives as JSON or read a ZIP. Other
methods are denied, and responses carry `Cache-Control: private, no-store`.
Uploads remain on the separate internal listener.

NodeDash can use a dedicated reader credential server-side, checking Ironic's
vendor passthru policy and reading only the selected node's UUID directory before returning
metadata or streaming a file. The CDN credential itself grants read access to
all archives; never give it to browser clients. There is no per-node policy in
NGINX. Rotate the password file and NodeDash credential together.

### Retrieval and capacity

Without NodeDash downloads configured, use Kubernetes access to find the pod
and copy a completed archive locally:

```sh
kubectl -n understack-cdn get pods -l app=cdn-edge
kubectl -n understack-cdn exec <pod-name> -c nginx -- ls -lh /var/lib/nginx/supportassist
kubectl -n understack-cdn cp <pod-name>:/var/lib/nginx/supportassist/<filename>.zip ./<filename>.zip -c nginx
```

Concurrent uploads share the PVC's available space; uploads fail when the
volume fills. Monitor free space, for example with
`kubectl -n understack-cdn exec <pod-name> -c nginx -- df -h /var/lib/nginx`.
NGINX permits 300 seconds without upload progress; the iad3-dev internal route
allows 15 minutes per request. Verify large collections against these limits
on the target iDRAC firmware.

Archives are retained on the PVC. Operators manage retention, capacity and
archiving. Archival storage after **90 days**
requires an archive destination and transfer mechanism; verify retrieval
before enabling it.

## Proxy configuration

The proxy edge service caches files locally on a persistent volume.

All files are proxied to our object bucket.  Anonymous credentials are used,
therefore we need to make the files in our bucket readable by anonymous if they
are to be accessible via HTTP.

## Uploading file to object storage

We have an ObjectBucket provisioned via rook/ceph.  The operator for our
ObjectBucketClaim creates credentials for us to access this bucket.

Our credentials and bucket info is in a secret and a configmap both named after
the bucketclaim:

``` sh
KEY_ID=`kubectl -n understack-cdn get secrets firmware-images -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d`
KEY=`kubectl -n understack-cdn get secrets firmware-images -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d`
```

### Using AWS CLI

Create a port-forward to the object store in the cluster:

``` sh
kubectl -n rook-ceph port-forward service/rook-ceph-rgw-ceph-objectstore 18082:80
```

Set AWS CLI settings using credentials from the cluster:

``` sh
export AWS_ACCESS_KEY_ID=$(kubectl -n understack-cdn get secret firmware-images -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)
export AWS_SECRET_ACCESS_KEY=$(kubectl -n understack-cdn get secret firmware-images -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)
export AWS_ENDPOINT_URL=http://localhost:18082   # AWS CLI v2.13+
export AWS_DEFAULT_REGION=us-east-1   # RGW ignores it, but the CLI wants one
```

Upload a file:

``` sh
aws s3 cp BIOS_MG8D3_WN64_1.8.26.EXE s3://firmware-images/DELL/XE7745/ --acl public-read
```

### Using minio CLI mc

I was able to manage the bucket using the minio CLI client called "mc".

``` sh
mc alias set myrook https://object-storage.dev.undercloud.rackspace.net/firmware-images/ $KEY_ID $KEY
mc anonymous set download myrook/firmware-images
mc cp DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE myrook/firmware-images/DELL/R7615/
mc anonymous set download myrook/firmware-images/DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE
```

## Testing with curl

curl https://cdn.dev.undercloud.rackspace.net/firmware-images/DELL/R7615/BIOS_H3TGJ_WN64_1.15.3.EXE | shasum

## See nginx logs to check that it is Caching

``` sh
⇒ kubectl -n understack-cdn logs deployments/cdn-edge
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
