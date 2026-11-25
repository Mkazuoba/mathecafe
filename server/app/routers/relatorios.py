from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta, timezone
import csv
import io
from app.database import get_db
from app.models import AcaoOperador, Sessao, Estacao, Usuario
from app.registro import ROTULOS
from app.importados import so_visiveis
from app.security import requer_perfil
from app.permissoes import requer_permissao
from app.tempo_diario import FUSO

router = APIRouter(prefix="/relatorios", tags=["relatorios"])

@router.get("/csv")
def exportar_csv(
    cliente_id: Optional[int] = None,
    estacao_nome: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(requer_permissao("relatorios")),
):
    q = so_visiveis(db.query(Sessao).filter(Sessao.encerrada_em != None), db)

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


def _filtrar(q, de, ate, db, abertas=False):
    """abertas=True inclui as sessoes em andamento (o historico mostra quem
    esta logado agora; o tempo delas so entra quando acabam)."""
    inicio, fim = _periodo_utc(de, ate)
    if not abertas:
        q = q.filter(Sessao.encerrada_em != None)
    q = so_visiveis(q, db)
    if inicio:
        q = q.filter(Sessao.iniciada_em >= inicio)
    if fim:
        q = q.filter(Sessao.iniciada_em < fim)
    return q


# 1 quando o grupo tem uma sessao em andamento
_ABERTA = func.max(case((Sessao.encerrada_em.is_(None), 1), else_=0))


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
                 func.min(Sessao.iniciada_em), func.max(Sessao.iniciada_em), _ABERTA, Estacao.id)
          .join(Estacao, Estacao.id == Sessao.estacao_id)
          .filter(Sessao.cliente_id == cliente_id), de, ate, db, abertas=True
    ).group_by(Estacao.id, Estacao.nome).order_by(func.max(Sessao.iniciada_em).desc()).all()
    # por estacao (6.18: o mesmo nome pode estar nos dois pisos), com o piso de cada
    from app.nomes_estacao import piso_id_de
    pisos = {e.id: piso_id_de(e) for e in db.query(Estacao).filter(Estacao.id.in_([l[6] for l in linhas]))}
    return {
        "cliente": {"id": cliente.id, "login": cliente.login, "nome": cliente.nome,
                    "tem_foto": cliente.foto_em is not None,
                    "foto_em": cliente.foto_em.isoformat() if cliente.foto_em else None},
        # estacao onde o cliente esta logado agora (None se nao esta)
        "em_uso": next((l[0] for l in linhas if l[5]), None),
        "sessoes": sum(l[1] for l in linhas),
        "tempo_segundos": int(sum(l[2] for l in linhas)),
        "primeira_vez": _iso(min((l[3] for l in linhas), default=None)),
        "ultima_vez": _iso(max((l[4] for l in linhas), default=None)),
        "itens": [{"estacao": nome, "estacao_id": eid, "piso_id": pisos.get(eid), "sessoes": n,
                   "tempo_segundos": int(t), "primeira_vez": _iso(p), "ultima_vez": _iso(u), "em_uso": bool(a)}
                  for nome, n, t, p, u, a, eid in linhas],
    }


