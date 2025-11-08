"""Configuration helpers for ADOIF."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

DEFAULT_LIBRARY_ROOT = Path.home() / "adoif-library"


class Settings(BaseModel):
    """Runtime configuration loaded from env vars with sensible defaults."""

    data_dir: Path = Field(default_factory=lambda: DEFAULT_LIBRARY_ROOT)
    db_filename: str = "library.sqlite3"
    log_level: str = "INFO"
    crossref_base_url: str = "https://api.crossref.org/works"
    unpaywall_base_url: str = "https://api.unpaywall.org/v2"
    unpaywall_email: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    def ensure_directories(self) -> None:
        """Create data directories if they are missing."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        data_dir = Path(os.environ.get("ADOIF_DATA_DIR", DEFAULT_LIBRARY_ROOT))
        return cls(
            data_dir=data_dir,
            db_filename=os.environ.get("ADOIF_DB_FILENAME", "library.sqlite3"),
            log_level=os.environ.get("ADOIF_LOG_LEVEL", "INFO"),
            crossref_base_url=os.environ.get(
                "ADOIF_CROSSREF_URL", "https://api.crossref.org/works"
            ),
            unpaywall_base_url=os.environ.get(
                "ADOIF_UNPAYWALL_URL", "https://api.unpaywall.org/v2"
            ),
            unpaywall_email=os.environ.get("ADOIF_UNPAYWALL_EMAIL"),
        )


def get_settings() -> Settings:
    """Convenience accessor for lazy modules."""
    settings = Settings.load()
    settings.ensure_directories()
    return settings
