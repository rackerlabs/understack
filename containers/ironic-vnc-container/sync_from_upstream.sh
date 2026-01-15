#!/bin/bash
set -ex
UPSTREAM_COMMIT="856238c56acb669c8e10cf1f0e0f4e0c9467c7e9"

if ! [[ -f sync_from_upstream.sh ]]; then
  echo "Run ./sync_from_upstream.sh only from the containers/ironic-vnc-console folder."
  exit 1
fi

DST=$(mktemp -d)

git clone https://opendev.org/openstack/ironic.git "$DST" --depth 1 --revision "$UPSTREAM_COMMIT"

for folder in bin drivers extension; do
  rm -rf "$folder"
  cp -r "$DST/tools/vnc-container/$folder" "$folder"
done

cp "$DST/tools/vnc-container/Containerfile.ubuntu" Dockerfile
cp "$DST/LICENSE" LICENSE
rm -rf "$DST"

echo "# Attribution" > NOTICE
echo "Obtained from https://opendev.org/openstack/ironic.git /tools/vnc-container" >> NOTICE
echo "Upstream commit: $UPSTREAM_COMMIT" >> NOTICE
