import os

from nautobot.core.settings import *  # noqa F401,F403

#########################
#                       #
#   Required settings   #
#                       #
#########################

# This is a list of valid fully-qualified domain names (FQDNs) for the Nautobot server. Nautobot will not permit write
# access to the server via any other hostnames. The first FQDN in the list will be treated as the preferred name.
#
# Example: ALLOWED_HOSTS = ['nautobot.example.com', 'nautobot.internal.local']
#
# ALLOWED_HOSTS = os.getenv("NAUTOBOT_ALLOWED_HOSTS", "").split(" ")

# The django-redis cache is used to establish concurrent locks using Redis.
#
# CACHES = {
#     "default": {
#         "BACKEND": os.getenv(
#             "NAUTOBOT_CACHES_BACKEND",
#             "django_prometheus.cache.backends.redis.RedisCache"
#             if METRICS_ENABLED else "django_redis.cache.RedisCache",
#         ),
#         "LOCATION": parse_redis_connection(redis_database=1),
#         "TIMEOUT": 300,
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#             "PASSWORD": "",
#         },
#     }
# }

# Number of seconds to cache ContentType lookups. Set to 0 to disable caching.
# CONTENT_TYPE_CACHE_TIMEOUT = int(os.getenv("NAUTOBOT_CONTENT_TYPE_CACHE_TIMEOUT", "0"))

# Celery broker URL used to tell workers where queues are located
#
# CELERY_BROKER_URL = os.getenv("NAUTOBOT_CELERY_BROKER_URL", parse_redis_connection(redis_database=0))

# Database configuration. See the Django documentation for a complete list of available parameters:
#   https://docs.djangoproject.com/en/stable/ref/settings/#databases
#
# DATABASES = {
#     "default": {
#         "NAME": os.getenv("NAUTOBOT_DB_NAME", "nautobot"),  # Database name
#         "USER": os.getenv("NAUTOBOT_DB_USER", ""),  # Database username
#         "PASSWORD": os.getenv("NAUTOBOT_DB_PASSWORD", ""),  # Database password
#         "HOST": os.getenv("NAUTOBOT_DB_HOST", "localhost"),  # Database server
#         "PORT": os.getenv("NAUTOBOT_DB_PORT", ""),  # Database port (leave blank for default)
#         "CONN_MAX_AGE": int(os.getenv("NAUTOBOT_DB_TIMEOUT", "300")),  # Database timeout
#         "ENGINE": os.getenv(
#             "NAUTOBOT_DB_ENGINE",
#             "django_prometheus.db.backends.postgresql" if METRICS_ENABLED else "django.db.backends.postgresql",
#         ),  # Database driver ("mysql" or "postgresql")
#     }
# }

# Ensure proper Unicode handling for MySQL
#
if DATABASES["default"]["ENGINE"].endswith("mysql"):  # noqa F405
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}  # noqa F405

# This key is used for secure generation of random numbers and strings. It must never be exposed outside of this file.
# For optimal security, SECRET_KEY should be at least 50 characters in length and contain a mix of letters, numbers, and
# symbols. Nautobot will not run without this defined. For more information, see
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-SECRET_KEY
SECRET_KEY = os.getenv("NAUTOBOT_SECRET_KEY", "celery-does-not-need-this")

#####################################
#                                   #
#   Optional Django core settings   #
#                                   #
#####################################

# Specify one or more name and email address tuples representing Nautobot administrators.
# These people will be notified of application errors (assuming correct email settings are provided).
#
# ADMINS = [
#     ['John Doe', 'jdoe@example.com'],
# ]

# FQDNs that are considered trusted origins for secure, cross-domain, requests such as HTTPS POST.
# If running Nautobot under a single domain, you may not need to set this variable;
# if running on multiple domains, you *may* need to set this variable to more or less the same as ALLOWED_HOSTS above.
# https://docs.djangoproject.com/en/stable/ref/settings/#csrf-trusted-origins
#
# CSRF_TRUSTED_ORIGINS = []

