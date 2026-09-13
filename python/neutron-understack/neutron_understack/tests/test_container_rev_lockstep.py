"""Enforce that the test env and the container build use the same neutron.

The scenario tests' guarantee -- "validate ML2 behavior against the same neutron
the container ships" -- only holds if the git revs pinned in this package's
[tool.uv.sources] match containers/neutron/Dockerfile's ARGs. This test fails if
they drift (e.g. a partial Renovate bump), rather than relying on a comment.
"""

import re
import tomllib
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOCKERFILE = _REPO_ROOT / "containers" / "neutron" / "Dockerfile"

# (uv.sources key, Dockerfile ARG name)
_PINS = [
    ("neutron", "NEUTRON_GIT_REF"),
    ("neutron-lib", "NEUTRON_LIB_GIT_REF"),
]


def _uv_source_rev(name):
    data = tomllib.loads((_PKG_ROOT / "pyproject.toml").read_text())
    return data["tool"]["uv"]["sources"][name]["rev"]


def _dockerfile_arg(text, arg):
    match = re.search(rf"^ARG {arg}=(\S+)", text, re.MULTILINE)
    return match.group(1) if match else None


@pytest.mark.parametrize(("source_key", "arg_name"), _PINS)
def test_neutron_rev_matches_container(source_key, arg_name):
    if not _DOCKERFILE.exists():
        pytest.skip(f"Dockerfile not found at {_DOCKERFILE} (not a repo checkout)")
    uv_rev = _uv_source_rev(source_key)
    docker_rev = _dockerfile_arg(_DOCKERFILE.read_text(), arg_name)
    assert uv_rev == docker_rev, (
        f"{source_key} rev drift: pyproject [tool.uv.sources]={uv_rev} but "
        f"Dockerfile {arg_name}={docker_rev}. Keep them in lockstep."
    )
