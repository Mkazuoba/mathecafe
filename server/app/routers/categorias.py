"""Categorias dos apps (Configurações → Apps): filtram a tela de apps do agente."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppPermitido, CategoriaApp
from app.security import requer_perfil

router = APIRouter(prefix="/categorias", tags=["categorias"])


class CategoriaNova(BaseModel):
    nome: str = Field(min_length=1, max_length=40)


class CategoriaAlterada(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=40)
    ordem: Optional[int] = None


def serial(db: Session, c: CategoriaApp) -> dict:
    return {
        "id": c.id,
        "nome": c.nome,
        "ordem": c.ordem,
        "apps": db.query(AppPermitido).filter(AppPermitido.categoria_id == c.id).count(),
    }


def _nome_livre(db: Session, nome: str, exceto: Optional[int] = None):
    q = db.query(CategoriaApp).filter(func.lower(CategoriaApp.nome) == nome.strip().lower())
    if exceto is not None:
        q = q.filter(CategoriaApp.id != exceto)
    if q.first():
        raise HTTPException(400, "Já existe uma categoria com esse nome")


@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [serial(db, c) for c in db.query(CategoriaApp).order_by(CategoriaApp.ordem, CategoriaApp.nome)]


@router.post("/")
def criar(data: CategoriaNova, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    _nome_livre(db, data.nome)
    ultima = db.query(func.max(CategoriaApp.ordem)).scalar()
    c = CategoriaApp(nome=data.nome.strip(), ordem=(ultima or 0) + 1)
    db.add(c)
    db.commit()
    return serial(db, c)


@router.put("/{categoria_id}")
def alterar(categoria_id: int, data: CategoriaAlterada, db: Session = Depends(get_db),
            _=Depends(requer_perfil("admin"))):
    c = db.get(CategoriaApp, categoria_id)
    if not c:
        raise HTTPException(404, "Categoria não encontrada")
    if data.nome is not None:
        _nome_livre(db, data.nome, exceto=c.id)
        c.nome = data.nome.strip()
    if data.ordem is not None:
        c.ordem = data.ordem
    db.commit()
    return serial(db, c)


@router.delete("/{categoria_id}")
def excluir(categoria_id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    """Os apps dela ficam sem categoria (no agente, em "Outros")."""
    c = db.get(CategoriaApp, categoria_id)
    if not c:
        raise HTTPException(404, "Categoria não encontrada")
    db.query(AppPermitido).filter(AppPermitido.categoria_id == c.id).update({AppPermitido.categoria_id: None})
    db.delete(c)
    db.commit()
    return {"ok": True}
