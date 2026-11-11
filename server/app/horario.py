"""Horario de funcionamento da biblioteca (8.4).

Configurado em Configuracoes -> Horario (chave "horario_funcionamento" em
configuracoes, JSON): ligado ou nao, e para cada dia da semana (0 = segunda)
se abre e das quantas as quantas, no horario de Brasilia.

Ligado: o batimento (main.py) avisa os clientes 10 e 5 minutos antes de fechar
e, fora do horario, encerra as sessoes devolvendo o tempo que sobrou; o login
no PC e o liberar direto sao recusados.
"""
import json
import math
from datetime import datetime, time
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ConfiguracaoSistema, Sessao
from app.tempo_diario import FUSO, fechar_tempo_da_sessao

CHAVE = "horario_funcionamento"
AVISOS_MINUTOS = (10, 5)
FECHADA = "A biblioteca está fechada agora."
PADRAO = {"ativo": False, "dias": [{"aberto": True, "abre": "08:00", "fecha": "20:00"} for _ in range(7)]}


def carregar(db: Session) -> dict:
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE).first()
    if cfg:
        try:
            horario = json.loads(cfg.valor)
            if isinstance(horario, dict) and len(horario.get("dias") or []) == 7:
                return horario
        except ValueError:
            pass
    return json.loads(json.dumps(PADRAO))


def gravar(db: Session, horario: dict):
    valor = json.dumps(horario, ensure_ascii=False)
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE).first()
    if cfg:
        cfg.valor = valor
    else:
        db.add(ConfiguracaoSistema(chave=CHAVE, valor=valor))
    db.commit()


def agora_local() -> datetime:
    """Agora em Brasilia, sem fuso (para comparar com os horarios do painel)."""
    return datetime.now(FUSO).replace(tzinfo=None)


def _hora(texto: str) -> time:
    h, m = texto.split(":")
    return time(int(h), int(m))


def minutos_para_fechar(horario: dict, agora: datetime) -> Optional[int]:
    """Minutos (arredondados para cima) ate fechar, se esta aberto agora; senao None."""
    dia = horario["dias"][agora.weekday()]
    if not dia.get("aberto"):
        return None
    abre = datetime.combine(agora.date(), _hora(dia["abre"]))
    fecha = datetime.combine(agora.date(), _hora(dia["fecha"]))
    if not (abre <= agora < fecha):
        return None
    return math.ceil((fecha - agora).total_seconds() / 60)


def esta_fechada(horario: dict, agora: datetime) -> bool:
    return bool(horario.get("ativo")) and minutos_para_fechar(horario, agora) is None


def decidir(horario: dict, agora: datetime, avisados: set) -> dict:
    """O que fazer agora: avisar (10 ou 5 minutos antes, uma vez cada por dia) ou
    encerrar as sessoes (fora do horario). `avisados` guarda o que ja foi dito."""
    if not horario.get("ativo"):
        return {"aviso": None, "encerrar": False}
    faltam = minutos_para_fechar(horario, agora)
    if faltam is None:
        return {"aviso": None, "encerrar": True}
    vencidos = [m for m in AVISOS_MINUTOS if faltam <= m]
    if not vencidos or (agora.date(), min(vencidos)) in avisados:
        return {"aviso": None, "encerrar": False}
    # servidor fora do ar na hora do primeiro aviso: diz so o mais urgente
    for m in vencidos:
        avisados.add((agora.date(), m))
    return {"aviso": min(vencidos), "encerrar": False}


def texto_do_aviso(horario: dict, agora: datetime, minutos: int) -> str:
    fecha = horario["dias"][agora.weekday()]["fecha"]
    return (f"A biblioteca fecha às {fecha}. Sua sessão termina em {minutos} minutos: "
            "salve o que estiver fazendo.")


def encerrar_sessoes_do_fechamento(db: Session) -> list:
    """Encerra as sessoes abertas como "horario", devolvendo o tempo que sobrou.
    Devolve [(id da estacao, restante)] para avisar agentes e paineis."""
    agora = datetime.utcnow()
    encerradas = []
    for sessao in db.query(Sessao).filter(Sessao.encerrada_em == None).all():
        _, restante = fechar_tempo_da_sessao(sessao, agora)
        sessao.encerrada_em = agora
        sessao.motivo_encerramento = "horario"
        sessao.cliente.saldo_segundos = restante
        sessao.sem_conexao_desde = None
        if sessao.estacao.status == "ocupada":
            sessao.estacao.status = "livre"
        encerradas.append((sessao.estacao_id, restante))
    db.commit()
    return encerradas
