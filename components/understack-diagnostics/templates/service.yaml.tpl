apiVersion: v1
kind: Service
metadata:
  name: diagnostics
  labels:
    app: diagnostics
spec:
  selector:
    app: diagnostics
  ports:
    # Uploads (PUT). Route only from the internal gateway.
    - name: upload
      port: 8080
      targetPort: upload
    # Authenticated reads. Route only over HTTPS.
    - name: archives
      port: 8081
      targetPort: archives
  type: ClusterIP
