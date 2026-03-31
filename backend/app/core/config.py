from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SellerCash API"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg2://sellercash:sellercash@postgres:5432/sellercash"

    opensearch_url: str = "http://opensearch:9200"
    opensearch_index: str = "sellercash_docs"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "sellercash-docs"
    minio_secure: bool = False

    auth_enabled: bool = False
    keycloak_server_url: str = "http://keycloak:8080"
    keycloak_realm: str = "sellercash"
    keycloak_frontend_client_id: str = "sellercash-web"
    keycloak_issuer: str | None = None
    keycloak_audience: str | None = None
    keycloak_verify_aud: bool = False

    default_horizon_days: int = 60
    history_days_for_forecast: int = 90
    min_sales_observations: int = 7


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
