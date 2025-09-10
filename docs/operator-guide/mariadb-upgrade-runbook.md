# MariaDB Operator Upgrade Runbook

This runbook describes the steps to upgrade the **MariaDB Operator** and perform backup/restore procedures in Kubernetes.

---

## Pre-Upgrade Steps

### 1. Backup current MariaDB configuration

```bash
kubectl get mariadb -A -o yaml > current-mariadb-config-backup-$(date +%Y%m%d).yaml
```

### 2. Retrieve root password

```bash
export MARIADB_ROOT_PASSWORD=$(kubectl get secret mariadb -n openstack -o jsonpath='{.data.root-password}' | base64 -d)
```

### 3. Assess database sizes and usage

```bash
kubectl exec -n openstack -it mariadb-0 -- mariadb -u root -p"$MARIADB_ROOT_PASSWORD"
```

Run inside MariaDB shell:

```sql
SELECT
  table_schema AS 'Database',
  ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size_MB'
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
GROUP BY table_schema
ORDER BY Size_MB DESC;
```

### 4. Backup all databases

```bash
kubectl exec -n openstack -it mariadb-0 -- mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" \
  --single-transaction \
  --routines \
  --triggers \
  --all-databases > full-backup-$(date +%Y%m%d-%H%M).sql
```

### 5. Verify storage classes

- StorageClass specified for MariaDB should exists

```bash
kubectl get storageclass
```

---

## Upgrade MariaDB Operator

### 6. Update Mariadb Operator version

- Edit operator reference in:
   [kustomization.yaml](https://github.com/rackerlabs/understack/blob/main/operators/mariadb-operator/kustomization.yaml)

### 7. Perform the release

 [Release Process Documentation](https://docs.undercloud.rackspace.net/technical-documentation/release_process/#creating-an-understack-release)

---

## Validate Upgrade

### 8. Check applications in ArgoCD

- **Dev:**
    - [ArgoCD Dev 1](https://argocd.dev.undercloud.rackspace.net)
    - [ArgoCD Dev 2](https://dev-argocd.pvceng.rax.io/)

- **Staging / Prod:**
    - [ArgoCD](https://argocd.pvceng.rax.io/)

Applications:

- `<deploy-cluster>-mariadb-operator` (ex: `charlie-uc-iad3-staging-mariadb-operator`)
- `<deploy-cluster>-openstack` (ex: `charlie-uc-iad3-staging-openstack`)

### 9. Check logs in MariaDB StatefulSet

```bash
kubectl logs -n openstack statefulset/mariadb -f
```

### 10. Check logs in MariaDB Operator

```bash
kubectl logs -n mariadb-operator deployment/mariadb-operator -f
```

---

## Emergency Cleanup

If you encounter **volume mount issues**:

```bash
kubectl patch mariadb mariadb -n openstack --type='merge' -p='{"metadata":{"finalizers":[]}}'
kubectl delete mariadb mariadb -n openstack
kubectl delete pvc -n openstack -l app.kubernetes.io/name=mariadb --wait=false
```

---

## Restore Procedure

### 11. Get new root password

```bash
export MARIADB_ROOT_PASSWORD=$(kubectl get secret mariadb -n openstack -o jsonpath='{.data.root-password}' | base64 -d)
```

### 12. Restore from backup if volumes has been deleted

```bash
kubectl exec -i -n openstack mariadb-0 -- mariadb -u root -p"$MARIADB_ROOT_PASSWORD" < full-backup-production-20250910-0735.sql
```

### 13. Re-check database sizes

```bash
kubectl exec -n openstack -it mariadb-0 -- mariadb -u root -p"$MARIADB_ROOT_PASSWORD"
```

Run SQL again:

```sql
SELECT
  table_schema AS 'Database',
  ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size_MB'
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
GROUP BY table_schema
ORDER BY Size_MB DESC;
```

---

## Post-Upgrade Connectivity Check

### 14. Test Galera peer connectivity

```bash
kubectl exec mariadb-0 -n openstack -- timeout 5 bash -c "echo > /dev/tcp/mariadb-1.mariadb-internal.openstack.svc.cluster.local/4567" && echo "mariadb-1 reachable" || echo "mariadb-1 not reachable"

kubectl exec mariadb-0 -n openstack -- timeout 5 bash -c "echo > /dev/tcp/mariadb-2.mariadb-internal.openstack.svc.cluster.local/4567" && echo "mariadb-2 reachable" || echo "mariadb-2 not reachable"
```

---

## End of Runbook
