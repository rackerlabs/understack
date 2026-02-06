FROM ghcr.io/flant/shell-operator:v1.13.1 AS prod
LABEL org.opencontainers.image.description="shell-operator for Ironic Runbooks"

RUN --mount=type=cache,target=/var/cache/apk apk add python3
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY containers/shell-operator-ironic/requirements.txt requirements.txt
RUN pip install --no-cache --upgrade -r requirements.txt

COPY containers/shell-operator-ironic/hooks /hooks
