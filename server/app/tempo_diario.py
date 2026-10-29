"""Tempo do dia de cada cliente.

Todo cliente tem por dia o tempo padrão das Configurações. O que sobra fica
para o mesmo dia; à meia-noite de Brasília zera e ele volta a ter a cota
cheia. Quando o tempo do dia acaba, só volta amanhã, a não ser que o operador
edite o saldo (tempo extra).

`usuarios.saldo_dia` diz de que dia é o `saldo_segundos`: saldo de outro dia
(ou nunca usado) vale a cota cheia. Assim o reset não precisa de tarefa
agendada à meia-noite.
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import case, func, literal
from sqlalchemy.orm import Session, object_session

from app.models import ConfiguracaoSistema, Usuario

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
COTA_PADRAO = 7200

ESGOTADO_OPERADOR = "O tempo de hoje deste cliente acabou. Para dar tempo extra, edite o saldo dele."
ESGOTADO_CLIENTE = "Seu tempo de hoje acabou. Volte amanhã!"


def hoje_br(agora: Optional[datetime] = None) -> date:
    """O dia em São Paulo (o servidor guarda as datas em UTC)."""
    agora = agora or datetime.now(timezone.utc)
    return agora.astimezone(FUSO).date()


def cota_diaria(db: Session) -> int:
    cfg = db.query(ConfiguracaoSistema).filter(
        ConfiguracaoSistema.chave == "tempo_padrao_segundos").first()
    try:
        return int(cfg.valor) if cfg else COTA_PADRAO
    except ValueError:
        return COTA_PADRAO


def saldo_do_dia(cliente: Usuario, cota: Optional[int] = None) -> int:
    """Quanto o cliente ainda pode usar hoje."""
    if cliente.saldo_dia != hoje_br():
        return cota if cota is not None else cota_diaria(object_session(cliente))
    return cliente.saldo_segundos or 0


def saldo_do_dia_sql(cota: int):
    """saldo_do_dia como expressão SQL (filtrar e ordenar a busca de clientes)."""
    return case(
        (Usuario.saldo_dia == hoje_br(), func.coalesce(Usuario.saldo_segundos, 0)),
        else_=literal(cota),
    )


def reservar_tempo(db: Session, cliente: Usuario) -> Optional[int]:
    """Tempo da sessão que vai começar, ou None se o de hoje acabou.
    O saldo fica 0 durante a sessão; no fim volta o que sobrou."""
    tempo = saldo_do_dia(cliente, cota_diaria(db))
    if tempo <= 0:
        return None
    cliente.saldo_segundos = 0
    cliente.saldo_dia = hoje_br()
    return tempo


def zerar_tempo_de_hoje(db: Session) -> int:
    """Todos os clientes voltam à cota cheia agora (o que a meia-noite faria)."""
    n = db.query(Usuario).filter(Usuario.perfil == "cliente", Usuario.saldo_dia != None) \
          .update({Usuario.saldo_dia: None}, synchronize_session=False)
    db.commit()
    return n
