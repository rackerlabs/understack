---
apiVersion: k8s.mariadb.com/v1alpha1
kind: MariaDB
metadata:
  name: mariadb  # this name is referenced by other resource kinds
  annotations:
    # do not allow ArgoCD to delete our DB
    argocd.argoproj.io/sync-options: Delete=false
spec:
  rootPasswordSecretKeyRef: {{ .Values.mariadb.rootPasswordSecretKeyRef | toJson }}

  # renovate: datasource=docker
  image: docker-registry1.mariadb.com/library/mariadb:11.4.4
  imagePullPolicy: IfNotPresent

  port: 3306
  storage: {{ .Values.mariadb.storage | toJson }}
  replicas: {{ .Values.mariadb.replicas }}
  service:
    type: ClusterIP

  myCnf: |
    [mariadb]
    bind-address=*
    default_storage_engine=InnoDB
    binlog_format=row
    innodb_autoinc_lock_mode=2
    max_allowed_packet=256M
    max_connections=1024
    innodb_flush_log_at_trx_commit=2
    innodb_buffer_pool_size=256M

  metrics:
    enabled: true
    username: mariadb-metrics
    serviceMonitor:
      prometheusRelease: kube-prometheus-stack
      jobLabel: mariadb-monitoring
      interval: 10s
      scrapeTimeout: 10s

  galera:
    enabled: true
    sst: mariabackup
    replicaThreads: 1
    agent:
      port: 5555
      kubernetesAuth:
        enabled: true
    recovery:
      enabled: true
      clusterHealthyTimeout: 2m
      clusterBootstrapTimeout: 10m
    config:
      reuseStorageVolume: false
      volumeClaimTemplate:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: 1Gi
        storageClassName: ceph-block-single

---
# mariadb-operator backups for openstack
# https://github.com/mariadb-operator/mariadb-operator/blob/main/docs/BACKUP.md
apiVersion: k8s.mariadb.com/v1alpha1
kind: Backup
metadata:
  name: backup
spec:
  mariaDbRef:
    name: mariadb
  maxRetention: 168h  # 7 days
  schedule:
    cron: "0 */1 * * *"
    suspend: false
  args:
    - --verbose
  storage:
    persistentVolumeClaim:
      resources:
        requests:
          storage: 20Gi
      accessModes:
        - ReadWriteOnce
---