# Date/time formatting. See the following link for supported formats:
# https://docs.djangoproject.com/en/stable/ref/templates/builtins/#date
#
# DATE_FORMAT = os.getenv("NAUTOBOT_DATE_FORMAT", "N j, Y")
# SHORT_DATE_FORMAT = os.getenv("NAUTOBOT_SHORT_DATE_FORMAT", "Y-m-d")
# TIME_FORMAT = os.getenv("NAUTOBOT_TIME_FORMAT", "g:i a")
# SHORT_TIME_FORMAT = os.getenv("NAUTOBOT_SHORT_TIME_FORMAT", "H:i:s")
# DATETIME_FORMAT = os.getenv("NAUTOBOT_DATETIME_FORMAT", "N j, Y g:i a")
# SHORT_DATETIME_FORMAT = os.getenv("NAUTOBOT_SHORT_DATETIME_FORMAT", "Y-m-d H:i")

# Set to True to enable server debugging. WARNING: Debugging introduces a substantial performance penalty and may reveal
# sensitive information about your installation. Only enable debugging while performing testing. Never enable debugging
# on a production system.
#
# DEBUG = is_truthy(os.getenv("NAUTOBOT_DEBUG", "False"))

# If hosting Nautobot in a subdirectory, you must set this value to match the base URL prefix configured in your
# HTTP server (e.g. `/nautobot/`). When not set, URLs will default to being prefixed by `/`.
#
# FORCE_SCRIPT_NAME = None

# IP addresses recognized as internal to the system.
#
# INTERNAL_IPS = ("127.0.0.1", "::1")

# Enable custom logging. Please see the Django documentation for detailed guidance on configuring custom logs:
#   https://docs.djangoproject.com/en/stable/topics/logging/
#
# LOGGING = {
#     "version": 1,
#     "disable_existing_loggers": False,
#     "formatters": {
#         "normal": {
#             "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s :\n  %(message)s",
#             "datefmt": "%H:%M:%S",
#         },
#         "verbose": {
#             "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-20s "
#                       "%(filename)-15s %(funcName)30s() :\n  %(message)s",
#             "datefmt": "%H:%M:%S",
#         },
#     },
#     "handlers": {
#         "normal_console": {
#             "level": "INFO",
#             "class": "logging.StreamHandler",
#             "formatter": "normal",
#         },
#         "verbose_console": {
#             "level": "DEBUG",
#             "class": "logging.StreamHandler",
#             "formatter": "verbose",
#         },
#     },
#     "loggers": {
#         "django": {"handlers": ["normal_console"], "level": "INFO"},
#         "nautobot": {
#             "handlers": ["verbose_console" if DEBUG else "normal_console"],
#             "level": "DEBUG" if DEBUG else "INFO",
#         },
#     },
# }

# The file path where uploaded media such as image attachments are stored. A trailing slash is not needed.
#
# MEDIA_ROOT = os.path.join(NAUTOBOT_ROOT, "media").rstrip("/")

# Set to True to use session cookies instead of persistent cookies.
# Session cookies will expire when a browser is closed.
#
# SESSION_EXPIRE_AT_BROWSER_CLOSE = is_truthy(os.getenv("NAUTOBOT_SESSION_EXPIRE_AT_BROWSER_CLOSE", "False"))

# The length of time (in seconds) for which a user will remain logged into the web UI before being prompted to
# re-authenticate. (Default: 1209600 [14 days])
#
# SESSION_COOKIE_AGE = int(os.getenv("NAUTOBOT_SESSION_COOKIE_AGE", "1209600"))  # 2 weeks, in seconds

# Where Nautobot stores user session data.
#
# SESSION_ENGINE = "django.contrib.sessions.backends.db"

# By default, Nautobot will store session data in the database. Alternatively, a file path can be specified here to use
# local file storage instead. (This can be useful for enabling authentication on a standby instance with read-only
# database access.) Note that the user as which Nautobot runs must have read and write permissions to this path.
#
# SESSION_FILE_PATH = os.getenv("NAUTOBOT_SESSION_FILE_PATH", None)

