import os

from nautobot.core.settings import *  # noqa F401,F403
from nautobot.core.settings import DATABASES

#########################
#                       #
#   Required settings   #
#                       #
#########################

# Ensure proper Unicode handling for MySQL
#
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}

# This key is used for secure generation of random numbers and strings. It must never be exposed outside of this file.
# For optimal security, SECRET_KEY should be at least 50 characters in length and contain a mix of letters, numbers, and
# symbols. Nautobot will not run without this defined. For more information, see
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-SECRET_KEY
SECRET_KEY = os.getenv(
    "NAUTOBOT_SECRET_KEY",
    "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
)

#####################################
#                                   #
#   Optional Django core settings   #
#                                   #
#####################################

# Enable custom logging. Please see the Django documentation for detailed guidance on configuring custom logs:
#   https://docs.djangoproject.com/en/stable/topics/logging/
#
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "normal": {
            "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s :\n  %(message)s",
            "datefmt": "%H:%M:%S",
        },
        "verbose": {
            "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-20s %(filename)-15s %(funcName)30s() :\n  %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "normal_console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "normal",
        },
        "verbose_console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["verbose_console"],
        "level": "DEBUG",
    },
}

###################################################################
#                                                                 #
#   Optional settings specific to Nautobot and its related apps   #
#                                                                 #
###################################################################


# SSO via Dex
def _read_cred(filename):
    try:
        with open(filename) as cred:
            return cred.read().strip()
    except FileNotFoundError:
        return None


SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = _read_cred("/opt/nautobot/sso/issuer") or os.getenv(
    "SOCIAL_AUTH_OIDC_OIDC_ENDPOINT"
)
SOCIAL_AUTH_OIDC_KEY = _read_cred("/opt/nautobot/sso/client-id") or "nautobot"
SOCIAL_AUTH_OIDC_SECRET = _read_cred("/opt/nautobot/sso/client-secret")
# The “openid”, “profile” and “email” are requested by default,
# below *adds* scope.
SOCIAL_AUTH_OIDC_SCOPE = ["groups"]

if SOCIAL_AUTH_OIDC_OIDC_ENDPOINT and SOCIAL_AUTH_OIDC_SECRET:
    AUTHENTICATION_BACKENDS = [
        "social_core.backends.open_id_connect.OpenIdConnectAuth",
        "nautobot.core.authentication.ObjectPermissionBackend",
    ]

# EXTERNAL_AUTH_DEFAULT_GROUPS = []
# EXTERNAL_AUTH_DEFAULT_PERMISSIONS = {}

# Directory where cloned Git repositories will be stored.
#
# GIT_ROOT = os.getenv("NAUTOBOT_GIT_ROOT", os.path.join(NAUTOBOT_ROOT, "git").rstrip("/"))

# Prefixes to use for custom fields, relationships, and computed fields in GraphQL representation of data.
#
# GRAPHQL_COMPUTED_FIELD_PREFIX = "cpf"
# GRAPHQL_CUSTOM_FIELD_PREFIX = "cf"
# GRAPHQL_RELATIONSHIP_PREFIX = "rel"

# Set to True to hide rather than disabling UI elements that a user doesn't have permission to access.
#
# HIDE_RESTRICTED_UI = False

# HTTP proxies Nautobot should use when sending outbound HTTP requests (e.g. for webhooks).
#
# HTTP_PROXIES = {
#     'http': 'http://10.10.1.10:3128',
#     'https': 'http://10.10.1.10:1080',
# }

# Directory where Jobs can be discovered.
#
# JOBS_ROOT = os.getenv("NAUTOBOT_JOBS_ROOT", os.path.join(NAUTOBOT_ROOT, "jobs").rstrip("/"))

# Log Nautobot deprecation warnings. Note that this setting is ignored (deprecation logs always enabled) if DEBUG = True
#
# LOG_DEPRECATION_WARNINGS = is_truthy(os.getenv("NAUTOBOT_LOG_DEPRECATION_WARNINGS", "False"))

