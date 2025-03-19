{{- if .Values.mariadb.enabled -}}
---
apiVersion: k8s.mariadb.com/v1alpha1
kind: MariaDB
metadata:
  name: mariadb  # this name is referenced by other resource kinds
spec:
  rootPasswordSecretKeyRef:
    name: {{ .Values.mariadb.rootAuth.name }}
    key: {{ .Values.mariadb.rootAuth.key }}
    generate: {{ .Values.mariadb.rootAuth.generate }}

  # renovate: datasource=docker
  image: {{ .Values.mariadb.image.repository }}:{{ .Values.mariadb.image.tag }}
  imagePullPolicy: {{ .Values.mariadb.image.pullPolicy }}
  {{- with .Values.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}

  port: 3306
  storage:
    size: {{ .Values.mariadb.storage.size }}
    {{- if .Values.mariadb.storage.storageClassName }}
    storageClassName: {{ .Values.mariadb.storage.storageClassName }}
    {{- end }}
    resizeInUseVolumes: true
    waitForVolumeResize: true

  service:
    type: ClusterIP

  myCnf: |
    [mariadb]
    bind-address=*
    default_storage_engine=InnoDB
    binlog_format=row
    innodb_autoinc_lock_mode=2
    max_allowed_packet=256M

  metrics:
    enabled: true
    username: mariadb-metrics
    serviceMonitor:
      prometheusRelease: kube-prometheus-stack
      jobLabel: mariadb-monitoring
      interval: 10s
      scrapeTimeout: 10s
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
{{- end }}
