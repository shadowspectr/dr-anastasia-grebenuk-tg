from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    admin_id: int
    supabase_url: str
    supabase_key: str

    # Новые поля
    web_server_url: str
    webhook_path: str

    model_config = SettingsConfigDict(env_file=".env")


config = Settings()