"""Cadastro automatico das estacoes (agente 1.14).

O instalador so pergunta o nome e o servidor. O agente gera um identificador
(UUID, guardado no agente.cfg) e conecta com ?id=. Um PC que o servidor ainda
nao conhece entra como estacao PENDENTE: aparece em "Novas estacoes" no painel,
fora do mapa, e ninguem faz login nele ate um admin aprovar (com nome e mapa).

O identificador, e nao o nome, e o que liga o PC a estacao: renomear no painel
nao perde a conexao, e um segundo PC instalado com o mesmo nome vira outra
estacao (com sufixo) em vez de tomar o lugar da primeira.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Estacao

TAMANHO_NOME = 20  # Estacao.nome e String(20)
AGUARDANDO = "Este computador aguarda aprovação no painel do MatheCafé"


def nome_livre(db: Session, desejado: str, ignorar_id: Optional[int] = None) -> str:
    """O nome pedido, ou com -2, -3... se outra estacao (ate excluida) ja o usa."""
    base = (desejado or "").strip()[:TAMANHO_NOME] or "PC"

    def usado(nome):
        q = db.query(Estacao).filter(Estacao.nome == nome)
        if ignorar_id:
            q = q.filter(Estacao.id != ignorar_id)
        return q.first() is not None

    if not usado(base):
        return base
    n = 2
    while True:
        sufixo = f"-{n}"
        nome = base[:TAMANHO_NOME - len(sufixo)] + sufixo
        if not usado(nome):
            return nome
        n += 1


def estacao_do_agente(db: Session, nome: str, identificador: Optional[str]) -> Tuple[Optional[Estacao], bool]:
    """A estacao deste agente: (estacao, nova_pendente). (None, False) = recusar a
    conexao (agente antigo com nome desconhecido, ou PC recusado no painel)."""
    identificador = (identificador or "").strip()[:64] or None
    nome = (nome or "").strip()

    if identificador:
        e = db.query(Estacao).filter(Estacao.identificador == identificador).first()
        if e:
            if e.ativa:
                return e, False
            if not e.aprovada:
                return None, False  # recusada em "Novas estacoes"
            # excluida no painel e o agente continua instalado: volta para aprovar
            e.ativa, e.aprovada, e.grupo_id = True, False, None
            db.commit()
            return e, True

    e = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if e and not (identificador and e.identificador):
        if identificador:
            # estacao cadastrada do jeito antigo recebendo o agente 1.14: adota o id
            e.identificador = identificador
            db.commit()
        return e, False
    if not identificador:
        return None, False

    e = Estacao(nome=nome_livre(db, nome), identificador=identificador, aprovada=False, status="livre")
    db.add(e)
    db.commit()
    db.refresh(e)
    return e, True


def info_para_o_agente(e: Estacao) -> dict:
    return {"nome": e.nome, "aprovada": bool(e.aprovada)}
