"""Cria um administrador do painel. Uso (dentro de server/):

    python -m app.cli                       pergunta login, nome e senha
    python -m app.cli --login X --nome Y    sem perguntar (instalador do servidor):
                                            a senha vem de MATHECAFE_SENHA_ADMIN,
                                            nunca da linha de comando. Se o login
                                            ja existe, troca a senha e o torna admin.
"""
import argparse
import getpass
import os
import sys

from app.database import init_db, SessionLocal
from app.models import Usuario
from app.security import hash_senha

SENHA_MINIMA = 10


def gravar_admin(login: str, nome: str, senha: str, trocar_se_existe: bool) -> str:
    """Cria (ou, com trocar_se_existe, atualiza) o admin. Devolve a mensagem;
    levanta ValueError com o motivo se nao der."""
    login = (login or "").strip()
    if not login:
        raise ValueError("Login não pode ser vazio.")
    if len(senha or "") < SENHA_MINIMA:
        raise ValueError(f"Senha muito curta (mínimo {SENHA_MINIMA} caracteres).")
    init_db()
    db = SessionLocal()
    try:
        existente = db.query(Usuario).filter(Usuario.login == login).first()
        if existente and not trocar_se_existe:
            raise ValueError(f"Já existe um usuário com login '{login}'.")
        if existente:
            existente.senha_hash = hash_senha(senha)
            existente.perfil, existente.ativo = "admin", True
            existente.nome = nome or existente.nome
            msg = f"Administrador '{login}' atualizado."
        else:
            db.add(Usuario(login=login, nome=nome or "Administrador", senha_hash=hash_senha(senha),
                           perfil="admin", ativo=True))
            msg = f"Administrador '{login}' criado."
        db.commit()
        return msg
    finally:
        db.close()


def criar_admin() -> int:
    """Modo interativo (terminal)."""
    login = input("Login do administrador: ").strip()
    nome = input("Nome (Enter = Administrador): ").strip() or "Administrador"
    senha = getpass.getpass(f"Senha (mínimo {SENHA_MINIMA} caracteres): ")
    if senha != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.")
        return 1
    try:
        print(gravar_admin(login, nome, senha, trocar_se_existe=False))
    except ValueError as e:
        print(e)
        return 1
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cria um administrador do painel")
    p.add_argument("--login")
    p.add_argument("--nome", default="Administrador")
    args = p.parse_args(argv)
    if not args.login:
        return criar_admin()
    try:
        print(gravar_admin(args.login, args.nome, os.environ.get("MATHECAFE_SENHA_ADMIN", ""),
                           trocar_se_existe=True))
    except ValueError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
