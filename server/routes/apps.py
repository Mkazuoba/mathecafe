from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import AppPermitido, GrupoEstacao
from auth import requer_perfil

router = APIRouter(prefix="/apps", tags=["apps"])

class AppCreate(BaseModel):
    nome: str
    processo: str
    caminho: Optional[str] = None
    grupo_id: Optional[int] = None
    imagem_url: Optional[str] = None

class AppUpdate(BaseModel):
    nome: Optional[str] = None
    processo: Optional[str] = None
    caminho: Optional[str] = None
    ativo: Optional[bool] = None
    imagem_url: Optional[str] = None

def serial(a: AppPermitido):
    return {
        "id": a.id,
        "nome": a.nome,
        "processo": a.processo,
        "caminho": a.caminho,
        "imagem_url": a.imagem_url,
        "grupo_id": a.grupo_id,
        "grupo_nome": a.grupo.nome if a.grupo else "Todos os grupos",
        "ativo": a.ativo,
    }

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [serial(a) for a in db.query(AppPermitido).order_by(AppPermitido.nome).all()]

@router.post("/")
def criar(data: AppCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    processo = data.processo.strip().lower()
    if not processo.endswith(".exe"):
        processo += ".exe"

    if data.grupo_id is not None:
        if not db.query(GrupoEstacao).filter(GrupoEstacao.id == data.grupo_id).first():
            raise HTTPException(404, "Grupo não encontrado")

    if db.query(AppPermitido).filter(
        AppPermitido.processo == processo,
        AppPermitido.grupo_id == data.grupo_id
    ).first():
        raise HTTPException(400, "Esse app já está na whitelist para esse grupo")

    app_p = AppPermitido(
        nome=data.nome.strip(), processo=processo,
        caminho=data.caminho.strip() if data.caminho else None,
        grupo_id=data.grupo_id,
        imagem_url=data.imagem_url.strip() if data.imagem_url else None
    )
    db.add(app_p); db.commit(); db.refresh(app_p)
    return serial(app_p)

@router.put("/{id}")
def atualizar(id: int, data: AppUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    app_p = db.query(AppPermitido).filter(AppPermitido.id == id).first()
    if not app_p:
        raise HTTPException(404, "App não encontrado")
    if data.nome: app_p.nome = data.nome.strip()
    if data.processo:
        p = data.processo.strip().lower()
        app_p.processo = p if p.endswith(".exe") else p + ".exe"
    if data.caminho is not None:
        app_p.caminho = data.caminho.strip() or None
    if data.imagem_url is not None:
        app_p.imagem_url = data.imagem_url.strip() or None
    if data.ativo is not None: app_p.ativo = data.ativo
    db.commit()
    return serial(app_p)

@router.delete("/{id}")
def remover(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    app_p = db.query(AppPermitido).filter(AppPermitido.id == id).first()
    if not app_p:
        raise HTTPException(404, "App não encontrado")
    db.delete(app_p); db.commit()
    return {"ok": True}
