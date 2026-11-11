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


def estacao_do_agente(db: Session, nome: str, identificador: Optional[str],
                      piso_id: Optional[int] = None) -> Tuple[Optional[Estacao], bool]:
    """A estacao deste agente: (estacao, nova_pendente). (None, False) = recusar a
    conexao (agente antigo com nome desconhecido, ou PC recusado no painel)."""
    identificador = (identificador or "").strip()[:64] or None
    nome = (nome or "").strip()

    if identificador:
        e = db.query(Estacao).filter(Estacao.identificador == identificador).first()
        if e:
            if e.ativa:
                _nome_vindo_do_pc(db, e, nome)
                return e, False
            if not e.aprovada:
                return None, False  # recusada em "Novas estacoes"
            # excluida no painel e o agente continua instalado: volta para aprovar
            e.ativa, e.aprovada, e.grupo_id = True, False, None
            db.commit()
            return e, True

    from app.models import Piso
    if piso_id is not None and db.get(Piso, piso_id) is None:
        piso_id = None  # piso que nao existe (apagado depois da instalacao): como sem piso
    if identificador and piso_id is not None:
        # agente 1.20: o instalador escolheu o piso. A estacao com esse nome no
        # piso, ainda sem PC, e dele (o admin ja montou o mapa); senao espera
        # em Novas estacoes, ja no piso (6.18)
        from app.nomes_estacao import com_o_nome
        vaga = next((x for x in com_o_nome(db, nome, piso_id) if not x.identificador), None)
        if vaga:
            vaga.identificador = identificador
            db.commit()
            return vaga, False
        e = Estacao(nome=nome_livre_no_piso(db, nome, piso_id), identificador=identificador,
                    aprovada=False, status="livre", piso_id=piso_id)
        db.add(e)
        db.commit()
        db.refresh(e)
        return e, True

    e = _pelo_nome(db, nome, identificador)
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


def nome_livre_no_piso(db: Session, desejado: str, piso_id: Optional[int], ignorar_id: Optional[int] = None) -> str:
    """O nome pedido, ou com -2, -3... se outra estacao ativa do piso ja o usa."""
    from app.nomes_estacao import ocupado_no_piso
    base = (desejado or "").strip()[:TAMANHO_NOME] or "PC"
    nome, n = base, 2
    while ocupado_no_piso(db, nome, piso_id, ignorar_id):
        sufixo = f"-{n}"
        nome = base[:TAMANHO_NOME - len(sufixo)] + sufixo
        n += 1
    return nome


def _pelo_nome(db: Session, nome: str, identificador: Optional[str]) -> Optional[Estacao]:
    """A estacao ativa com o nome, quando da para saber qual (6.18: o nome pode
    estar nos dois pisos). Agente 1.14 (com id): so as que ainda nao tem PC; com
    duas candidatas fica pendente (o admin escolhe em "Substitui a X"). Agente
    antigo (sem id): a do piso padrao, senao a primeira."""
    lista = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).order_by(Estacao.id).all()
    if identificador:
        livres = [e for e in lista if not e.identificador]
        if len(livres) > 1:
            return None
        return livres[0] if livres else (lista[0] if lista else None)
    if len(lista) > 1:
        from app.pisos import piso_da_estacao, piso_padrao
        padrao = piso_padrao(db)
        return next((e for e in lista if padrao and piso_da_estacao(e) == padrao), lista[0])
    return lista[0] if lista else None


def _nome_vindo_do_pc(db: Session, e: Estacao, nome: str):
    """O agente conectou com outro nome (trocado no PC, em Configurar conexao).
    Pendente: e so o nome que ela vai ter na aprovacao. Aprovada: vira um
    pedido de troca para o admin aceitar (o agente recebe o nome atual de
    volta em estacao_info e segue com ele)."""
    nome = (nome or "").strip()[:TAMANHO_NOME]
    if not nome or nome == e.nome:
        return
    if not e.aprovada:
        e.nome = nome_livre(db, nome, ignorar_id=e.id)
    elif e.nome_pedido != nome:
        e.nome_pedido = nome
    else:
        return
    db.commit()


def info_para_o_agente(e: Estacao) -> dict:
    return {"nome": e.nome, "aprovada": bool(e.aprovada)}
