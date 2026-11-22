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
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
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

{{- if .Values.supportassist.enabled }}
        - name: supportassist-signer
          image: public.ecr.aws/aws-observability/aws-sigv4-proxy:1.13
          args:
            - --port=127.0.0.1:8082
            - --name=s3
            - --region=us-east-1
            - --host=$(BUCKET_HOST):$(BUCKET_PORT)
            - --upstream-url-scheme=http
          envFrom:
            - secretRef:
                name: supportassist
          env:
            - name: BUCKET_HOST
              valueFrom:
                configMapKeyRef:
                  name: supportassist
                  key: BUCKET_HOST
            - name: BUCKET_PORT
              valueFrom:
                configMapKeyRef:
                  name: supportassist
                  key: BUCKET_PORT
            - name: GOMEMLIMIT
              value: 3GiB
          # v1.13 buffers the body twice. NGINX admits one upload up to 1 GiB.
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: "2"
              memory: 6Gi
          securityContext:
            runAsNonRoot: true
            runAsUser: 101
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
{{- end }}

      volumes:
        - name: nginx-config
          configMap:
            name: nginx-config
        - name: nginx-cache
          persistentVolumeClaim:
            claimName: nginx-cache

      terminationGracePeriodSeconds: 30
