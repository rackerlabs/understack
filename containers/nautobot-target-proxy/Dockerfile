FROM python:3.12.13-alpine AS builder

RUN pip install --upgrade poetry poetry-plugin-export

COPY python/nautobot_target_proxy/pyproject.toml \
  python/nautobot_target_proxy/poetry.lock \
  /tmp/nautobot_target_proxy/

RUN cd /tmp/nautobot_target_proxy && \
  poetry export --only main -o /tmp/requirements.txt --without-hashes

FROM python:3.12.13-alpine AS prod

RUN pip3 install -U pip setuptools wheel

COPY --from=builder /tmp/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

COPY python/nautobot_target_proxy /app
RUN pip3 install --no-deps /app

WORKDIR /app
EXPOSE 8000
