from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="./.env", env_file_encoding="utf-8")

    nautobot_token: str | None = None
    nautobot_url: str = "https://nautobot.dev.undercloud.rackspace.net"
    debug: bool = False
    os_cloud: str | None = None
    os_project: str = "default"
    os_client_config_file: str | None = None
    output_format: str = "table"


Settings.model_rebuild()
app_settings = Settings()
