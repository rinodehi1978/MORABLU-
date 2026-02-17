from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/customer_support.db"
    anthropic_api_key: str = ""

    # Amazon SP API accounts
    amazon_morablu_refresh_token: str = ""
    amazon_morablu_lwa_app_id: str = ""
    amazon_morablu_lwa_client_secret: str = ""

    amazon_2ndmorablu_refresh_token: str = ""
    amazon_2ndmorablu_lwa_app_id: str = ""
    amazon_2ndmorablu_lwa_client_secret: str = ""

    amazon_cha3_refresh_token: str = ""
    amazon_cha3_lwa_app_id: str = ""
    amazon_cha3_lwa_client_secret: str = ""

    amazon_marketplace_id: str = "A1VC38T7YXB528"
    amazon_region: str = "FE"

    # Gmail IMAP
    gmail_morablu_address: str = ""
    gmail_morablu_app_password: str = ""
    gmail_2ndmorablu_address: str = ""
    gmail_2ndmorablu_app_password: str = ""
    gmail_cha3_address: str = ""
    gmail_cha3_app_password: str = ""

    fetch_interval_minutes: int = 5

    # Dashboard authentication
    dashboard_password: str = "changeme"
    session_secret: str = "auto-generated-secret-change-in-production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
