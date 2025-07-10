from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    admin_id: int
    supabase_url: str
    supabase_key: str

    model_config = SettingsConfigDict(env_file=".env")

# Создаем экземпляр конфига, который будет импортироваться в другие файлы
config = Settings()