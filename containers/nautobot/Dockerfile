# renovate: datasource=docker depName=networktocode/nautobot versioning=semver
ARG NAUTOBOT_VERSION=3.0.2
ARG PYTHON_VERSION=3.12
ARG NAUTOBOT_CONTAINER_TYPE=""

FROM ghcr.io/nautobot/nautobot${NAUTOBOT_CONTAINER_TYPE}:${NAUTOBOT_VERSION}-py${PYTHON_VERSION} AS prod

LABEL org.opencontainers.image.source=https://github.com/rackerlabs/understack

ENV PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# install plugin_requirements to /opt/nautobot/ per the Nautobot Docker Compose example
COPY ./containers/nautobot/plugin_requirements.txt /opt/nautobot/
RUN pip install --no-warn-script-location -r /opt/nautobot/plugin_requirements.txt
# copy in a sample config
COPY ./containers/nautobot/nautobot_config.py /opt/nautobot_config/nautobot_config.py
# copy in the healthcheck script for celery beats
COPY ./containers/nautobot/scripts/nautobot_celery_beats_hcheck.py /opt/nautobot/
