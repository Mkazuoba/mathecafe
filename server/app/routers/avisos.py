"""Avisos da biblioteca (9.11): comunicados, regras do espaço e eventos do dia
no widget à direita da tela de apps do agente. Iguais em todas as estações.

O agente não tem login: a lista dos ativos é aberta, como /api/programacao/agente."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AvisoBiblioteca
from app.security import requer_perfil
from app.websocket_manager import manager

router = APIRouter(prefix="/avisos", tags=["avisos"])


class AvisoNovo(BaseModel):
    titulo: str = Field(default="", max_length=80)
    texto: str = Field(default="", max_length=400)

    @model_validator(mode="after")
    def _nao_vazio(self):
        if not (self.titulo.strip() or self.texto.strip()):
            raise ValueError("Escreva o título ou o texto do aviso")
        return self


class AvisoAlterado(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=80)
    texto: Optional[str] = Field(default=None, max_length=400)
    ativo: Optional[bool] = None
    ordem: Optional[int] = None


def _serial(a: AvisoBiblioteca) -> dict:
    return {"id": a.id, "titulo": a.titulo or "", "texto": a.texto or "", "ativo": bool(a.ativo), "ordem": a.ordem}


def _ordenados(db: Session):
    return db.query(AvisoBiblioteca).order_by(AvisoBiblioteca.ordem, AvisoBiblioteca.id)


async def _avisar_agentes():
    await manager.broadcast_estacoes("avisos_atualizados", {})


@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [_serial(a) for a in _ordenados(db)]


@router.get("/agente")
def para_o_agente(db: Session = Depends(get_db)):
    """Só os ativos, na ordem."""
    return [_serial(a) for a in _ordenados(db).filter(AvisoBiblioteca.ativo == True)]


@router.post("/")
async def criar(body: AvisoNovo, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    ultima = db.query(func.max(AvisoBiblioteca.ordem)).scalar()
    a = AvisoBiblioteca(titulo=body.titulo.strip(), texto=body.texto.strip(), ordem=(ultima or 0) + 1)
    db.add(a)
    db.commit()
    db.refresh(a)
    await _avisar_agentes()
    return _serial(a)


@router.put("/{aviso_id}")
async def alterar(aviso_id: int, body: AvisoAlterado, db: Session = Depends(get_db),
                  _=Depends(requer_perfil("admin"))):
    a = db.get(AvisoBiblioteca, aviso_id)
    if not a:
        raise HTTPException(404, "Aviso não encontrado")
    for campo in ("titulo", "texto"):
        valor = getattr(body, campo)
        if valor is not None:
            setattr(a, campo, valor.strip())
    if body.ativo is not None:
        a.ativo = body.ativo
    if body.ordem is not None:
        a.ordem = body.ordem
    db.commit()
    await _avisar_agentes()
    return _serial(a)


@router.delete("/{aviso_id}")
async def excluir(aviso_id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    a = db.get(AvisoBiblioteca, aviso_id)
    if not a:
        raise HTTPException(404, "Aviso não encontrado")
    db.delete(a)
    db.commit()
    await _avisar_agentes()
    return {"ok": True}
