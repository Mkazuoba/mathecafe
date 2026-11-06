"""Sessoes importadas do VSCyber (importar_historico.py, motivo "vscyber").

Ficam guardadas no banco, mas por enquanto nao aparecem em nenhum historico
nem relatorio (pedido do Matheus em 06/11/2026: a importacao ainda precisa de
ajustes). Para mostrar: configuracoes.historico_vscyber_visivel = "true".
"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import ConfiguracaoSistema, Sessao

MOTIVO = "vscyber"
CHAVE = "historico_vscyber_visivel"


def visivel(db: Session) -> bool:
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE).first()
    return bool(cfg) and cfg.valor == "true"


def so_visiveis(q, db: Session):
    """A consulta de sessoes sem as importadas do VSCyber, enquanto estiverem escondidas."""
    if visivel(db):
        return q
    return q.filter(or_(Sessao.motivo_encerramento == None, Sessao.motivo_encerramento != MOTIVO))
