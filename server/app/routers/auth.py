from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Usuario
from app.security import verificar_senha, criar_token, hash_senha, get_usuario_atual

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


class TrocarSenhaRequest(BaseModel):
    senha_atual: str
    nova_senha: str

@router.put("/trocar-senha")
def trocar_senha(req: TrocarSenhaRequest, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    
    usuario = db.query(Usuario).filter(Usuario.id == int(usuario["sub"])).first()
    if not usuario or not verificar_senha(req.senha_atual, usuario.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(req.nova_senha) < 4:
        raise HTTPException(status_code=400, detail="Nova senha muito curta (mínimo 4 caracteres)")
    usuario.senha_hash = hash_senha(req.nova_senha)
    db.commit()
    return {"ok": True}
