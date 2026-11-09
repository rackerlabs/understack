# Development environment

In order to easily setup the development environment for `neutron_understack`:

1. [Install Devbox](https://www.jetify.com/devbox/docs/installing_devbox/) if
   you don't have it yet.
2. Start using the environment with one of the methods described below

That's it.

## Automated method (recommended)

If you want the environment to be started automatically when you `cd` into a
project directory (without you having to run `devenv shell`), run a one-time
command:

`devbox generate direnv`

You also need to have [direnv](https://direnv.net/docs/installation.html)
installed on your system.

The next time you change into the project directory you will have the
environment ready to use.

## Manual method

Run `devbox shell` in the project directory every time you want to enter
development environment.

## What's available in the environment

- Neutron and neutron-lib
- pytest
- python 3.11
- argo client to interact with the Argo workflows

## Running the tests

This package is installed into the OpenStack `neutron` container using the
release's upper-constraints, so it has no `uv.lock`. Install and test it with
the same constraints (`uv sync` and `uv run` can't take a constraints file, so
use `uv pip`; `neutron-lib` is dropped from the constraints because the fork
in `[tool.uv.sources]` provides it):

```bash
uv venv
uv pip install -e . --group test \
  --constraint <(curl -fsSL https://releases.openstack.org/constraints/upper/2026.1 | grep -v '^neutron-lib===')
uv run --no-sync pytest
```

Use the release that matches `OPENSTACK_VERSION` in
`.github/workflows/code-test.yaml`.
