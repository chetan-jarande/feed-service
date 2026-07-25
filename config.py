from functools import lru_cache
from typing import Any
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Azure DevOps Artifacts and PyPI integration.

    All settings can be overridden via environment variables or a `.env` file.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    azure_org: str = ""
    azure_project: str = ""
    azure_project_name: str = ""
    azure_feed_name: str = ""
    azure_devops_ui_base: str = ""
    azure_api_version: str = "7.1-preview.1"
    azure_pat: str = ""

    pypi_json_base: str = "https://pypi.org/pypi"
    pypi_project_base: str = "https://pypi.org/project"

    default_python_tag: str = "cp312"
    default_download_dir: str = "./wheels"
    request_timeout: int = 60
    upload_timeout: int = 600

    def model_post_init(self, context: Any) -> None:
        """Constructs default UI base URL if not explicitly configured."""
        if not self.azure_devops_ui_base and self.azure_org:
            project_identifier = self.azure_project_name or self.azure_project
            if project_identifier:
                self.azure_devops_ui_base = f"https://{self.azure_org}.visualstudio.com/{quote(project_identifier)}"

    @property
    def feeds_api_base(self) -> str:
        """Returns base URL for Azure DevOps Packaging REST API."""
        return f"https://feeds.dev.azure.com/{self.azure_org}/{self.azure_project}/_apis/packaging/Feeds"

    def upload_url(self, feed_name: str | None = None) -> str:
        """Returns Twine repository upload URL for target feed."""
        feed = feed_name or self.azure_feed_name
        return f"https://pkgs.dev.azure.com/{self.azure_org}/{self.azure_project}/_packaging/{feed}/pypi/upload/"

    def simple_index_url(self, feed_name: str | None = None) -> str:
        """Returns PEP 503 Simple Index URL for target feed."""
        feed = feed_name or self.azure_feed_name
        return f"https://pkgs.dev.azure.com/{self.azure_org}/{self.azure_project}/_packaging/{feed}/pypi/simple/"


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings instance."""
    return Settings()
