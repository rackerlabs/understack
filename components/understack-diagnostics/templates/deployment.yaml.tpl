apiVersion: apps/v1
kind: Deployment
metadata:
  name: diagnostics
  labels:
    app: diagnostics
spec:
  replicas: 1
  selector:
    matchLabels:
      app: diagnostics
  strategy:
    # The volume is ReadWriteOnce, so the old pod must stop first.
    type: Recreate
  template:
    metadata:
      labels:
        app: diagnostics
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/nginx-config.yaml.tpl") . | sha256sum }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 101      # nginx user in nginx:alpine
        fsGroup: 101        # makes the data volume writable by nginx
      containers:
        - name: nginx
          image: nginx:1.27-alpine
          ports:
            - name: upload
              containerPort: 8080
            - name: archives
              containerPort: 8081
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              memory: 512Mi
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: config
              mountPath: /etc/nginx/nginx.conf
              subPath: nginx.conf
            - name: data
              mountPath: /data
            - name: run
              mountPath: /var/cache/nginx
            - name: auth
              mountPath: /etc/nginx/auth
              readOnly: true
          livenessProbe:
            httpGet:
              path: /healthz
              port: upload
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /healthz
              port: upload
            periodSeconds: 5
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5 && nginx -s quit"]
      # Let in-flight uploads finish on a rollout.
      terminationGracePeriodSeconds: 60
      volumes:
        - name: config
          configMap:
            name: diagnostics-nginx
        - name: data
          persistentVolumeClaim:
            claimName: diagnostics
        - name: run
          emptyDir: {}
        - name: auth
          secret:
            secretName: diagnostics-download-auth
