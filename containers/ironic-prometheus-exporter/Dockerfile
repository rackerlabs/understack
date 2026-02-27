FROM python:3.12-slim AS prod

ENV PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      git \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY containers/ironic-prometheus-exporter/requirements.txt /

RUN --mount=type=cache,target=/root/.cache/pip pip install -r /requirements.txt dumb-init==1.2.5

RUN useradd -m -d /runner -s /bin/bash runner
WORKDIR /runner
USER runner

# RUN --mount=type=cache,target=/root/.cache/pip ansible-galaxy collection install -r /requirements.yml

# ENTRYPOINT ["dumb-init"]
# CMD ["ansible-runner"]
CMD ["python", "-m", "flask", "run"]
# gunicorn3 -b <ip_address>:9608 \
#   --env IRONIC_CONFIG=$IRONIC_CONFIG \
#   --env FLASK_DEBUG=1 -w 4 \
#   --access-logfile=ipe_access.log \
#   --error-logfile=ipe_errors.log \
#   -D ironic_prometheus_exporter.app.wsgi:application
# CMD [
#     "gunicorn", "-b", "0.0.0.0:9608"
# ]
