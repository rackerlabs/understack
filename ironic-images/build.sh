#!/bin/sh
# used only for local testing
cd /code
export DIB_RELEASE=bookworm
export ELEMENTS_PATH=/code/.venv/share/ironic-python-agent-builder/dib:/code/custom_elements
export DIB_CLOUD_INIT_DATASOURCES="ConfigDrive, OpenStack, None"
diskimage-builder ./ipa-debian-bookworm.yaml
