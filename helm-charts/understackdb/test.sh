#!/bin/sh
# Requires the Operator to be installed in the cluster already
helm -n default -f test-values.yaml upgrade --install  understackdb .
helm -n default test understackdb
