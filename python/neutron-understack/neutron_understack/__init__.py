__version__ = "0.1"

# Neutron's extension loader looks for ``<service_plugin_root>.extensions`` as
# an attribute on the imported top-level package.
from neutron_understack import extensions  # noqa: F401
