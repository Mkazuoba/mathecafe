from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta, timezone
import csv
import io
from app.database import get_db
from app.models import Sessao, Estacao, Usuario
from app.security import requer_perfil
from app.tempo_diario import FUSO

router = APIRouter(prefix="/relatorios", tags=["relatorios"])

@router.get("/csv")
def exportar_csv(
    cliente_id: Optional[int] = None,
    estacao_nome: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(requer_perfil("admin")),
):
    q = db.query(Sessao).filter(Sessao.encerrada_em != None)

    if cliente_id:
        q = q.filter(Sessao.cliente_id == cliente_id)
    if estacao_nome:
        estacao = db.query(Estacao).filter(Estacao.nome == estacao_nome).first()
        if estacao:
            q = q.filter(Sessao.estacao_id == estacao.id)
    if data_inicio:
        inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        q = q.filter(Sessao.iniciada_em >= inicio)
    if data_fim:
        fim = datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
        q = q.filter(Sessao.iniciada_em < fim)

    sessoes = q.order_by(Sessao.iniciada_em.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "cliente_login", "cliente_nome", "estacao", "iniciada_em", "encerrada_em",
        "tempo_total_min", "tempo_consumido_min", "saldo_restante_min", "motivo_encerramento"
    ])

    for s in sessoes:
        tempo_total_min = round((s.tempo_total_segundos or 0) / 60, 1)
        tempo_consumido_min = round((s.tempo_consumido_segundos or 0) / 60, 1)
        saldo_restante_min = round(max(0, (s.tempo_total_segundos or 0) - (s.tempo_consumido_segundos or 0)) / 60, 1)
        writer.writerow([
            s.cliente.login,
            s.cliente.nome,
            s.estacao.nome,
            s.iniciada_em.isoformat() if s.iniciada_em else "",
            s.encerrada_em.isoformat() if s.encerrada_em else "",
            tempo_total_min,
            tempo_consumido_min,
            saldo_restante_min,
            s.motivo_encerramento or "",
        ])

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=relatorio_sessoes.csv"}
    )


# ── Historicos: maquinas de um cliente / clientes de uma maquina ─────────────

def _periodo_utc(de: Optional[str], ate: Optional[str]):
    """Dias de Brasilia (AAAA-MM-DD) -> intervalo em UTC, como o banco guarda."""
    def utc(dia: str, mais_um=False):
        try:
            d = datetime.strptime(dia, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Data no formato AAAA-MM-DD")
        if mais_um:
            d += timedelta(days=1)
        return d.replace(tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)
    return (utc(de) if de else None), (utc(ate, mais_um=True) if ate else None)


def _filtrar(q, de, ate):
    inicio, fim = _periodo_utc(de, ate)
    q = q.filter(Sessao.encerrada_em != None)
    if inicio:
        q = q.filter(Sessao.iniciada_em >= inicio)
    if fim:
        q = q.filter(Sessao.iniciada_em < fim)
    return q


def _iso(d):
    return d.isoformat() if d else None


@router.get("/cliente/{cliente_id}")
def historico_do_cliente(cliente_id: int, de: Optional[str] = None, ate: Optional[str] = None,
                         db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    """Quais estacoes o cliente ja usou, quantas vezes e por quanto tempo."""
    cliente = db.query(Usuario).filter(Usuario.id == cliente_id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    tempo = func.coalesce(func.sum(Sessao.tempo_consumido_segundos), 0)
    linhas = _filtrar(
        db.query(Estacao.nome, func.count(Sessao.id), tempo,
                 func.min(Sessao.iniciada_em), func.max(Sessao.iniciada_em))
          .join(Estacao, Estacao.id == Sessao.estacao_id)
          .filter(Sessao.cliente_id == cliente_id), de, ate
    ).group_by(Estacao.nome).order_by(func.max(Sessao.iniciada_em).desc()).all()
    return {
        "cliente": {"id": cliente.id, "login": cliente.login, "nome": cliente.nome},
        "sessoes": sum(l[1] for l in linhas),
        "tempo_segundos": int(sum(l[2] for l in linhas)),
        "primeira_vez": _iso(min((l[3] for l in linhas), default=None)),
        "ultima_vez": _iso(max((l[4] for l in linhas), default=None)),
        "itens": [{"estacao": nome, "sessoes": n, "tempo_segundos": int(t), "primeira_vez": _iso(p),
                   "ultima_vez": _iso(u)} for nome, n, t, p, u in linhas],
    }


@router.get("/estacao/{nome}")
def historico_da_estacao(nome: str, de: Optional[str] = None, ate: Optional[str] = None,
                         db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    """Quais clientes ja passaram pela estacao, quantas vezes e por quanto tempo."""
    estacao = db.query(Estacao).filter(Estacao.nome == nome).first()
    if not estacao:
        raise HTTPException(404, "Estação não encontrada")
    tempo = func.coalesce(func.sum(Sessao.tempo_consumido_segundos), 0)
    linhas = _filtrar(
        db.query(Usuario.id, Usuario.login, Usuario.nome, func.count(Sessao.id), tempo,
                 func.min(Sessao.iniciada_em), func.max(Sessao.iniciada_em))
          .join(Usuario, Usuario.id == Sessao.cliente_id)
          .filter(Sessao.estacao_id == estacao.id), de, ate
    ).group_by(Usuario.id, Usuario.login, Usuario.nome).order_by(func.max(Sessao.iniciada_em).desc()).all()
    return {
        "estacao": {"id": estacao.id, "nome": estacao.nome, "grupo": estacao.grupo.nome if estacao.grupo else None},
        "sessoes": sum(l[3] for l in linhas),
        "clientes": len(linhas),
        "tempo_segundos": int(sum(l[4] for l in linhas)),
        "primeira_vez": _iso(min((l[5] for l in linhas), default=None)),
        "ultima_vez": _iso(max((l[6] for l in linhas), default=None)),
        "itens": [{"cliente_id": i, "login": lg, "nome": nm, "sessoes": n, "tempo_segundos": int(t),
                   "primeira_vez": _iso(p), "ultima_vez": _iso(u)} for i, lg, nm, n, t, p, u in linhas],
    }
