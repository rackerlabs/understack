---
apiVersion: v1
kind: ConfigMap
metadata:
  name: mariadb
data:
  UMASK: "0660"
  UMASK_DIR: "0750"
