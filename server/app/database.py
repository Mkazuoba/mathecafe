from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import get_settings
from app.models import Base, Usuario, GrupoEstacao, ConfiguracaoSistema
from app.security import hash_senha

settings = get_settings()

# Resolve o caminho do banco sempre relativo a server/, independente de onde
# o uvicorn for iniciado. Usa forward slashes para compatibilidade no Windows.
_base_server = Path(__file__).resolve().parent.parent  # server/
_db_path = (_base_server / "cybercafe.db").resolve()
_db_url = f"sqlite:///{_db_path.as_posix()}"
print(f"Database: {_db_path}")

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _migrar_colunas_faltantes():
    """Migracao leve: adiciona colunas novas sem apagar dados existentes."""
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(apps_permitidos)")).fetchall()
        nomes = [c[1] for c in cols]
        if cols and "caminho" not in nomes:
            conn.execute(text("ALTER TABLE apps_permitidos ADD COLUMN caminho VARCHAR(500)"))
            conn.commit()
            print("Migracao: coluna 'caminho' adicionada em apps_permitidos")
        if cols and "imagem_url" not in nomes:
            conn.execute(text("ALTER TABLE apps_permitidos ADD COLUMN imagem_url VARCHAR(500)"))
            conn.commit()
            print("Migracao: coluna 'imagem_url' adicionada em apps_permitidos")

        cols_estacoes = conn.execute(text("PRAGMA table_info(estacoes)")).fetchall()
        nomes_estacoes = [c[1] for c in cols_estacoes]
        if cols_estacoes and "pos_x" not in nomes_estacoes:
            conn.execute(text("ALTER TABLE estacoes ADD COLUMN pos_x INTEGER DEFAULT 0"))
            conn.commit()
            print("Migracao: coluna 'pos_x' adicionada em estacoes")
        if cols_estacoes and "pos_y" not in nomes_estacoes:
            conn.execute(text("ALTER TABLE estacoes ADD COLUMN pos_y INTEGER DEFAULT 0"))
            conn.commit()
            print("Migracao: coluna 'pos_y' adicionada em estacoes")

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
