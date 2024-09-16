#!/bin/bash

# elements path - need to include both the ironic-python-agent-builder DIB packages
# and our custom_elements packages
# export ELEMENTS_PATH=/path/to/venv/share/ironic-python-agent-builder/dib:/path/to/custom_elements

# distro version
export DIB_RELEASE=bookworm

diskimage-builder ipa-debian-bookworm.yaml
