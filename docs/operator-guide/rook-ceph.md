# Rook Ceph

UnderStack uses Ceph primarily as an OpenStack Glance backend and for pod volumes.

## Accessing Ceph Dashboard

The Ceph admin dashboard is not exposed publicly so a port-forward needs to be
created and then you'll be able to access the Ceph UI.

``` bash
kubectl -n rook-ceph port-forward service/rook-ceph-mgr-dashboard 8443:8443
```

Once the port-forward is running, you can browse to <https://localhost:8443/> to access the Ceph admin dashboard.

### Getting Ceph admin credentials

Username: `admin`

Password:

``` bash
kubectl -n rook-ceph get secret rook-ceph-dashboard-password -o jsonpath="{.data.password}" | base64 --decode && echo
```
