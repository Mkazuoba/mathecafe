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
    # Backup diario do SQLite (app/backup.py). Vazio: server/backups. Pode ser
    # outro disco ou pasta de rede (ex.: D:/BackupMatheCafe).
    BACKUP_PASTA: str = ""
    BACKUP_DIAS: int = 14

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


def pasta_de_backup(configurada: str) -> Path:
    """BACKUP_PASTA resolvida: vazia vira server/backups; relativa, a partir de server/."""
    base = Path(__file__).resolve().parent.parent
    pasta = Path(configurada.strip()) if (configurada or "").strip() else Path("backups")
    return pasta if pasta.is_absolute() else (base / pasta).resolve()


def normalizar_url_banco(url: str) -> str:
    """URL do banco no formato que o SQLAlchemy usa aqui.

    O Supabase e o Render dão postgres:// ou postgresql://; o driver instalado
    é o psycopg 3 (postgresql+psycopg://). Só SQLite e PostgreSQL são aceitos.
    """
    url = (url or "").strip()
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    if url.startswith(("postgresql+psycopg://", "sqlite:///")):
        return url
    raise ValueError("Use uma URL sqlite:///... ou postgresql://usuario:senha@servidor:5432/banco")


def descrever_banco(url: str) -> dict:
    """Tipo e destino do banco para mostrar no painel, sem a senha."""
    if url.startswith("sqlite"):
        return {"tipo": "SQLite", "destino": url[len("sqlite:///"):]}
    from sqlalchemy.engine import make_url
    u = make_url(url)
    destino = f"{u.host or ''}{f':{u.port}' if u.port else ''}/{u.database or ''}"
    if u.username:
        destino = f"{u.username}@{destino}"
    return {"tipo": "PostgreSQL", "destino": destino}


def gravar_no_env(arquivo: Path, chave: str, valor: str):
    """Troca (ou acrescenta) a linha CHAVE=valor do .env, sem mexer nas outras."""
    linhas = arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []
    nova = f"{chave}={valor}"
    for i, linha in enumerate(linhas):
        if linha.strip().startswith(f"{chave}="):
            linhas[i] = nova
            break
    else:
        linhas.append(nova)
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
