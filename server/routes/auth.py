from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Usuario
from auth import verificar_senha, criar_token

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    login: str
    senha: str

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(
        Usuario.login == req.login,
        Usuario.ativo == True
    ).first()

    if not usuario or not verificar_senha(req.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Login ou senha inválidos")

    if usuario.perfil == "cliente":
        raise HTTPException(status_code=403, detail="Clientes acessam pela estação")

    token = criar_token({
        "sub": str(usuario.id),
        "login": usuario.login,
        "nome": usuario.nome,
        "perfil": usuario.perfil
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "perfil": usuario.perfil,
        "nome": usuario.nome
    }
