from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str

    retry_max_attempts: int = 3
    retry_wait_multiplier: float = 1.0
    retry_wait_min: float = 1.0
    retry_wait_max: float = 10.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
