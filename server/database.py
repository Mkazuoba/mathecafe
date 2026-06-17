from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import get_settings
from models import Base, Usuario, GrupoEstacao, ConfiguracaoSistema
from auth import hash_senha

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _migrar_colunas_faltantes():
    """Migração leve: adiciona colunas novas sem apagar dados existentes."""
    if "sqlite" not in settings.DATABASE_URL:
        return
    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(apps_permitidos)")).fetchall()
        nomes = [c[1] for c in cols]
        if cols and "caminho" not in nomes:
            conn.execute(text("ALTER TABLE apps_permitidos ADD COLUMN caminho VARCHAR(500)"))
            conn.commit()
            print("✅ Migração: coluna 'caminho' adicionada em apps_permitidos")
        if cols and "imagem_url" not in nomes:
            conn.execute(text("ALTER TABLE apps_permitidos ADD COLUMN imagem_url VARCHAR(500)"))
            conn.commit()
            print("✅ Migração: coluna 'imagem_url' adicionada em apps_permitidos")

        cols_estacoes = conn.execute(text("PRAGMA table_info(estacoes)")).fetchall()
        nomes_estacoes = [c[1] for c in cols_estacoes]
        if cols_estacoes and "pos_x" not in nomes_estacoes:
            conn.execute(text("ALTER TABLE estacoes ADD COLUMN pos_x INTEGER DEFAULT 0"))
            conn.commit()
            print("✅ Migração: coluna 'pos_x' adicionada em estacoes")
        if cols_estacoes and "pos_y" not in nomes_estacoes:
            conn.execute(text("ALTER TABLE estacoes ADD COLUMN pos_y INTEGER DEFAULT 0"))
            conn.commit()
            print("✅ Migração: coluna 'pos_y' adicionada em estacoes")

def init_db():
    Base.metadata.create_all(bind=engine)
    _migrar_colunas_faltantes()

    db = SessionLocal()
    try:
        if not db.query(Usuario).filter(Usuario.login == "admin").first():
            db.add(Usuario(
                login="admin", nome="Administrador",
                senha_hash=hash_senha("admin123"),
                perfil="admin", ativo=True
            ))

        if not db.query(GrupoEstacao).filter(GrupoEstacao.nome == "Padrão").first():
            db.add(GrupoEstacao(nome="Padrão", tempo_padrao_segundos=7200))

        configs_padrao = {
            "reiniciar_ao_encerrar": "false",
            "tempo_padrao_segundos": "7200",
        }
        for chave, valor in configs_padrao.items():
            if not db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == chave).first():
                db.add(ConfiguracaoSistema(chave=chave, valor=valor))

        db.commit()
        print("✅ MatheCafé pronto. Admin: login=admin / senha=admin123")
    except Exception as e:
        db.rollback()
        print(f"Erro ao inicializar banco: {e}")
    finally:
        db.close()
