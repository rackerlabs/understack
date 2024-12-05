#!/bin/sh
# Requires the Operator to be installed in the cluster already
helm -n default -f test-values.yaml upgrade --install  understackdb .
helm -n default test understackdb
helm -n default uninstall understackdb
kubectl -n default delete pvc storage-test-mariadb-0
