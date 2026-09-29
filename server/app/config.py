from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./cybercafe.db"
    SECRET_KEY: str = "TROQUE_ESTA_CHAVE_EM_PRODUCAO"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    # Opcional: cria este admin na inicialização se ainda não houver nenhum
    ADMIN_LOGIN: str = ""
    ADMIN_SENHA: str = ""

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
