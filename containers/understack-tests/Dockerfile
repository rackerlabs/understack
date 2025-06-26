FROM python:3.12-slim AS builder
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_COMPILE_BYTECODE=1
ENV PATH="/code/.venv/bin:/code/.bin:$PATH"

WORKDIR /code
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY python/understack-tests/uv.lock python/understack-tests/pyproject.toml /code/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --verbose --locked --no-dev
COPY python/understack-tests /code


FROM builder AS prod
WORKDIR /code
COPY --from=builder /code /code
RUN useradd --create-home app
COPY --chown=app:app containers/understack-tests/rally.conf /home/app/.rally/rally.conf
USER app
RUN rally db create
