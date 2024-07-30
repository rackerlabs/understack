ARG BASE=ghcr.io/rackerlabs/understack/argo-python3.11.8-alpine3.19:latest

FROM ${BASE} as builder

ARG APP_PATH=/app
ARG APP_USER=appuser
ARG APP_GROUP=appgroup
ARG APP_USER_UID=1000
ARG APP_GROUP_GID=1000

COPY --chown=${APP_USER}:${APP_GROUP} containers/requirements.txt /app
RUN --mount=type=cache,target=/var/cache/apk apk add --virtual build-deps gcc python3-dev musl-dev linux-headers
RUN --mount=type=cache,target=/root/.cache/.pip pip install --no-cache-dir -r /app/requirements.txt

FROM ${BASE} as prod

LABEL org.opencontainers.image.title="Python 3.11 image with pynautobot"
LABEL org.opencontainers.image.base.name="ghcr.io/rackerlabs/understack/nautobot-update-cf"
LABEL org.opencontainers.image.source=https://github.com/rackerlabs/understack


ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

USER $APP_USER

COPY --chown=${APP_USER}:${APP_GROUP} code/ /app
CMD ["python", "/app/main.py"]
