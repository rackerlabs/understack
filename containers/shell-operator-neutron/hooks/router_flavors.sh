#!/usr/bin/env bash

set -euo pipefail

if [[ "${1:-}" == "--config" ]] ; then
  cat <<EOF
{
  "configVersion":"v1",
  "onStartup": 1,
  "settings": {
    "executionMinInterval": "30s",
    "executionBurst": 1
  }
}
EOF
  exit 0
fi

CONFIG_PATH="${NEUTRON_ROUTER_FLAVORS_CONFIG:-/etc/neutron-router-flavors/flavors.json}"
DEFAULT_SERVICE_TYPE="${NEUTRON_ROUTER_FLAVOR_SERVICE_TYPE:-L3_ROUTER_NAT}"
OPENSTACK_READY_RETRIES="${NEUTRON_ROUTER_FLAVOR_READY_RETRIES:-30}"
OPENSTACK_READY_DELAY="${NEUTRON_ROUTER_FLAVOR_READY_DELAY:-10}"

log() {
  echo "[router_flavors] $*" >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Required command '$1' is not available"
    exit 1
  fi
}

json_field() {
  local object="$1"
  local filter="$2"

  jq -r "${filter} // empty" <<< "${object}"
}

normalize_json() {
  jq -cS . <<< "$1"
}

wait_for_openstack_network() {
  local attempt

  for ((attempt = 1; attempt <= OPENSTACK_READY_RETRIES; attempt++)); do
    if openstack network flavor list -f value -c ID >/dev/null 2>&1; then
      return
    fi

    if (( attempt < OPENSTACK_READY_RETRIES )); then
      log "Waiting for Neutron API (${attempt}/${OPENSTACK_READY_RETRIES})"
      sleep "${OPENSTACK_READY_DELAY}"
    fi
  done

  log "Neutron API did not become ready after ${OPENSTACK_READY_RETRIES} attempt(s)"
  exit 1
}

profile_id_from_json() {
  jq -r '.id // .ID // .Id // empty'
}

