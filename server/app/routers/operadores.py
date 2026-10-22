from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models import Usuario, Autorizacao
from app.security import hash_senha, requer_perfil

router = APIRouter(prefix="/operadores", tags=["operadores"])

class OperadorCreate(BaseModel):
    login: str
    nome: str
    senha: str
    perfil: Optional[str] = "operador"

class OperadorUpdate(BaseModel):
    nome: Optional[str] = None
    senha: Optional[str] = None
    ativo: Optional[bool] = None
    perfil: Optional[str] = None

def serializar(u: Usuario):
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "ativo": u.ativo,
        "perfil": u.perfil,
        "criado_em": u.criado_em.isoformat() if u.criado_em else None,
    }

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operadores = db.query(Usuario).filter(
        Usuario.perfil.in_(["operador", "admin"])
    ).order_by(Usuario.perfil, Usuario.nome).all()
    return [serializar(o) for o in operadores]

@router.post("/")
def criar(data: OperadorCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    if db.query(Usuario).filter(Usuario.login == data.login).first():
        raise HTTPException(status_code=400, detail="Login ja existe")
    perfil_val = data.perfil if data.perfil in ("admin", "operador") else "operador"
    operador = Usuario(
        login=data.login, nome=data.nome,
        senha_hash=hash_senha(data.senha),
        perfil=perfil_val
    )
    db.add(operador)
    db.commit()
    db.refresh(operador)
    return serializar(operador)

@router.put("/{id}")
def atualizar(id: int, data: OperadorUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operador = db.query(Usuario).filter(Usuario.id == id).first()
    if not operador:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    if data.nome: operador.nome = data.nome
    if data.senha: operador.senha_hash = hash_senha(data.senha)
    if data.ativo is not None: operador.ativo = data.ativo
    if data.perfil in ("admin", "operador"): operador.perfil = data.perfil
    db.commit()
    return serializar(operador)

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operador = db.query(Usuario).filter(Usuario.id == id).first()
    if not operador:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    # A fila guarda quem liberou cada cliente
    if db.query(Autorizacao).filter(Autorizacao.autorizado_por_id == id).first():
        raise HTTPException(status_code=409,
                            detail="Operador ja liberou clientes. Desative-o em vez de excluir.")
    db.delete(operador)
    db.commit()
    return {"ok": True}
