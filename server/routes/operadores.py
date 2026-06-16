from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import Usuario
from auth import hash_senha, requer_perfil

router = APIRouter(prefix="/operadores", tags=["operadores"])

class OperadorCreate(BaseModel):
    login: str
    nome: str
    senha: str

class OperadorUpdate(BaseModel):
    nome: Optional[str] = None
    senha: Optional[str] = None
    ativo: Optional[bool] = None

def serializar(u: Usuario):
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "ativo": u.ativo,
        "criado_em": u.criado_em.isoformat() if u.criado_em else None,
    }

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operadores = db.query(Usuario).filter(Usuario.perfil == "operador").order_by(Usuario.nome).all()
    return [serializar(o) for o in operadores]

@router.post("/")
def criar(data: OperadorCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    if db.query(Usuario).filter(Usuario.login == data.login).first():
        raise HTTPException(status_code=400, detail="Login já existe")
    operador = Usuario(
        login=data.login, nome=data.nome,
        senha_hash=hash_senha(data.senha),
        perfil="operador"
    )
    db.add(operador)
    db.commit()
    db.refresh(operador)
    return serializar(operador)

@router.put("/{id}")
def atualizar(id: int, data: OperadorUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operador = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "operador").first()
    if not operador:
        raise HTTPException(status_code=404, detail="Operador não encontrado")
    if data.nome: operador.nome = data.nome
    if data.senha: operador.senha_hash = hash_senha(data.senha)
    if data.ativo is not None: operador.ativo = data.ativo
    db.commit()
    return serializar(operador)

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operador = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "operador").first()
    if not operador:
        raise HTTPException(status_code=404, detail="Operador não encontrado")
    db.delete(operador)
    db.commit()
    return {"ok": True}
