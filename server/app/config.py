import secrets
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

# Resolve o .env relativo a este arquivo (server/.env),
# independente de onde o uvicorn for iniciado.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
# Chave gerada na primeira subida quando nenhuma foi configurada (fora do git)
_ARQUIVO_CHAVE = Path(__file__).resolve().parent.parent / ".secret_key"

# Valores de exemplo que ja estiveram no codigo ou no .env.example: quem os
# conhece forja um login de admin, entao o servidor nao sobe com eles.
CHAVES_DE_EXEMPLO = {"TROQUE_ESTA_CHAVE_EM_PRODUCAO", "troque_por_uma_chave_aleatoria_longa"}
TAMANHO_MINIMO_CHAVE = 32


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./cybercafe.db"
    # Vazio: usa server/.secret_key (gerada sozinha). Ver resolver_secret_key.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    # Opcional: cria este admin na inicialização se ainda não houver nenhum
    ADMIN_LOGIN: str = ""
    ADMIN_SENHA: str = ""

    class Config:
        env_file = str(_ENV_FILE)


def resolver_secret_key(configurada: str, arquivo: Path) -> str:
    """A chave que assina os logins.

    Configurada (variavel de ambiente ou .env): vale essa, se for forte.
    Sem configurar: le de `arquivo`, ou gera uma aleatoria e guarda la, para
    a proxima subida usar a mesma (senao todo mundo seria deslogado).
    """
    configurada = (configurada or "").strip()
    if configurada:
        if configurada in CHAVES_DE_EXEMPLO or len(configurada) < TAMANHO_MINIMO_CHAVE:
            raise RuntimeError(
                "SECRET_KEY fraca ou de exemplo. Apague a linha SECRET_KEY do .env "
                "(o servidor gera uma sozinho) ou use uma com 32+ caracteres: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"')
        return configurada
    if arquivo.exists():
        guardada = arquivo.read_text(encoding="utf-8").strip()
        if len(guardada) >= TAMANHO_MINIMO_CHAVE:
            return guardada
    nova = secrets.token_urlsafe(48)
    arquivo.write_text(nova, encoding="utf-8")
    print(f"SECRET_KEY: chave nova gerada em {arquivo} (guarde junto com o backup do banco)")
    return nova


@lru_cache()
def get_settings():
    s = Settings()
    s.SECRET_KEY = resolver_secret_key(s.SECRET_KEY, _ARQUIVO_CHAVE)
    return s
