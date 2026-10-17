from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    postgres_user: str = "compass"
    postgres_password: str = "compass"
    postgres_db: str = "compass"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    timezone: str = "Europe/Berlin"
    log_level: str = "INFO"

    # MCP server and its built-in OAuth server. The public URL is what Claude connects to;
    # the MCP endpoint is <public url>/mcp.
    mcp_public_url: str = "http://localhost:8001"
    mcp_access_token_ttl: int = 3600
    mcp_refresh_token_ttl: int = 60 * 60 * 24 * 30
    mcp_write_limit_per_hour: int = 120

    # The owner login, shared with the Caddy basic auth in front of the web app.
    compass_basic_auth_user: str = ""
    compass_basic_auth_hash: str = ""

    @property
    def owner_password_hash(self) -> str:
        # In .env every $ of the bcrypt hash is written as $$ for Docker Compose.
        return self.compass_basic_auth_hash.replace("$$", "$")

    @property
    def mcp_resource_url(self) -> str:
        return self.mcp_public_url.rstrip("/") + "/mcp"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
