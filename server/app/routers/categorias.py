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


# a cor que cada categoria nova ganha, em ordem (o admin troca no painel)
CORES = ["#8b5cf6", "#3b82f6", "#22c55e", "#f59e0b", "#f43f5e", "#06b6d4", "#ec4899", "#84cc16"]
COR = r"^#[0-9a-fA-F]{6}$"


def cor_da_categoria(c) -> str:
    """Categoria de antes da 9.11 (sem cor gravada) ganha uma da paleta pelo id."""
    return c.cor or CORES[(c.id or 0) % len(CORES)]


class CategoriaNova(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    cor: Optional[str] = Field(default=None, pattern=COR)


class CategoriaAlterada(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=40)
    ordem: Optional[int] = None
    cor: Optional[str] = Field(default=None, pattern=COR)


def serial(db: Session, c: CategoriaApp) -> dict:
    return {
        "id": c.id,
        "nome": c.nome,
        "ordem": c.ordem,
        "cor": cor_da_categoria(c),
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
    cor = (data.cor or CORES[db.query(CategoriaApp).count() % len(CORES)]).lower()
    c = CategoriaApp(nome=data.nome.strip(), ordem=(ultima or 0) + 1, cor=cor)
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
    if data.cor is not None:
        c.cor = data.cor.lower()
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
