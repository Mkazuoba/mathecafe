from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppPiso, GrupoEstacao, Piso, Usuario
from app.security import requer_perfil

router = APIRouter(prefix="/pisos", tags=["pisos"])

COR = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class PisoNovo(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    cor: str = COR


class PisoAlterado(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=40)
    cor: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    padrao: Optional[bool] = None  # so True: o padrao muda passando para outro piso


def serial(db: Session, p: Piso) -> dict:
    return {
        "id": p.id,
        "nome": p.nome,
        "cor": p.cor,
        "padrao": bool(p.padrao),
        "grupos": db.query(GrupoEstacao).filter(GrupoEstacao.piso_id == p.id, GrupoEstacao.ativo == True).count(),
        "clientes": db.query(Usuario).filter(Usuario.piso_id == p.id, Usuario.perfil == "cliente").count(),
    }


def _nome_livre(db: Session, nome: str, exceto: Optional[int] = None):
    q = db.query(Piso).filter(func.lower(Piso.nome) == nome.strip().lower())
    if exceto is not None:
        q = q.filter(Piso.id != exceto)
    if q.first():
        raise HTTPException(400, "Já existe um piso com esse nome")


@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [serial(db, p) for p in db.query(Piso).order_by(Piso.id)]


@router.post("/")
def criar(data: PisoNovo, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    _nome_livre(db, data.nome)
    p = Piso(nome=data.nome.strip(), cor=data.cor, padrao=db.query(Piso).count() == 0)
    db.add(p)
    db.commit()
    return serial(db, p)


@router.put("/{piso_id}")
def alterar(piso_id: int, data: PisoAlterado, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    p = db.get(Piso, piso_id)
    if not p:
        raise HTTPException(404, "Piso não encontrado")
    if data.nome is not None:
        _nome_livre(db, data.nome, exceto=p.id)
        p.nome = data.nome.strip()
    if data.cor is not None:
        p.cor = data.cor
    if data.padrao:
        db.query(Piso).filter(Piso.id != p.id).update({Piso.padrao: False})
        p.padrao = True
    db.commit()
    return serial(db, p)


@router.delete("/{piso_id}")
def excluir(piso_id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    p = db.get(Piso, piso_id)
    if not p:
        raise HTTPException(404, "Piso não encontrado")
    if p.padrao:
        raise HTTPException(400, "Este é o piso padrão. Escolha outro como padrão antes de excluir.")
    uso = serial(db, p)
    if uso["clientes"] or uso["grupos"]:
        raise HTTPException(400, f"O piso tem {uso['clientes']} cliente(s) e {uso['grupos']} mapa(s). "
                                 "Passe-os para outro piso antes de excluir.")
    db.query(AppPiso).filter(AppPiso.piso_id == p.id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}
