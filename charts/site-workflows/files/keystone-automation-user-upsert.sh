#!/bin/sh
echo "Received Secret Event ${EVENT_TYPE} for ${SECRET_NAME}"
set -x
# roles are a comma separated annotation; fall back to the legacy label
SVC_ROLES=${ROLES_ANNOTATION:-$(python -c "import json,os; print(json.loads(os.environ.get('LABELS') or '{}').get('understack.rackspace.com/keystone-role',''))")}
SVC_ROLES=$(printf '%s' "${SVC_ROLES}" | tr -d '[:space:]')
SVC_USER=$(python -c "import json,os; print(json.loads(os.environ.get('LABELS') or '{}').get('understack.rackspace.com/keystone-user',''))")
SVC_USER=${SVC_USER:-$SECRET_NAME}
PROJ_ID=$(openstack project create --or-show --domain service automation -f value -c id)
SVC_ID=$(openstack user create --or-show --domain service --project "${PROJ_ID}" --description "${SECRET_NAME}" "${SVC_USER}" -f value -c id)
openstack user set --description "${SECRET_NAME}" --project "${PROJ_ID}" "${SVC_ID}"
set +x
svc_pass=$(cat /tmp/user-create/password)
if [ -z "${svc_pass}" ]; then
  echo "Empty password supplied, skipping setting the password"
else
  if OS_USERNAME="${SVC_USER}" OS_PASSWORD="${svc_pass}" OS_USER_DOMAIN_NAME=service OS_PROJECT_NAME=automation OS_PROJECT_DOMAIN_NAME=service openstack token issue > /dev/null 2>&1; then
    echo "Password for ${SVC_ID} is already correct, skipping update."
  else
    openstack user set --password "${svc_pass}" "${SVC_ID}"
    echo "Password for ${SVC_ID} was set."
  fi
fi
set -x
openstack role add --user "${SVC_ID}" --project "${PROJ_ID}" reader
set -f
OLD_IFS=${IFS}
IFS=','
for svc_role in ${SVC_ROLES}; do
  case ${svc_role} in
  tenant-read)
    openstack role add --user "${SVC_ID}" --domain default --inherited reader
    ;;
  tenant-readwrite)
    openstack role add --user "${SVC_ID}" --domain default --inherited member
    ;;
  tenant-admin)
    openstack role add --user "${SVC_ID}" --domain default admin
    ;;
  infra-read)
    openstack role add --user "${SVC_ID}" --project-domain infra --project baremetal reader
    ;;
  infra-readwrite)
    openstack role add --user "${SVC_ID}" --project-domain infra --project baremetal admin
    ;;
  system-readwrite)
    openstack role add --user "${SVC_ID}" --system all reader
    openstack role add --user "${SVC_ID}" --system all member
    ;;
  *)
    echo "Invalid role ${svc_role}"
    ;;
  esac
done
IFS=${OLD_IFS}
set +f
