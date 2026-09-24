# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/cinder:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# renovate: name=openstack/cinder repo=https://github.com/rackerlabs/cinder.git branch=understack/2026.1
ARG CINDER_GIT_REF=bccccd4b4c2baab05b3620679499c474bb5b4c52
ADD --keep-git-dir=true https://github.com/rackerlabs/cinder.git#${CINDER_GIT_REF} /src/cinder
RUN git -C /src/cinder fetch --unshallow --tags

COPY python/cinder-understack /src/cinder-understack

ARG OPENSTACK_VERSION="required_argument"
ADD https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} /upper-constraints.txt

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --no-sources \
      --constraint /upper-constraints.txt \
        /src/cinder \
        /src/cinder-understack

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/cinder:${OPENSTACK_VERSION}-ubuntu_noble AS final

RUN rm -rf /var/lib/openstack
COPY --from=build --link /var/lib/openstack /var/lib/openstack
