import codecs
import os.path

from setuptools import setup

# Obtaining version number using recommended approach from
# https://packaging.python.org/guides/single-sourcing-package-version/
# This avoids problems that may arise from trying to import neutron_understack while
# it is not installed.


def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), "r") as fp:
        return fp.read()


def get_version(rel_path):
    for line in read(rel_path).splitlines():
        if line.startswith("__version__"):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")


setup(
    name="neutron_understack",
    version=get_version("neutron_understack/__init__.py"),
)
