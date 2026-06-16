from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import csv
import io
from database import get_db
from models import Sessao, Estacao
from auth import requer_perfil

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
