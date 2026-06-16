from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import Usuario
from auth import hash_senha, requer_perfil

router = APIRouter(prefix="/clientes", tags=["clientes"])

class ClienteCreate(BaseModel):
    login: str
    nome: str
    senha: str
    observacao: Optional[str] = None

class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    senha: Optional[str] = None
    ativo: Optional[bool] = None
    observacao: Optional[str] = None

def serializar(u: Usuario):
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "ativo": u.ativo,
        "saldo_segundos": u.saldo_segundos,
        "observacao": u.observacao,
        "criado_em": u.criado_em.isoformat() if u.criado_em else None,
        "na_fila": u.autorizacao is not None and not u.autorizacao.usado
    }

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    clientes = db.query(Usuario).filter(Usuario.perfil == "cliente").order_by(Usuario.nome).all()
    return [serializar(c) for c in clientes]

@router.post("/")
def criar(data: ClienteCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    if db.query(Usuario).filter(Usuario.login == data.login).first():
        raise HTTPException(status_code=400, detail="Login já existe")
    cliente = Usuario(
        login=data.login, nome=data.nome,
        senha_hash=hash_senha(data.senha),
        perfil="cliente", observacao=data.observacao
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return serializar(cliente)

@router.put("/{id}")
def atualizar(id: int, data: ClienteUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if data.nome: cliente.nome = data.nome
    if data.senha: cliente.senha_hash = hash_senha(data.senha)
    if data.ativo is not None: cliente.ativo = data.ativo
    if data.observacao is not None: cliente.observacao = data.observacao
    db.commit()
    return serializar(cliente)

@router.get("/{id}")
def obter(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return serializar(cliente)
