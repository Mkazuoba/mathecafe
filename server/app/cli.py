"""Cria um administrador do painel. Uso (dentro de server/): python -m app.cli"""
import sys
import getpass

from app.database import init_db, SessionLocal
from app.models import Usuario
from app.security import hash_senha


def criar_admin():
    init_db()
    login = input("Login do administrador: ").strip()
    if not login:
        print("Login não pode ser vazio.")
        sys.exit(1)
    nome = input("Nome (Enter = Administrador): ").strip() or "Administrador"

    senha = getpass.getpass("Senha (mínimo 10 caracteres): ")
    if len(senha) < 10:
        print("Senha muito curta.")
        sys.exit(1)
    if senha != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.")
        sys.exit(1)

    db = SessionLocal()
    try:
        if db.query(Usuario).filter(Usuario.login == login).first():
            print(f"Já existe um usuário com login '{login}'.")
            sys.exit(1)
        db.add(Usuario(login=login, nome=nome, senha_hash=hash_senha(senha),
                       perfil="admin", ativo=True))
        db.commit()
    finally:
        db.close()
    print(f"Administrador '{login}' criado.")


if __name__ == "__main__":
    criar_admin()
