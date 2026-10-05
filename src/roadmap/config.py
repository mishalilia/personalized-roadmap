"""Settings from the environment or a local `.env`, and the YAML files in `config/`."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    llm_provider: str | None = None  # a provider from config/llm.yaml
    llm_api_key_groq: SecretStr | None = None
    llm_api_key_google: SecretStr | None = None
    config_dir: Path = Path("config")
    data_dir: Path = Path("data")
    output_dir: Path = Path("out")  # where saved paths are looked for; git-ignored

    @property
    def llm_api_keys(self) -> dict[str, SecretStr]:
        """Keys by provider name, for the providers that have one."""
        keys = {"groq": self.llm_api_key_groq, "google": self.llm_api_key_google}
        return {provider: key for provider, key in keys.items() if key is not None}

    @property
    def llm_file(self) -> Path:
        return self.config_dir / "llm.yaml"

    @property
    def curriculum_file(self) -> Path:
        return self.config_dir / "curriculum.yaml"

    @property
    def questions_file(self) -> Path:
        return self.config_dir / "onboarding.yaml"

    @property
    def profiles_file(self) -> Path:
        return self.config_dir / "profiles.yaml"

    @property
    def curriculum_checkout(self) -> Path:
        return self.data_dir / "curriculum"


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
