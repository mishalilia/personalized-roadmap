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
    llm_api_key_openai: SecretStr | None = None
    config_dir: Path = Path("config")
    data_dir: Path = Path("data")
    # Reviewed checkpoint questions: checkpoints/<curriculum version>/<module id>.yaml.
    checkpoints_dir: Path = Path("checkpoints")
    # Progress that learners chose to share (roadmap.events); data/events.sqlite unless set.
    api_events_file: Path | None = None

    @property
    def llm_api_keys(self) -> dict[str, SecretStr]:
        """Keys by provider name, for the providers that have one."""
        keys = {
            "groq": self.llm_api_key_groq,
            "google": self.llm_api_key_google,
            "openai": self.llm_api_key_openai,
        }
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
    def events_file(self) -> Path:
        return self.api_events_file or self.data_dir / "events.sqlite"

    @property
    def curricula_dir(self) -> Path:
        """One shared clone of the curriculum and a checkout per version."""
        return self.data_dir / "curricula"


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
