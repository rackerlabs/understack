# Development environment

In order to easily setup the development environment for `ironic_understack`:

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

- ironic
- pytest
- python 3.11
- Kubernetes tools (kubectl, [kubeseal][kubeseal], kustomize, [telepresence][telepresence])
- Argo client to interact with the Argo workflows

[telepresence]: https://www.telepresence.io/
[kubeseal]: https://github.com/bitnami-labs/sealed-secrets
