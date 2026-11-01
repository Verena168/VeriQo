from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]  # backend/intelligence


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Optional: raises the GitHub API limit from 60 to 5,000 requests/hour.
    github_token: str | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Whitebook Algorithm 1 used 0.8, but all-MiniLM-L6-v2 scores bare skill names lower: measured
    # React/React Native 0.74, ML/Deep Learning 0.69, Blockchain/Ethereum 0.69, Python/Java 0.45.
    # 0.8 would never fire, so 0.65 is the default (see docs/ML_MODELS.md).
    semantic_threshold: float = 0.65
    models_dir: Path = SERVICE_ROOT / "models"
    clone_timeout_s: int = 180
    max_repo_files: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()
