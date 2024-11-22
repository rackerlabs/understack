"""Additional functions to process an Azure user."""

import logging
import os

from django.contrib.auth.models import Group


def _env_list(field: str) -> list[str]:
    data = os.getenv(field)
    if not data:
        return []
    if not isinstance(data, str):
        return []
    return data.split(",")


logger = logging.getLogger("auth.Dex")
GROUPS_ATTR_NAME = os.getenv("NAUTOBOT_SSO_CLAIMS_GROUP", "groups")
SUPERUSER_GROUPS = _env_list("NAUTOBOT_SSO_SUPERUSER_GROUPS")
STAFF_GROUPS = _env_list("NAUTOBOT_SSO_STAFF_GROUPS")


def group_sync(uid, user=None, response=None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg, unused-argument
    """Sync the users groups from the response and set staff/superuser as
    appropriate"""
    if user and response and response.get(GROUPS_ATTR_NAME, False):
        group_memberships = response.get(GROUPS_ATTR_NAME)
        is_staff = False
        is_superuser = False
        logger.debug("User %s is a member of %s", uid, {", ".join(group_memberships)})
        # Make sure all groups exist in Nautobot
        group_ids = []
        for group in group_memberships:
            if group in SUPERUSER_GROUPS:
                is_superuser = True
            if group in STAFF_GROUPS:
                is_staff = True
            group_ids.append(Group.objects.get_or_create(name=group)[0].id)
        user.groups.set(group_ids)
        user.is_superuser = is_superuser
        user.is_staff = is_staff
        user.save()
    else:
        logger.debug("Did not receive groups from Dex, response: %s", response)
