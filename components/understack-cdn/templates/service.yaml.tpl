apiVersion: v1
kind: Service
metadata:
  name: cdn-edge
spec:
  selector:
    app: cdn-edge
  ports:
    - name: http
      port: 80
      targetPort: 8080
{{- if .Values.supportassist.enabled }}
    - name: supportassist
      port: 8081
      targetPort: supportassist
{{- end }}
  type: ClusterIP