# Where static files (CSS, JavaScript, etc.) are stored
#
# STATIC_ROOT = os.path.join(NAUTOBOT_ROOT, "static")

# Time zone (default: UTC)
#
# TIME_ZONE = os.getenv("NAUTOBOT_TIME_ZONE", "UTC")

###################################################################
#                                                                 #
#   Optional settings specific to Nautobot and its related apps   #
#                                                                 #
###################################################################

# URL schemes that are allowed within links in Nautobot
#
# ALLOWED_URL_SCHEMES = (
#     "file",
#     "ftp",
#     "ftps",
#     "http",
#     "https",
#     "irc",
#     "mailto",
#     "sftp",
#     "ssh",
#     "tel",
#     "telnet",
#     "tftp",
#     "vnc",
#     "xmpp",
# )

# Banners (HTML is permitted) to display at the top and/or bottom of all Nautobot pages, and on the login page itself.
#
# BANNER_BOTTOM = ""
# BANNER_LOGIN = ""
# BANNER_TOP = ""

# Branding logo locations. The logo takes the place of the Nautobot logo in the top right of the nav bar.
# The filepath should be relative to the `MEDIA_ROOT`.
#
# BRANDING_FILEPATHS = {
#     "logo": os.getenv("NAUTOBOT_BRANDING_FILEPATHS_LOGO", None),  # Navbar logo
#     "favicon": os.getenv("NAUTOBOT_BRANDING_FILEPATHS_FAVICON", None),  # Browser favicon
#     "icon_16": os.getenv("NAUTOBOT_BRANDING_FILEPATHS_ICON_16", None),  # 16x16px icon
#     "icon_32": os.getenv("NAUTOBOT_BRANDING_FILEPATHS_ICON_32", None),  # 32x32px icon
#     "icon_180": os.getenv(
#         "NAUTOBOT_BRANDING_FILEPATHS_ICON_180", None
#     ),  # 180x180px icon - used for the apple-touch-icon header
#     "icon_192": os.getenv("NAUTOBOT_BRANDING_FILEPATHS_ICON_192", None),  # 192x192px icon
#     "icon_mask": os.getenv(
#         "NAUTOBOT_BRANDING_FILEPATHS_ICON_MASK", None
#     ),  # mono-chrome icon used for the mask-icon header
#     "header_bullet": os.getenv(
#         "NAUTOBOT_BRANDING_FILEPATHS_HEADER_BULLET", None
#     ),  # bullet image used for various view headers
#     "nav_bullet": os.getenv("NAUTOBOT_BRANDING_FILEPATHS_NAV_BULLET", None),  # bullet image used for nav menu headers
# }

# Prepended to CSV, YAML and export template filenames (i.e. `nautobot_device.yml`)
#
# BRANDING_PREPENDED_FILENAME = os.getenv("NAUTOBOT_BRANDING_PREPENDED_FILENAME", "nautobot_")

# Title to use in place of "Nautobot"
#
# BRANDING_TITLE = os.getenv("NAUTOBOT_BRANDING_TITLE", "Nautobot")

# Branding URLs (links in the bottom right of the footer)
#
# BRANDING_URLS = {
#     "code": os.getenv("NAUTOBOT_BRANDING_URLS_CODE", "https://github.com/nautobot/nautobot"),
#     "docs": os.getenv("NAUTOBOT_BRANDING_URLS_DOCS", None),
#     "help": os.getenv("NAUTOBOT_BRANDING_URLS_HELP", "https://github.com/nautobot/nautobot/wiki"),
# }

# Options to pass to the Celery broker transport, for example when using Celery with Redis Sentinel.
#
# CELERY_BROKER_TRANSPORT_OPTIONS = {}

# Default celery queue name that will be used by workers and tasks if no queue is specified
