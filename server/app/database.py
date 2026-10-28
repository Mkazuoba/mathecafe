from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import get_settings
from app.models import Base, Usuario, GrupoEstacao, ConfiguracaoSistema
from app.security import hash_senha

settings = get_settings()

# Usa DATABASE_URL (PostgreSQL em producao, banco temporario nos testes).
# SQLite com caminho relativo resolve a partir de server/, independente de onde
# o uvicorn for iniciado. Usa forward slashes para compatibilidade no Windows.
_base_server = Path(__file__).resolve().parent.parent  # server/
_db_url = settings.DATABASE_URL
_eh_sqlite = _db_url.startswith("sqlite")
if _eh_sqlite and _db_url.startswith("sqlite:///") and not Path(_db_url[len("sqlite:///"):]).is_absolute():
    _db_url = f"sqlite:///{(_base_server / _db_url[len('sqlite:///'):]).resolve().as_posix()}"
print(f"Database: {_db_url if _eh_sqlite else _db_url.split('@')[-1]}")

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if _eh_sqlite else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _literal_sql(valor):
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def _migrar_colunas_faltantes():
    """Migracao leve: adiciona colunas novas sem apagar dados existentes."""
    if not _eh_sqlite:
        return
    with engine.connect() as conn:
        # Toda coluna do models.py que o banco ainda nao tem. O create_all so
        # cria tabelas novas; uma coluna esquecida aqui derrubava a rota inteira
        # (grupos_estacao.cor: GET /api/estacoes/ dava 500).
        for tabela in Base.metadata.sorted_tables:
            existentes = {c[1] for c in conn.execute(text(f"PRAGMA table_info({tabela.name})"))}
            if not existentes:
                continue
            for coluna in tabela.columns:
                if coluna.name in existentes:
                    continue
                ddl = f"ALTER TABLE {tabela.name} ADD COLUMN {coluna.name} {coluna.type.compile(dialect=engine.dialect)}"
                if coluna.default is not None and coluna.default.is_scalar:
                    # as linhas existentes tambem recebem o padrao
                    ddl += f" DEFAULT {_literal_sql(coluna.default.arg)}"
                conn.exec_driver_sql(ddl)
                conn.commit()
                print(f"Migracao: coluna '{coluna.name}' adicionada em {tabela.name}")

        # Indice para busca rapida de clientes por nome/login (42k+ registros)
        indices = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'")).fetchall()
        nomes_indices = {r[0] for r in indices}
        if "ix_usuarios_nome_login" not in nomes_indices:
            conn.execute(text("CREATE INDEX ix_usuarios_nome_login ON usuarios (perfil, nome, login)"))
            conn.commit()
            print("Migracao: indice ix_usuarios_nome_login criado em usuarios")

def init_db():
    Base.metadata.create_all(bind=engine)
    _migrar_colunas_faltantes()

    db = SessionLocal()
    try:
        tem_admin = db.query(Usuario).filter(Usuario.perfil == "admin").first() is not None
        if not tem_admin and settings.ADMIN_LOGIN and settings.ADMIN_SENHA:
            db.add(Usuario(
                login=settings.ADMIN_LOGIN, nome="Administrador",
                senha_hash=hash_senha(settings.ADMIN_SENHA),
                perfil="admin", ativo=True
            ))
            tem_admin = True

        if not db.query(GrupoEstacao).filter(GrupoEstacao.nome == "Padrao").first():
            db.add(GrupoEstacao(nome="Padrao", tempo_padrao_segundos=7200))

        configs_padrao = {
            "reiniciar_ao_encerrar": "false",
            "tempo_padrao_segundos": "7200",
        }
        for chave, valor in configs_padrao.items():
            if not db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == chave).first():
                db.add(ConfiguracaoSistema(chave=chave, valor=valor))

        db.commit()
        print("MatheCafe pronto.")
        if not tem_admin:
            print("Nenhum administrador cadastrado. Crie um com: python -m app.cli")
    except Exception as e:
        db.rollback()
        print(f"Erro ao inicializar banco: {e}")
    finally:
        db.close()
