from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from database import get_db
from models import Sessao, Estacao
from auth import requer_perfil
from websocket_manager import manager

router = APIRouter(prefix="/sessoes", tags=["sessoes"])

def serial_sessao(s: Sessao):
    return {
        "id": s.id,
        "cliente_id": s.cliente_id,
        "cliente_login": s.cliente.login,
        "cliente_nome": s.cliente.nome,
        "estacao_nome": s.estacao.nome,
        "iniciada_em": s.iniciada_em.isoformat(),
        "encerrada_em": s.encerrada_em.isoformat() if s.encerrada_em else None,
        "tempo_total_segundos": s.tempo_total_segundos,
        "tempo_consumido_segundos": s.tempo_consumido_segundos,
        "motivo_encerramento": s.motivo_encerramento,
        "ativa": s.encerrada_em is None
    }

@router.get("/ativas")
def sessoes_ativas(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [serial_sessao(s) for s in
            db.query(Sessao).filter(Sessao.encerrada_em == None).all()]

@router.get("/historico")
def historico(cliente_id: Optional[int] = None, estacao_nome: Optional[str] = None,
              limit: int = 100, db: Session = Depends(get_db),
              _=Depends(requer_perfil("admin", "operador"))):
    q = db.query(Sessao).filter(Sessao.encerrada_em != None)
    if cliente_id:
        q = q.filter(Sessao.cliente_id == cliente_id)
    if estacao_nome:
        estacao = db.query(Estacao).filter(Estacao.nome == estacao_nome).first()
        if estacao:
            q = q.filter(Sessao.estacao_id == estacao.id)
    return [serial_sessao(s) for s in q.order_by(Sessao.iniciada_em.desc()).limit(limit).all()]

@router.post("/encerrar/{sessao_id}")
async def encerrar_operador(sessao_id: int, db: Session = Depends(get_db),
                             _=Depends(requer_perfil("admin", "operador"))):
    """Operador encerra sessão manualmente pelo painel."""
    sessao = db.query(Sessao).filter(
        Sessao.id == sessao_id, Sessao.encerrada_em == None).first()
    if not sessao:
        raise HTTPException(404, "Sessão ativa não encontrada")

    agora = datetime.utcnow()
    consumido = int((agora - sessao.iniciada_em).total_seconds())
    restante = max(0, sessao.tempo_total_segundos - consumido)

    sessao.encerrada_em = agora
    sessao.tempo_consumido_segundos = consumido
    sessao.motivo_encerramento = "operador"
    sessao.cliente.saldo_segundos = restante
    sessao.estacao.status = "livre"
    estacao_nome = sessao.estacao.nome
    db.commit()

    # Avisa o agente para bloquear a tela
    await manager.enviar_estacao(estacao_nome, "encerrar_sessao",
                                  {"motivo": "operador", "saldo_restante": restante})

    # Avisa painéis que a sessão encerrou
    await manager.broadcast_paineis("sessao_encerrada", {
        "estacao": estacao_nome,
        "cliente": sessao.cliente.login,
        "motivo": "operador",
        "saldo_restante": restante
    })

    # Garante que o painel veja a estação como online/livre
    if estacao_nome in manager.estacoes_online():
        await manager.broadcast_paineis("estacao_online", {"nome": estacao_nome})

    return {"ok": True, "saldo_restante": restante}
