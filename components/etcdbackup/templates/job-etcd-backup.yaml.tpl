apiVersion: batch/v1
kind: CronJob
metadata:
  name: etcd-backup-job
  namespace: kube-system
  labels:
    {{- include "etcdbackup.labels" . | nindent 4 }}
spec:
  concurrencyPolicy: Forbid
  failedJobsHistoryLimit: 5
  jobTemplate:
    metadata:
      name: etcd-backup-cronjob-run
    spec:
      completions: 1
      template:
        metadata:
          name: etcd-backup-job-run
        spec:
          containers:
          - command:
            - etcdctl
            - --cert=/etc/kubernetes/pki/etcd/server.crt
            - --key=/etc/kubernetes/pki/etcd/server.key
            - --cacert=/etc/kubernetes/pki/etcd/ca.crt
            - --endpoints=127.0.0.1:2379
            - snapshot
            - save
            - /var/backups/{{ .Values.backup.fileName }}
            env:
            - name: ETCDCTL_API
              value: "3"
            image: registry.k8s.io/etcd:3.5.15-0
            imagePullPolicy: IfNotPresent
            name: snapshot
            resources: {}
            terminationMessagePath: /dev/termination-log
            terminationMessagePolicy: File
            volumeMounts:
            - mountPath: /var/lib/etcd
              name: etcd-data
            - mountPath: /etc/kubernetes/pki/etcd
              name: etcd-certs
            - mountPath: /var/backups
              name: backups
          dnsPolicy: ClusterFirst
          nodeName: {{ .Values.backup.nodeName }}
          hostNetwork: true
          restartPolicy: OnFailure
          schedulerName: default-scheduler
          securityContext: {}
          terminationGracePeriodSeconds: 30
          volumes:
          - hostPath:
              path: /etc/kubernetes/pki/etcd
              type: ""
            name: etcd-certs
          - hostPath:
              path: /var/lib/etcd
              type: ""
            name: etcd-data
          - hostPath:
              path: /var/backups
              type: ""
            name: backups
      ttlSecondsAfterFinished: 604800
  schedule: 0 0 * * *
  successfulJobsHistoryLimit: 3
  suspend: false
