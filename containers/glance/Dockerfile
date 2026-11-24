# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/glance:${OPENSTACK_VERSION}-ubuntu_noble AS final

# Required for using the Glance S3 backend
RUN /var/lib/openstack/bin/pip install boto3
