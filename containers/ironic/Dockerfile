# syntax=docker/dockerfile:1

FROM ubuntu:noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# setup requireements
# renovate: name=openstack/requirements repo=https://github.com/openstack/requirements.git branch=stable/2025.2
ARG REQUIREMENTS_GIT_REF=7d16424510c49daa913fc20a6300427b72522231
ADD --keep-git-dir=true https://github.com/openstack/requirements.git#${REQUIREMENTS_GIT_REF} /src/requirements

# clone source and patch it
# renovate: name=openstack/ironic repo=https://github.com/openstack/ironic.git branch=stable/2025.2
ARG IRONIC_GIT_REF=7c12f13ee57399e0a13f52eb5c3375cb9cf50be2
ADD --keep-git-dir=true https://github.com/openstack/ironic.git#${IRONIC_GIT_REF} /src/ironic
RUN git -C /src/ironic fetch --unshallow
#COPY patches/ironic /patches/ironic
#RUN git -C /src/ironic apply --verbose /patches/ironic/*

COPY bindep.txt /src/
RUN uvx bindep -f -b -l newline > /src/binpkgs.txt

# our local things
COPY python/ironic-understack /src/understack/ironic-understack
COPY python/understack-flavor-matcher /src/understack/understack-flavor-matcher

# now install everything
RUN --mount=type=cache,id=uv-default,target=/root/.cache/uv <<EOF bash -xe
uv pip install \
    --constraint /src/requirements/upper-constraints.txt \
        /src/ironic \
        /src/understack/ironic-understack \
        /src/understack/understack-flavor-matcher \
        proliantutils==2.16.3
EOF

FROM ubuntu:noble AS runtime

COPY --from=build --link /src/requirements/{global-requirements.txt,upper-constraints.txt} /
COPY --from=build --link /src/binpkgs.txt /

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        $(cat /src/binpkgs.txt) \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=build --link /var/lib/openstack /var/lib/openstack
