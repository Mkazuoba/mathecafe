from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta, timezone
import csv
import io
from app.database import get_db
from app.models import AcaoOperador, Sessao, Estacao, Usuario
from app.registro import ROTULOS
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


# ── Acoes dos operadores (8.1) ───────────────────────────────────────────────

def _acoes_filtradas(db: Session, operador_id, acao, cliente, estacao, de, ate, limite):
    q = db.query(AcaoOperador)
    if operador_id:
        q = q.filter(AcaoOperador.operador_id == operador_id)
    if acao:
        q = q.filter(AcaoOperador.acao == acao)
    if estacao:
        q = q.filter(AcaoOperador.estacao == estacao)
    if cliente:
        termo = f"%{cliente.strip().lower()}%"
        q = q.filter((func.lower(AcaoOperador.cliente_login).like(termo)) |
                     (func.lower(AcaoOperador.cliente_nome).like(termo)))
    # datas do painel sao de Brasilia; o registro guarda UTC
    if de:
        inicio = datetime.strptime(de, "%Y-%m-%d").replace(tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)
        q = q.filter(AcaoOperador.quando >= inicio)
    if ate:
        fim = (datetime.strptime(ate, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=FUSO)
        q = q.filter(AcaoOperador.quando < fim.astimezone(timezone.utc).replace(tzinfo=None))
    return q.order_by(AcaoOperador.quando.desc(), AcaoOperador.id.desc()).limit(limite).all()


def _serial_acao(a: AcaoOperador) -> dict:
    return {
        "id": a.id,
        "quando": a.quando.isoformat() + "Z",
        "operador_id": a.operador_id,
        "operador": a.operador_nome,
        "acao": a.acao,
        "rotulo": ROTULOS.get(a.acao, a.acao),
        "cliente_id": a.cliente_id,
        "cliente_login": a.cliente_login,
        "cliente_nome": a.cliente_nome,
        "estacao": a.estacao,
        "detalhe": a.detalhe,
    }


@router.get("/acoes")
def acoes_dos_operadores(
    operador_id: Optional[int] = None, acao: Optional[str] = None, cliente: Optional[str] = None,
    estacao: Optional[str] = None, de: Optional[str] = None, ate: Optional[str] = None,
    limite: int = 500, db: Session = Depends(get_db), _=Depends(requer_perfil("admin")),
):
    """O que cada operador fez, do mais recente para o mais antigo."""
    limite = max(1, min(limite, 5000))
    return [_serial_acao(a) for a in _acoes_filtradas(db, operador_id, acao, cliente, estacao, de, ate, limite)]


@router.get("/acoes/tipos")
def tipos_de_acao(_=Depends(requer_perfil("admin"))):
    return [{"acao": k, "rotulo": v} for k, v in ROTULOS.items()]


@router.get("/acoes.csv")
def acoes_csv(
    operador_id: Optional[int] = None, acao: Optional[str] = None, cliente: Optional[str] = None,
    estacao: Optional[str] = None, de: Optional[str] = None, ate: Optional[str] = None,
    db: Session = Depends(get_db), _=Depends(requer_perfil("admin")),
):
    acoes = _acoes_filtradas(db, operador_id, acao, cliente, estacao, de, ate, 100000)
    saida = io.StringIO()
    saida.write("\ufeff")  # o Excel abre com acentos
    w = csv.writer(saida, delimiter=";")
    w.writerow(["Quando", "Operador", "Ação", "Cliente", "Login", "Estação", "Detalhe"])
    for a in acoes:
        quando = a.quando.replace(tzinfo=timezone.utc).astimezone(FUSO).strftime("%d/%m/%Y %H:%M:%S")
        w.writerow([quando, a.operador_nome, ROTULOS.get(a.acao, a.acao), a.cliente_nome or "",
                    a.cliente_login or "", a.estacao or "", a.detalhe or ""])
    saida.seek(0)
    return StreamingResponse(iter([saida.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=acoes_operadores.csv"})


# ── Relatorio de uso (8.2) ───────────────────────────────────────────────────

@router.get("/uso")
def relatorio_de_uso(
    de: Optional[str] = None, ate: Optional[str] = None, piso_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(requer_perfil("admin")),
):
    """Uso no periodo (datas de Brasilia, padrao: ultimos 30 dias), so sessoes
    encerradas: resumo, por dia, pico (dia da semana x hora) e estacoes."""
    from collections import defaultdict
    from app.pisos import piso_da_estacao

    hoje = datetime.now(FUSO).date()
    fim_local = datetime.strptime(ate, "%Y-%m-%d").date() if ate else hoje
    inicio_local = datetime.strptime(de, "%Y-%m-%d").date() if de else fim_local - timedelta(days=29)

    def utc(dia):
        return datetime.combine(dia, datetime.min.time()).replace(tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)

    q = db.query(Sessao).filter(Sessao.encerrada_em != None,
                                Sessao.iniciada_em >= utc(inicio_local),
                                Sessao.iniciada_em < utc(fim_local + timedelta(days=1)))
    if piso_id:
        do_piso = [e.id for e in db.query(Estacao).all() if (p := piso_da_estacao(e)) and p.id == piso_id]
        q = q.filter(Sessao.estacao_id.in_(do_piso or [-1]))

    total = {"sessoes": 0, "segundos": 0}
    clientes = set()
    dias = defaultdict(lambda: {"sessoes": 0, "segundos": 0, "clientes": set()})
    pico = defaultdict(int)
    estacoes = defaultdict(lambda: {"sessoes": 0, "segundos": 0})
    for s in q.all():
        uso = max(0, s.tempo_consumido_segundos or 0)
        inicio = s.iniciada_em.replace(tzinfo=timezone.utc).astimezone(FUSO).replace(tzinfo=None)
        total["sessoes"] += 1
        total["segundos"] += uso
        clientes.add(s.cliente_id)
        d = dias[inicio.date().isoformat()]
        d["sessoes"] += 1
        d["segundos"] += uso
        d["clientes"].add(s.cliente_id)
        e = estacoes[s.estacao.nome if s.estacao else "?"]
        e["sessoes"] += 1
        e["segundos"] += uso
        # o uso espalhado pelas horas em que aconteceu
        momento, resta = inicio, uso
        while resta > 0:
            proxima_hora = momento.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            pedaco = min(resta, int((proxima_hora - momento).total_seconds()) or 3600)
            pico[(momento.weekday(), momento.hour)] += pedaco
            resta -= pedaco
            momento += timedelta(seconds=pedaco)

    return {
        "periodo": {"de": inicio_local.isoformat(), "ate": fim_local.isoformat()},
        "resumo": {**total, "clientes": len(clientes),
                   "media_segundos": total["segundos"] // total["sessoes"] if total["sessoes"] else 0},
        "por_dia": [{"dia": dia, "sessoes": v["sessoes"], "segundos": v["segundos"], "clientes": len(v["clientes"])}
                    for dia, v in sorted(dias.items())],
        "pico": [{"dia_semana": k[0], "hora": k[1], "segundos": v} for k, v in sorted(pico.items())],
        "estacoes": sorted(({"estacao": nome, **v} for nome, v in estacoes.items()),
                           key=lambda x: (-x["segundos"], x["estacao"])),
    }
