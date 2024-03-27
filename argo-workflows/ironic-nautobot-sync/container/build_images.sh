docker build -t registry.sno.rackspace.net/undercloud/argo-ironic:0.0.1 -f Dockerfile.ironic .
kind --name understack load docker-image registry.sno.rackspace.net/undercloud/argo-ironic:0.0.1
