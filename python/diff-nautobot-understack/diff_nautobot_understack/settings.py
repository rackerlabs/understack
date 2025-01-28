from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="./.env", env_file_encoding="utf-8")

    nautobot_api_token: Optional[str] = None
    nautobot_url: str = "https://nautobot.dev.undercloud.rackspace.net"
    debug: bool = False
    os_cloud: Optional[str] = None
    os_project: Optional[str] = "default"
    os_client_config_file: Optional[str] = None


Settings.model_rebuild()
app_settings = Settings()
