# RabbitMQ Cheat Sheet

## Get Admin Username and Password

```bash
# Username
admin
# Password
kubectl -n rook-ceph get secret rook-ceph-dashboard-password -o jsonpath="{.data.password}" | base64 --decode && echo
```

## Opening the Ceph Dashboard

```bash
kubectl -n rook-ceph port-forward service/rook-ceph-mgr-dashboard 8443:8443
```

Then open <https://localhost:8443/> in your web browser and log in using the credentials from above.
