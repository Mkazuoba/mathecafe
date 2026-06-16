from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db
from models import Estacao, GrupoEstacao, Autorizacao, Usuario
from auth import requer_perfil
from websocket_manager import manager

router = APIRouter(prefix="/estacoes", tags=["estacoes"])

class EstacaoUpdate(BaseModel):
    nome: Optional[str] = None
    grupo_id: Optional[int] = None
    ativa: Optional[bool] = None
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None

class PosicaoUpdate(BaseModel):
    pos_x: int
    pos_y: int

def serial_estacao(e: Estacao):
    online = e.nome in manager.estacoes_online()
    return {
        "id": e.id,
        "nome": e.nome,
        "grupo_id": e.grupo_id,
        "grupo_nome": e.grupo.nome if e.grupo else None,
        "status": e.status if online else "desligada",
        "online": online,
        "ip": e.ip,
        "ultimo_ping": e.ultimo_ping.isoformat() if e.ultimo_ping else None,
        "pos_x": e.pos_x,
        "pos_y": e.pos_y,
    }

def serial_autorizacao(a: Autorizacao):
    return {
        "id": a.id,
        "cliente_id": a.cliente_id,
        "cliente_login": a.cliente.login,
        "cliente_nome": a.cliente.nome,
        "saldo_segundos": a.cliente.saldo_segundos,
        "autorizado_em": a.autorizado_em.isoformat(),
        "autorizado_por": a.autorizado_por.nome,
    }

# ── Grupos ────────────────────────────────────────────────────────────────────
@router.get("/grupos")
def listar_grupos(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [{"id": g.id, "nome": g.nome, "tempo_padrao_segundos": g.tempo_padrao_segundos}
            for g in db.query(GrupoEstacao).filter(GrupoEstacao.ativo == True).all()]

@router.post("/grupos")
def criar_grupo(nome: str, tempo_padrao_segundos: int = 7200,
                db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    g = GrupoEstacao(nome=nome, tempo_padrao_segundos=tempo_padrao_segundos)
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, "nome": g.nome, "tempo_padrao_segundos": g.tempo_padrao_segundos}

# ── Estações ──────────────────────────────────────────────────────────────────
@router.get("/")
def listar(grupo_id: Optional[int] = None, db: Session = Depends(get_db),
           _=Depends(requer_perfil("admin", "operador"))):
    q = db.query(Estacao).filter(Estacao.ativa == True)
    if grupo_id:
        q = q.filter(Estacao.grupo_id == grupo_id)
    return [serial_estacao(e) for e in q.order_by(Estacao.nome).all()]

@router.post("/")
def criar(nome: str, grupo_id: Optional[int] = None,
          db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    if db.query(Estacao).filter(Estacao.nome == nome).first():
        raise HTTPException(400, "Estação já existe")
    e = Estacao(nome=nome, grupo_id=grupo_id)
    db.add(e); db.commit(); db.refresh(e)
    return serial_estacao(e)

@router.put("/{id}")
def atualizar(id: int, data: EstacaoUpdate, db: Session = Depends(get_db),
              _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if data.nome: e.nome = data.nome
    if data.grupo_id is not None: e.grupo_id = data.grupo_id
    if data.ativa is not None: e.ativa = data.ativa
    if data.pos_x is not None: e.pos_x = data.pos_x
    if data.pos_y is not None: e.pos_y = data.pos_y
    db.commit()
    return serial_estacao(e)

@router.put("/{id}/posicao")
def atualizar_posicao(id: int, data: PosicaoUpdate, db: Session = Depends(get_db),
                       _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    e.pos_x = data.pos_x
    e.pos_y = data.pos_y
    db.commit()
    return serial_estacao(e)

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    db.delete(e); db.commit()
    return {"ok": True}

# ── Fila de espera ────────────────────────────────────────────────────────────
@router.get("/fila")
def ver_fila(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    fila = db.query(Autorizacao).filter(Autorizacao.usado == False)\
             .order_by(Autorizacao.autorizado_em).all()
    return [serial_autorizacao(a) for a in fila]

@router.post("/fila/{cliente_id}")
async def autorizar_cliente(cliente_id: int, db: Session = Depends(get_db),
                             operador=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(
        Usuario.id == cliente_id, Usuario.perfil == "cliente", Usuario.ativo == True).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    auth = db.query(Autorizacao).filter(Autorizacao.cliente_id == cliente_id).first()

    if auth and not auth.usado:
        raise HTTPException(400, "Cliente já está na fila")

    if auth:
        auth.usado = False
        auth.autorizado_por_id = int(operador["sub"])
        auth.autorizado_em = datetime.utcnow()
    else:
        auth = Autorizacao(
            cliente_id=cliente_id,
            autorizado_por_id=int(operador["sub"])
        )
        db.add(auth)

    db.commit()
    db.refresh(auth)

    await manager.broadcast_paineis("fila_atualizada", {
        "acao": "adicionado", "cliente": serial_autorizacao(auth)
    })
    return serial_autorizacao(auth)

@router.delete("/fila/{cliente_id}")
async def remover_fila(cliente_id: int, db: Session = Depends(get_db),
                        _=Depends(requer_perfil("admin", "operador"))):
    auth = db.query(Autorizacao).filter(
        Autorizacao.cliente_id == cliente_id, Autorizacao.usado == False).first()
    if not auth:
        raise HTTPException(404, "Cliente não está na fila")
    db.delete(auth); db.commit()
    await manager.broadcast_paineis("fila_atualizada", {"acao": "removido", "cliente_id": cliente_id})
    return {"ok": True}
