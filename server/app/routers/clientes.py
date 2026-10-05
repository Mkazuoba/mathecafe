from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, time as dt_time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from app.database import get_db
from app.models import Usuario, Sessao
from app.security import hash_senha, requer_perfil

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
    saldo_segundos: Optional[int] = None

def _uso_hoje(db: Session, cliente_id: int) -> int:
    """Retorna segundos consumidos hoje (fuso Brasil UTC-3) em sessoes encerradas."""
    tz_br = ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(tz=tz_br).date()
    inicio_hoje_utc = (
        datetime.combine(hoje_br, dt_time.min)
        .replace(tzinfo=tz_br)
        .astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
    )
    total = db.query(func.sum(Sessao.tempo_consumido_segundos)).filter(
        Sessao.cliente_id == cliente_id,
        Sessao.iniciada_em >= inicio_hoje_utc,
        Sessao.encerrada_em != None
    ).scalar() or 0
    return int(total)


def serializar(u: Usuario, db: Session = None):
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "ativo": u.ativo,
        "saldo_segundos": u.saldo_segundos,
        "observacao": u.observacao,
        "criado_em": u.criado_em.isoformat() if u.criado_em else None,
        "na_fila": u.autorizacao is not None and not u.autorizacao.usado,
        "uso_hoje_segundos": _uso_hoje(db, u.id) if db is not None else 0,
    }

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    clientes = db.query(Usuario).filter(Usuario.perfil == "cliente").order_by(Usuario.nome).all()
    return [serializar(c, db) for c in clientes]

@router.post("/")
def criar(data: ClienteCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
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
    return serializar(cliente, db)

@router.put("/{id}")
def atualizar(id: int, data: ClienteUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if data.nome: cliente.nome = data.nome
    if data.senha: cliente.senha_hash = hash_senha(data.senha)
    if data.ativo is not None: cliente.ativo = data.ativo
    if data.observacao is not None: cliente.observacao = data.observacao
    if data.saldo_segundos is not None: cliente.saldo_segundos = data.saldo_segundos
    db.commit()
    return serializar(cliente, db)

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Quem já usou os computadores fica no histórico de sessões (e nos relatórios)
    if db.query(Sessao).filter(Sessao.cliente_id == id).first():
        raise HTTPException(status_code=409,
                            detail="Cliente tem histórico de uso. Desative-o em vez de excluir.")
    if cliente.autorizacao:
        db.delete(cliente.autorizacao)
    db.delete(cliente)
    db.commit()
    return {"ok": True}

@router.get("/{id}")
def obter(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return serializar(cliente, db)
