#!/bin/bash
set -ex
UPSTREAM_REPO="https://opendev.org/openstack/ironic.git"
UPSTREAM_COMMIT="9ed35c6360ea02a8c90c53bb38425eb1902f4ca6"

if ! [[ -f sync_from_upstream.sh ]]; then
  echo "Run ./sync_from_upstream.sh only from the containers/ironic-vnc-console folder."
  exit 1
fi

DST=$(mktemp -d)

git clone "$UPSTREAM_REPO" "$DST" --depth 1 --revision "$UPSTREAM_COMMIT"

for folder in bin drivers extension; do
  rm -rf "$folder"
  cp -r "$DST/tools/vnc-container/$folder" "$folder"
done

cp "$DST/tools/vnc-container/Containerfile.ubuntu" Dockerfile
cp "$DST/LICENSE" LICENSE
rm -rf "$DST"

echo "# Attribution" > NOTICE
echo "Obtained from $UPSTREAM_REPO /tools/vnc-container" >> NOTICE
echo "Upstream commit: $UPSTREAM_COMMIT" >> NOTICE
