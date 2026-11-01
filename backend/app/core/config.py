from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "VERIQO API"
    postgres_dsn: str = "postgresql+asyncpg://veriqo:veriqo@localhost:5432/veriqo"
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "veriqo"
    intelligence_url: str = "http://localhost:8001"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24
    # Used for per-day / per-hour grouping in the Year in Code analytics.
    display_timezone: str = "Asia/Kolkata"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Uploaded files (CVs, pitch decks) live in MongoDB GridFS under this bucket name.
    gridfs_bucket: str = "uploads"

    # Email via Python's smtplib. Gmail: smtp.gmail.com:587 with STARTTLS, smtp_user = the Gmail
    # address and smtp_password = a 16-character App Password (needs 2-Step Verification), never
    # the account password. If smtp_user is empty, emails are written to the log instead of sent.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "VERIQO"
    smtp_timeout_s: int = 20
    frontend_url: str = "http://localhost:5173"  # for links inside emails
    # Never send to these domains (the demo accounts' made-up addresses): bounces from
    # non-existent domains hurt the Gmail account's sending reputation.
    email_suppressed_domains: list[str] = ["demo.veriqo.dev", "example.com", "example.org"]

    # One-time passcodes (team invitations); stored only as HMAC-SHA256 with jwt_secret as the key.
    otp_ttl_minutes: int = 15
    otp_max_attempts: int = 5
    otp_resend_cooldown_s: int = 60
    otp_max_sends: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
