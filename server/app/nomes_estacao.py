"""Mapas separados por piso (6.18): o nome da estacao e unico so dentro do piso.

AD-01 pode existir no Adulto e no Infantil; o que identifica a estacao e o id
(no painel, nas conexoes e nos comandos). Quem so tem o nome (agente antigo,
chamada antiga da API) acha a estacao quando ela e a unica com esse nome, ou
informando o piso.
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Estacao, GrupoEstacao
from app.pisos import piso_da_estacao, piso_padrao


def piso_id_de(e: Estacao) -> Optional[int]:
    """O piso da estacao: o do grupo; sem grupo, o guardado nela; senao o padrao."""
    p = piso_da_estacao(e)
    return p.id if p else None


def piso_id_do_grupo(db: Session, grupo_id: Optional[int]) -> Optional[int]:
    """O piso em que fica uma estacao posta neste grupo (sem grupo: o padrao)."""
    g = db.get(GrupoEstacao, grupo_id) if grupo_id else None
    if g is not None and g.piso_id is not None:
        return g.piso_id
    p = piso_padrao(db)
    return p.id if p else None


def com_o_nome(db: Session, nome: str, piso_id: Optional[int] = None, ativas: bool = True) -> List[Estacao]:
    q = db.query(Estacao).filter(Estacao.nome == nome)
    if ativas:
        q = q.filter(Estacao.ativa == True)
    lista = q.order_by(Estacao.id).all()
    if piso_id is not None:
        lista = [e for e in lista if piso_id_de(e) == piso_id]
    return lista


def ocupado_no_piso(db: Session, nome: str, piso_id: Optional[int], ignorar_id: Optional[int] = None) -> Optional[Estacao]:
    """Outra estacao ativa com esse nome no mesmo piso (ou None)."""
    return next((e for e in com_o_nome(db, nome, piso_id) if e.id != ignorar_id), None)


def exigir_nome_livre(db: Session, nome: str, piso_id: Optional[int], ignorar_id: Optional[int] = None):
    if ocupado_no_piso(db, nome, piso_id, ignorar_id):
        raise HTTPException(400, f"Já existe a estação {nome} neste piso")


def achar_estacao(db: Session, nome: str, estacao_id: Optional[int] = None,
                  piso_id: Optional[int] = None) -> Estacao:
    """A estacao ativa de uma rota /{nome}/...: pelo id quando vem (o painel
    sempre manda); so pelo nome, precisa ser a unica com ele (ou dizer o piso)."""
    if estacao_id is not None:
        e = db.query(Estacao).filter(Estacao.id == estacao_id, Estacao.ativa == True).first()
        if not e:
            raise HTTPException(404, "Estação não encontrada")
        return e
    lista = com_o_nome(db, nome, piso_id)
    if not lista:
        raise HTTPException(404, "Estação não encontrada")
    if len(lista) > 1:
        raise HTTPException(409, f"Há {len(lista)} estações {nome} (uma em cada piso): informe qual")
    return lista[0]