find_matching_profile_id() {
  local driver="$1"
  local metainfo="$2"
  local normalized_metainfo

  normalized_metainfo="$(normalize_json "${metainfo}")"

  openstack network flavor profile list -f json | jq -r \
    --arg driver "${driver}" \
    --arg metainfo "${normalized_metainfo}" '
      def parse_metainfo:
        if type == "object" then
          .
        elif type == "string" then
          (try fromjson catch (try (gsub("'"'"'"; "\"") | fromjson) catch null))
        else
          null
        end;

      def normalize:
        if . == null then
          ""
        else
          to_entries | sort_by(.key) | from_entries | tojson
        end;

      [
        .[]
        | select((.driver // .Driver // "") == $driver)
        | select(((.metainfo // .Metainfo // "{}") | parse_metainfo | normalize) == $metainfo)
        | .id // .ID // .Id
      ][0] // ""
    '
}

ensure_profile() {
  local name="$1"
  local driver="$2"
  local description="$3"
  local metainfo="$4"
  local profile_id="$5"
  local normalized_metainfo output

  normalized_metainfo="$(normalize_json "${metainfo}")"

  if [[ -n "${profile_id}" ]]; then
    if openstack network flavor profile show "${profile_id}" >/dev/null 2>&1; then
      log "Using configured service profile ${profile_id} for ${name}"
      echo "${profile_id}"
      return
    fi

    log "Configured service profile ${profile_id} for ${name} was not found"
  fi

  profile_id="$(find_matching_profile_id "${driver}" "${normalized_metainfo}")"
  if [[ -n "${profile_id}" ]]; then
    log "Reusing service profile ${profile_id} for ${name}"
    openstack network flavor profile set \
      --description "${description}" \
      --metainfo "${normalized_metainfo}" \
      "${profile_id}" >/dev/null
    echo "${profile_id}"
    return
  fi

  log "Creating service profile for ${name} driver=${driver}"
  output="$(openstack network flavor profile create \
    --enable \
    --driver "${driver}" \
    --metainfo "${normalized_metainfo}" \
    --description "${description}" \
    -f json)"
  profile_id="$(profile_id_from_json <<< "${output}")"

  if [[ -z "${profile_id}" ]]; then
    log "Unable to parse service profile ID from: ${output}"
    return 1
  fi

  echo "${profile_id}"
}

ensure_flavor() {
  local name="$1"
  local service_type="$2"
  local description="$3"
  local command_args

  if openstack network flavor show "${name}" >/dev/null 2>&1; then
    log "Router flavor ${name} already exists"
    if [[ -n "${description}" ]]; then
      openstack network flavor set --description "${description}" "${name}" >/dev/null
    fi
    return
  fi

  command_args=(network flavor create --service-type "${service_type}")
  if [[ -n "${description}" ]]; then
    command_args+=(--description "${description}")
  fi
  command_args+=("${name}")

  log "Creating router flavor ${name} service_type=${service_type}"
  openstack "${command_args[@]}" >/dev/null
}

flavor_has_profile() {
  local flavor="$1"
  local profile_id="$2"

  openstack network flavor show "${flavor}" -f json | jq -e \
    --arg profile_id "${profile_id}" '
      (.service_profile_ids
        // .service_profiles
        // .profiles
        // .["Service Profile IDs"]
        // .["Service profiles"]
        // .["Service Profiles"]
        // []) as $profiles
      | if ($profiles | type) == "array" then
          $profiles | index($profile_id)
        else
          ($profiles | tostring | contains($profile_id))
        end
    ' >/dev/null
}

ensure_profile_attached() {
  local flavor="$1"
  local profile_id="$2"
  local output

  if flavor_has_profile "${flavor}" "${profile_id}"; then
    log "Router flavor ${flavor} already has service profile ${profile_id}"
    return
  fi

  log "Binding service profile ${profile_id} to router flavor ${flavor}"
  if ! output="$(openstack network flavor add profile "${flavor}" "${profile_id}" 2>&1)"; then
    if grep -qi "already" <<< "${output}"; then
      log "Router flavor ${flavor} already has service profile ${profile_id}"
      return
    fi

    log "${output}"
    return 1
  fi
}

sync_flavor() {
  local flavor="$1"
  local name driver profile_description metainfo service_type description profile_id
  local resolved_profile_id

  name="$(json_field "${flavor}" '.name')"
  driver="$(json_field "${flavor}" '.driver')"
  profile_description="$(json_field "${flavor}" '.profile_description')"
  description="$(json_field "${flavor}" '.description')"
  service_type="$(json_field "${flavor}" '.service_type')"
  profile_id="$(json_field "${flavor}" '.profile_id')"
  metainfo="$(jq -c '.metainfo // {}' <<< "${flavor}")"

  if [[ -z "${name}" || -z "${driver}" ]]; then
    log "Each router flavor entry must define name and driver: ${flavor}"
    return 1
  fi

  if [[ -z "${service_type}" ]]; then
    service_type="${DEFAULT_SERVICE_TYPE}"
  fi
  if [[ -z "${profile_description}" ]]; then
    profile_description="${description}"
  fi

  log "Reconciling router flavor ${name}"
  resolved_profile_id="$(ensure_profile "${name}" "${driver}" "${profile_description}" "${metainfo}" "${profile_id}")"
  if [[ -z "${resolved_profile_id}" ]]; then
    log "Unable to resolve service profile for ${name}"
    return 1
  fi

  ensure_flavor "${name}" "${service_type}" "${description}"
  ensure_profile_attached "${name}" "${resolved_profile_id}"
  openstack network flavor show "${name}"
}

require_command jq
require_command openstack

if [[ ! -f "${CONFIG_PATH}" ]]; then
  log "Router flavor config not found at ${CONFIG_PATH}"
  exit 1
fi

jq -e '.router_flavors | type == "array"' "${CONFIG_PATH}" >/dev/null
wait_for_openstack_network

flavor_count="$(jq -r '.router_flavors | length' "${CONFIG_PATH}")"
log "Found ${flavor_count} router flavor(s) to reconcile"

for ((i = 0; i < flavor_count; i++)); do
  sync_flavor "$(jq -c ".router_flavors[${i}]" "${CONFIG_PATH}")"
done

log "Finished reconciling router flavors"
