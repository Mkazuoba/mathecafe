from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models import Sessao, Estacao
from app.security import requer_perfil
from app.websocket_manager import manager
from app.tempo_diario import fechar_tempo_da_sessao

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
        "ativa": s.encerrada_em is None,
        "pausada": bool(s.pausada),
        # o painel para a contagem a partir daqui enquanto a sessao esta pausada
        "pausada_em": s.pausada_em.isoformat() if s.pausada and s.pausada_em else None
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
    restante = await encerrar_pelo_operador(db, sessao)
    return {"ok": True, "saldo_restante": restante}


async def encerrar_pelo_operador(db: Session, sessao: Sessao, avisar_agente: bool = True) -> int:
    """Encerra a sessao como "operador", devolvendo ao cliente o tempo que sobrou.
    Sem avisar o agente quando quem chama ja manda outro comando (desligar,
    reiniciar), que tambem tira o cliente da sessao."""
    agora = datetime.utcnow()
    _, restante = fechar_tempo_da_sessao(sessao, agora)

    sessao.encerrada_em = agora
    sessao.motivo_encerramento = "operador"
    sessao.cliente.saldo_segundos = restante
    sessao.estacao.status = "livre"
    sessao.sem_conexao_desde = None
    estacao_nome = sessao.estacao.nome
    db.commit()

    # Avisa o agente para bloquear a tela
    if avisar_agente:
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
    return restante


@router.post("/pausar/{sessao_id}")
async def pausar_sessao(sessao_id: int, db: Session = Depends(get_db),
                         _=Depends(requer_perfil("admin", "operador"))):
    s = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.encerrada_em == None).first()
    if not s:
        raise HTTPException(404, "Sessao ativa nao encontrada")
    if s.pausada:
        raise HTTPException(400, "Sessao ja pausada")
    s.pausada = True
    s.pausada_em = datetime.utcnow()
    estacao_nome = s.estacao.nome
    db.commit()
    await manager.enviar_estacao(estacao_nome, "pausar_sessao", {})
    await manager.broadcast_paineis("sessao_pausada", {"estacao": estacao_nome, "sessao_id": sessao_id})
    return {"ok": True}


@router.post("/retomar/{sessao_id}")
async def retomar_sessao(sessao_id: int, db: Session = Depends(get_db),
                          _=Depends(requer_perfil("admin", "operador"))):
    s = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.encerrada_em == None).first()
    if not s:
        raise HTTPException(404, "Sessao ativa nao encontrada")
    if not s.pausada:
        raise HTTPException(400, "Sessao nao esta pausada")
    agora = datetime.utcnow()
    tempo_em_pausa = int((agora - s.pausada_em).total_seconds())
    s.tempo_pausado_segundos = (s.tempo_pausado_segundos or 0) + tempo_em_pausa
    s.pausada = False
    s.pausada_em = None
    # Estende o tempo total para compensar a pausa
    s.tempo_total_segundos = (s.tempo_total_segundos or 0) + tempo_em_pausa
    estacao_nome = s.estacao.nome
    db.commit()
    await manager.enviar_estacao(estacao_nome, "retomar_sessao",
                                  {"tempo_total_segundos": s.tempo_total_segundos})
    await manager.broadcast_paineis("sessao_retomada", {"estacao": estacao_nome, "sessao_id": sessao_id})
    return {"ok": True}


@router.post("/renovar/{sessao_id}")
async def renovar_sessao(sessao_id: int, minutos: int, db: Session = Depends(get_db),
                          _=Depends(requer_perfil("admin", "operador"))):
    if minutos <= 0:
        raise HTTPException(400, "Minutos deve ser maior que zero")
    s = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.encerrada_em == None).first()
    if not s:
        raise HTTPException(404, "Sessao ativa nao encontrada")
    segundos_extra = minutos * 60
    s.tempo_total_segundos = (s.tempo_total_segundos or 0) + segundos_extra
    estacao_nome = s.estacao.nome
    db.commit()
    await manager.enviar_estacao(estacao_nome, "renovar_sessao",
                                  {"tempo_total_segundos": s.tempo_total_segundos})
    await manager.broadcast_paineis("sessao_renovada", {
        "estacao": estacao_nome,
        "sessao_id": sessao_id,
        "tempo_total_segundos": s.tempo_total_segundos
    })
    return {"ok": True, "tempo_total_segundos": s.tempo_total_segundos}
