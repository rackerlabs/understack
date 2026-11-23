apiVersion: apps/v1
kind: Deployment
metadata:
  name: cdn-edge
  labels:
    app: cdn-edge
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cdn-edge
  strategy:
    # Avoid overlapping pods using the same persistent storage during upgrades.
    type: Recreate
    # Clear existing rolling-update settings so Argo CD can apply Recreate.
    rollingUpdate: null
  template:
    metadata:
      labels:
        app: cdn-edge
    spec:
      # Init container to set correct permissions on cache dir
      initContainers:
        - name: cache-dir-init
          image: busybox:1.36
          command: ["sh", "-c", "mkdir -p /var/cache/nginx/cdn && chown -R 101:101 /var/cache/nginx"]
          volumeMounts:
            - name: nginx-cache
              mountPath: /var/cache/nginx
{{- if .Values.supportassist.enabled }}
        - name: supportassist-dir-init
          image: busybox:1.36
          command: ["sh", "-c", "mkdir -p /var/lib/nginx/supportassist /var/lib/nginx/client_temp && chown 101:101 /var/lib/nginx/supportassist /var/lib/nginx/client_temp"]
          volumeMounts:
            - name: supportassist
              mountPath: /var/lib/nginx
{{- end }}

      containers:
        - name: nginx
          image: nginx:1.27-alpine
          ports:
            - containerPort: 8080
              name: http
{{- if .Values.supportassist.enabled }}
            - containerPort: 8081
              name: supportassist
{{- end }}

          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "2"
              memory: "1Gi"

          volumeMounts:
            - name: nginx-config
              mountPath: /etc/nginx/nginx.conf
              subPath: nginx.conf
            - name: nginx-config
              mountPath: /etc/nginx/conf.d/default.conf
              subPath: default.conf
            - name: nginx-cache
              mountPath: /var/cache/nginx
{{- if .Values.supportassist.enabled }}
            - name: supportassist
              mountPath: /var/lib/nginx
            - name: supportassist-auth
              mountPath: /etc/nginx/supportassist-auth
              readOnly: true
{{- end }}

          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10

          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 5

          # Graceful shutdown — let in-flight transfers complete
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5 && nginx -s quit"]

          securityContext:
            runAsNonRoot: true
            runAsUser: 101      # nginx user in nginx:alpine
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true

      volumes:
        - name: nginx-config
          configMap:
            name: nginx-config
        - name: nginx-cache
          persistentVolumeClaim:
            claimName: nginx-cache
{{- if .Values.supportassist.enabled }}
        - name: supportassist
          persistentVolumeClaim:
            claimName: supportassist
        - name: supportassist-auth
          secret:
            secretName: supportassist-download-auth
{{- end }}

      terminationGracePeriodSeconds: 30
