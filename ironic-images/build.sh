cd /code
export DIB_RELEASE=bookworm
export ELEMENTS_PATH=/code/.venv/share/ironic-python-agent-builder/dib:/code/custom_elements
diskimage-builder ./ipa-debian-bookworm.yaml
