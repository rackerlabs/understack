# Poor-man's CDN for serving firmware images

Images are stored in Object Store

Caching reverse-proxies at each fabric will fetch the images from Object Store
and make them available via HTTPS.

When enabled, the same pod also accepts SupportAssist HTTP uploads into a
separate private `supportassist` bucket.

This allows a device to access firmware images via an HTTPS request to a
cluster-local tendot IP address.

## SupportAssist uploads

Enable `supportassist.enabled` in the site's CDN values to provision a local
`supportassist` ObjectBucketClaim and start the signing sidecar. Its bucket
quota defaults to `40G` (`supportassist.bucketMaxSize`). Rook supplies the
endpoint ConfigMap and credentials Secret, both named `supportassist`. No
anonymous bucket policy is needed. Firmware configuration is unchanged.

Route `/supportassist/` to Service `cdn-edge`, port **8081**, using an HTTPRoute
attached only to the internal gateway. The existing firmware Service port 80
does not expose uploads. Sites own this route; the CDN chart does not choose
a gateway or address. For iad3-dev, the share URL is
`http://10.46.100.83/supportassist/`. The IP-based route supports iDRACs without
DNS servers configured. Use the IP URL: the existing CDN hostname routes to
the firmware listener.

iDRAC appends the collection filename and sends a PUT with Content-Length and
the raw ZIP body. NGINX streams it to a loopback-only AWS SigV4 proxy, which
signs the request for RGW with the generated bucket credentials. NGINX accepts
only PUT beneath `/supportassist/`, rejects query strings and strips incoming
headers before forwarding. GET, listing, deletion, ACL changes and S3 copy
requests are not exposed through this listener. Retrieve archives with an
authenticated S3 client using the `supportassist` bucket credentials.

### Retention and archiving

Collections have no automatic expiration or archive transition. The bucket's
`40G` default quota limits capacity; it does not remove old collections.
Operators must manage capacity until a lifecycle policy is configured.

A transition to archival storage after **90 days** is deferred. Repository
configuration and live iad3-dev RGW settings checked on 2026-11-21 provide
only the `STANDARD` object-storage class, backed by a 2+1 erasure-coded pool,
with no archive tier or external archive destination. Another bucket on that
same pool would not reduce storage usage or cost.

Revisit the 90-day transition once an archive destination is available, and
verify retrieval behavior before enabling it. Automatic deletion is not part
of the agreed policy.

### Upload limits and memory

The pinned [AWS SigV4 proxy v1.13 source](https://github.com/awslabs/aws-sigv4-proxy/blob/v1.13/handler/proxy_client.go)
buffers the complete body twice, even with `--unsigned-payload`. NGINX request
buffering is disabled, but this does not remove the signer's buffers. Uploads
therefore have these explicit limits:

- Maximum archive: **1 GiB**; larger requests return HTTP 413.
- One active upload per CDN pod, shared across NGINX workers. An overlapping
  upload returns HTTP 503 and must be retried later; it is not queued.
- Signer memory limit: **6 GiB**, with Go's soft memory target at 3 GiB.
  Its 128 MiB memory request covers idle operation, not peak upload demand;
  the node needs headroom for a large collection.

A local test of the pinned proxy source on macOS/amd64 with Go 1.27.3 measured
peak signer RSS of about 910 MiB for a 256 MiB body and 3.16 GiB for a 1 GiB
body. These are development measurements, not Kubernetes container results;
verify peak memory against the deployed image before increasing size or
concurrency. The container memory limit remains the final bound, including
requests that outlive a disconnected or timed-out client. An OOM restart will
fail affected uploads. NGINX's active-request limit does not cancel work
already running in the signer.

The internal route allows 15 minutes per request. NGINX allows 300 seconds
without upload progress and 600 seconds without a response from the signer.
Firmware downloads do not share the upload concurrency limit. Archives go to
RGW, not the firmware cache PVC. This is a credential-free internal ingress;
clients that can reach it can upload or overwrite objects in the bucket.

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