# Setting this to True will display a "maintenance mode" banner at the top of every page.
#
# MAINTENANCE_MODE = is_truthy(os.getenv("NAUTOBOT_MAINTENANCE_MODE", "False"))

# Maximum number of objects that the UI and API will retrieve in a single request.
#
# MAX_PAGE_SIZE = 1000

# Expose Prometheus monitoring metrics at the HTTP endpoint '/metrics'
#
# METRICS_ENABLED = is_truthy(os.getenv("NAUTOBOT_METRICS_ENABLED", "False"))

# Credentials that Nautobot will uses to authenticate to devices when connecting via NAPALM.
#
NAPALM_USERNAME = os.environ.get("NAUTOBOT_NAPALM_USERNAME", "admin")
NAPALM_PASSWORD = os.environ.get("NAUTOBOT_NAPALM_PASSWORD", "admin")
NAPALM_TIMEOUT = int(os.environ.get("NAUTOBOT_NAPALM_TIMEOUT", "30"))

# NAPALM optional arguments (see https://napalm.readthedocs.io/en/latest/support/#optional-arguments). Arguments must
# be provided as a dictionary.
#
# NAPALM_ARGS = {}

# Default number of objects to display per page of the UI and REST API.
#
# PAGINATE_COUNT = 50

# Options given in the web UI for the number of objects to display per page.
#
# PER_PAGE_DEFAULTS = [25, 50, 100, 250, 500, 1000]

# Enable installed plugins. Add the name of each plugin to the list.
#
# PLUGINS = []
PLUGINS = [
    "nautobot_plugin_nornir",
    "nautobot_golden_config",
]

PLUGINS_CONFIG = {
    "nautobot_plugin_nornir": {
        "username": "admin",
        "password": "admin",
        "secret": "admin",
        "nornir_settings": {
            "credentials": "nautobot_plugin_nornir.plugins.credentials.nautobot_secrets.CredentialsNautobotSecrets",
            "username": "admin",
            "runner": {
                "plugin": "threaded",
                "options": {
                    "num_workers": 20,
                },
            },
        },
        "use_config_context": {
            "connection_options": True,
        },
        "connection_options": {
            "napalm": {
                "extras": {
                    "optional_args": {
                        "port": 41268,
                    },
                },
            },
        },
    },
    "nautobot_golden_config": {
        "per_feature_bar_width": 0.15,
        "per_feature_width": 13,
        "per_feature_height": 4,
        "enable_backup": True,
        "enable_compliance": True,
        "enable_intended": True,
        "enable_sotagg": True,
        "sot_agg_transposer": None,
        "enable_postprocessing": True,
        "postprocessing_callables": [],
        "postprocessing_subscribed": [],
        "platform_slug_map": None,
    },
    "dispatcher_mapping": {
        "default": "nornir_nautobot.plugins.tasks.dispatcher.default.NautobotNornirDriver",
        "default_netmiko": "nornir_nautobot.plugins.tasks.dispatcher.default.NetmikoNautobotNornirDriver",
        "cisco_asa": "nornir_nautobot.plugins.tasks.dispatcher.cisco_asa.NautobotNornirDriver",
        "cisco_nxos": "nornir_nautobot.plugins.tasks.dispatcher.cisco_nxos.NautobotNornirDriver",
        "cisco_ios": "nornir_nautobot.plugins.tasks.dispatcher.cisco_ios.NautobotNornirDriver",
        "cisco_xr": "nornir_nautobot.plugins.tasks.dispatcher.cisco_xr.NautobotNornirDriver",
        "juniper_junos": "nornir_nautobot.plugins.tasks.dispatcher.juniper_junos.NautobotNornirDriver",
        "arista_eos": "nornir_nautobot.plugins.tasks.dispatcher.arista_eos.NautobotNornirDriver",
    },
}