@router.get("/estacao/{nome}")
def historico_da_estacao(nome: str, de: Optional[str] = None, ate: Optional[str] = None,
                         piso_id: Optional[int] = None, id: Optional[int] = None,
                         db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    """Quais clientes ja passaram pela estacao, quantas vezes e por quanto tempo.
    O nome pode estar nos dois pisos (6.18): o painel manda o piso (ou o id)."""
    from app.nomes_estacao import com_o_nome
    if id is not None:
        candidatas = db.query(Estacao).filter(Estacao.id == id).all()
    else:
        # a ativa com o nome; senao uma excluida (o historico continua valendo)
        candidatas = com_o_nome(db, nome, piso_id) or com_o_nome(db, nome, piso_id, ativas=False)[-1:]
    if not candidatas:
        raise HTTPException(404, "Estação não encontrada")
    if len(candidatas) > 1:
        raise HTTPException(409, f"Há {len(candidatas)} estações {nome} (uma em cada piso): escolha o piso")
    estacao = candidatas[0]
    tempo = func.coalesce(func.sum(Sessao.tempo_consumido_segundos), 0)
    linhas = _filtrar(
        db.query(Usuario.id, Usuario.login, Usuario.nome, func.count(Sessao.id), tempo,
                 func.min(Sessao.iniciada_em), func.max(Sessao.iniciada_em), _ABERTA)
          .join(Usuario, Usuario.id == Sessao.cliente_id)
          .filter(Sessao.estacao_id == estacao.id), de, ate, db, abertas=True
    ).group_by(Usuario.id, Usuario.login, Usuario.nome).order_by(func.max(Sessao.iniciada_em).desc()).all()
    return {
        "estacao": {"id": estacao.id, "nome": estacao.nome, "grupo": estacao.grupo.nome if estacao.grupo else None},
        "sessoes": sum(l[3] for l in linhas),
        "clientes": len(linhas),
        "tempo_segundos": int(sum(l[4] for l in linhas)),
        "primeira_vez": _iso(min((l[5] for l in linhas), default=None)),
        "ultima_vez": _iso(max((l[6] for l in linhas), default=None)),
        "itens": [{"cliente_id": i, "login": lg, "nome": nm, "sessoes": n, "tempo_segundos": int(t),
                   "primeira_vez": _iso(p), "ultima_vez": _iso(u), "em_uso": bool(a)} for i, lg, nm, n, t, p, u, a in linhas],
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
    limite: int = 500, db: Session = Depends(get_db), _=Depends(requer_permissao("relatorios")),
):
    """O que cada operador fez, do mais recente para o mais antigo."""
    limite = max(1, min(limite, 5000))
    return [_serial_acao(a) for a in _acoes_filtradas(db, operador_id, acao, cliente, estacao, de, ate, limite)]


@router.get("/acoes/tipos")
def tipos_de_acao(_=Depends(requer_permissao("relatorios"))):
    return [{"acao": k, "rotulo": v} for k, v in ROTULOS.items()]


@router.get("/acoes.csv")
def acoes_csv(
    operador_id: Optional[int] = None, acao: Optional[str] = None, cliente: Optional[str] = None,
    estacao: Optional[str] = None, de: Optional[str] = None, ate: Optional[str] = None,
    db: Session = Depends(get_db), _=Depends(requer_permissao("relatorios")),
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

def _utc(dia):
    """Meia-noite de Brasilia do dia -> UTC sem fuso, como o banco guarda."""
    return datetime.combine(dia, datetime.min.time()).replace(tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)


def _segundos_abertos(inicio_local, fim_local, db):
    """Horas em que a biblioteca abriu no periodo (horario de funcionamento
    configurado, ligado ou nao), ate agora: um dia futuro nao conta e o de hoje
    conta so ate este momento. Devolve (segundos, dias abertos)."""
    from app import horario as hor
    dias_cfg = hor.carregar(db)["dias"]
    agora = datetime.now(FUSO).replace(tzinfo=None)
    total, dias = 0, 0
    dia = inicio_local
    while dia <= fim_local and dia <= agora.date():
        cfg = dias_cfg[dia.weekday()]
        if cfg.get("aberto"):
            abre = datetime.combine(dia, datetime.strptime(cfg["abre"], "%H:%M").time())
            fecha = min(datetime.combine(dia, datetime.strptime(cfg["fecha"], "%H:%M").time()), agora)
            if fecha > abre:
                total += int((fecha - abre).total_seconds())
                dias += 1
        dia += timedelta(days=1)
    return total, dias


def _calcular_uso(db: Session, inicio_local, fim_local, piso_id: Optional[int]):
    """Os numeros da aba Uso (e da planilha): so sessoes encerradas, datas de Brasilia."""
    from collections import defaultdict
    from app.pisos import piso_da_estacao

    todas = db.query(Estacao).all()
    piso_de = {e.id: piso_da_estacao(e) for e in todas}
    nomes = {e.id: e.nome for e in todas}
    nome_piso = {i: (p.nome if p else "") for i, p in piso_de.items()}

    # so os campos usados (com o historico do VSCyber sao centenas de milhares)
    q = db.query(Sessao.cliente_id, Sessao.estacao_id, Sessao.iniciada_em, Sessao.tempo_consumido_segundos).filter(
                                Sessao.encerrada_em != None,
                                Sessao.iniciada_em >= _utc(inicio_local),
                                Sessao.iniciada_em < _utc(fim_local + timedelta(days=1)))
    q = so_visiveis(q, db)
    if piso_id:
        do_piso = [i for i, p in piso_de.items() if p and p.id == piso_id]
        q = q.filter(Sessao.estacao_id.in_(do_piso or [-1]))

    total = {"sessoes": 0, "segundos": 0}
    clientes = set()
    dias = defaultdict(lambda: {"sessoes": 0, "segundos": 0, "clientes": set()})
    pico = defaultdict(int)
    estacoes = defaultdict(lambda: {"sessoes": 0, "segundos": 0})
    pisos = defaultdict(lambda: {"sessoes": 0, "segundos": 0, "clientes": set()})
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
        e = estacoes[s.estacao_id]
        e["sessoes"] += 1
        e["segundos"] += uso
        p = pisos[nome_piso.get(s.estacao_id, "")]
        p["sessoes"] += 1
        p["segundos"] += uso
        p["clientes"].add(s.cliente_id)
        # o uso espalhado pelas horas em que aconteceu
        momento, resta = inicio, uso
        while resta > 0:
            proxima_hora = momento.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            pedaco = min(resta, int((proxima_hora - momento).total_seconds()) or 3600)
            pico[(momento.weekday(), momento.hour)] += pedaco
            resta -= pedaco
            momento += timedelta(seconds=pedaco)

    # ocupacao: uso / (estacoes cadastradas x horas em que a biblioteca abriu)
    abertas_seg, dias_abertos = _segundos_abertos(inicio_local, fim_local, db)
    n_estacoes = sum(1 for e in todas if e.ativa and e.aprovada
                     and (not piso_id or (piso_de[e.id] and piso_de[e.id].id == piso_id)))
    disponivel = abertas_seg * n_estacoes

    def pct(usado, de):
        return round(usado / de * 100, 1) if de else None

    return {
        "periodo": {"de": inicio_local.isoformat(), "ate": fim_local.isoformat()},
        "resumo": {**total, "clientes": len(clientes),
                   "media_segundos": total["segundos"] // total["sessoes"] if total["sessoes"] else 0,
                   "ocupacao": {"percentual": pct(total["segundos"], disponivel), "estacoes": n_estacoes,
                                "dias_abertos": dias_abertos, "disponivel_segundos": disponivel}},
        "por_dia": [{"dia": dia, "sessoes": v["sessoes"], "segundos": v["segundos"], "clientes": len(v["clientes"])}
                    for dia, v in sorted(dias.items())],
        "por_piso": sorted(({"piso": nome, "sessoes": v["sessoes"], "segundos": v["segundos"],
                             "clientes": len(v["clientes"])} for nome, v in pisos.items()),
                           key=lambda x: (-x["segundos"], x["piso"])),
        "pico": [{"dia_semana": k[0], "hora": k[1], "segundos": v} for k, v in sorted(pico.items())],
        "estacoes": sorted(({"estacao": nomes.get(i, "?"), "piso": nome_piso.get(i, ""), **v,
                             "ocupacao": pct(v["segundos"], abertas_seg)} for i, v in estacoes.items()),
                           key=lambda x: (-x["segundos"], x["estacao"])),
    }


@router.get("/uso")
def relatorio_de_uso(
    de: Optional[str] = None, ate: Optional[str] = None, piso_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(requer_permissao("relatorios")),
):
    """Uso no periodo (datas de Brasilia, padrao: ultimos 30 dias), so sessoes
    encerradas: resumo (com a ocupacao), por dia, por piso, pico (dia da semana
    x hora) e estacoes."""
    hoje = datetime.now(FUSO).date()
    fim_local = datetime.strptime(ate, "%Y-%m-%d").date() if ate else hoje
    inicio_local = datetime.strptime(de, "%Y-%m-%d").date() if de else fim_local - timedelta(days=29)
    return _calcular_uso(db, inicio_local, fim_local, piso_id)


DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@router.get("/uso.xlsx")
def exportar_uso_do_mes(
    mes: str, piso_id: Optional[int] = None,
    db: Session = Depends(get_db), _=Depends(requer_permissao("relatorios")),
):
    """O uso de um mes (AAAA-MM) numa planilha: Resumo, Por dia, Por estacao e Sessoes."""
    import calendar
    from app import planilha as pl
    from app.models import Piso
    from app.pisos import piso_da_estacao
    try:
        primeiro = datetime.strptime(mes, "%Y-%m").date()
    except ValueError:
        raise HTTPException(400, "Mês no formato AAAA-MM")
    ultimo = primeiro.replace(day=calendar.monthrange(primeiro.year, primeiro.month)[1])
    u = _calcular_uso(db, primeiro, ultimo, piso_id)
    piso = db.query(Piso).filter(Piso.id == piso_id).first() if piso_id else None
    r, oc = u["resumo"], u["resumo"]["ocupacao"]

    def br(d):
        return d.strftime("%d/%m/%Y")

    resumo = [
        [pl.Negrito("Relatório de uso dos computadores"), ""],
        ["Período", f"{br(primeiro)} a {br(ultimo)}"],
        ["Piso", piso.nome if piso else "Todos os pisos"],
        ["Gerado em", datetime.now(FUSO).replace(tzinfo=None)],
        [],
        [pl.Negrito("Uso total no período"), pl.Duracao(r["segundos"])],
        ["Sessões", r["sessoes"]],
        ["Clientes diferentes", r["clientes"]],
        ["Média por sessão", pl.Duracao(r["media_segundos"])],
        ["Dias de funcionamento", oc["dias_abertos"]],
        ["Média de uso por dia aberto", pl.Duracao(r["segundos"] // oc["dias_abertos"] if oc["dias_abertos"] else 0)],
        ["Estações", oc["estacoes"]],
        ["Horas disponíveis (estações x horário)", pl.Duracao(oc["disponivel_segundos"])],
        ["Ocupação das estações", pl.Porcentagem(oc["percentual"])],
    ]
    if not piso and u["por_piso"]:
        resumo += [[], [pl.Negrito("Piso"), pl.Negrito("Sessões"), pl.Negrito("Uso"), pl.Negrito("Clientes")]]
        resumo += [[p["piso"] or "(sem piso)", p["sessoes"], pl.Duracao(p["segundos"]), p["clientes"]]
                   for p in u["por_piso"]]

    por_dia = {d["dia"]: d for d in u["por_dia"]}
    dias = [["Dia", "Dia da semana", "Sessões", "Uso", "Clientes"]]
    d = primeiro
    while d <= ultimo:
        v = por_dia.get(d.isoformat(), {"sessoes": 0, "segundos": 0, "clientes": 0})
        dias.append([d, DIAS_SEMANA[d.weekday()], v["sessoes"], pl.Duracao(v["segundos"]), v["clientes"]])
        d += timedelta(days=1)
    dias.append([pl.Negrito("Total"), "", r["sessoes"], pl.Duracao(r["segundos"]), r["clientes"]])

    estacoes = [["Estação", "Piso", "Sessões", "Uso", "Ocupação"]]
    estacoes += [[e["estacao"], e["piso"], e["sessoes"], pl.Duracao(e["segundos"]), pl.Porcentagem(e["ocupacao"])]
                 for e in u["estacoes"]]

    # cada sessao do mes, da mais antiga para a mais nova
    q = (db.query(Sessao).filter(Sessao.encerrada_em != None, Sessao.iniciada_em >= _utc(primeiro),
                                 Sessao.iniciada_em < _utc(ultimo + timedelta(days=1))))
    q = so_visiveis(q, db).order_by(Sessao.iniciada_em)

    def local(t):
        return t.replace(tzinfo=timezone.utc).astimezone(FUSO).replace(tzinfo=None) if t else None

    sessoes = [["Início", "Fim", "Login", "Cliente", "Estação", "Piso", "Uso", "Encerramento"]]
    for s in q.all():
        p = piso_da_estacao(s.estacao) if s.estacao else None
        if piso_id and (not p or p.id != piso_id):
            continue
        sessoes.append([local(s.iniciada_em), local(s.encerrada_em), s.cliente.login if s.cliente else "",
                        s.cliente.nome if s.cliente else "", s.estacao.nome if s.estacao else "",
                        p.nome if p else "", pl.Duracao(s.tempo_consumido_segundos or 0),
                        s.motivo_encerramento or ""])

    conteudo = pl.gerar([
        pl.Aba("Resumo", resumo, larguras=[38, 24, 12, 12], cabecalho=False),
        pl.Aba("Por dia", dias, larguras=[12, 14, 10, 12, 10]),
        pl.Aba("Por estação", estacoes, larguras=[16, 12, 10, 12, 11]),
        pl.Aba("Sessões", sessoes, larguras=[17, 17, 14, 30, 12, 12, 10, 16]),
    ])
    sufixo = f"_{piso.nome.lower()}" if piso else ""
    return StreamingResponse(
        iter([conteudo]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=uso_{mes}{sufixo}.xlsx"},
    )
