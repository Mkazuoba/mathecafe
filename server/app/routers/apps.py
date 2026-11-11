from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from app.database import get_db
from app.models import AppPermitido, AppPiso, CategoriaApp, GrupoEstacao, Piso
from app.pisos import piso_padrao
from app.security import requer_perfil

router = APIRouter(prefix="/apps", tags=["apps"])

class AppCreate(BaseModel):
    nome: str
    processo: str
    caminho: Optional[str] = None
    grupo_id: Optional[int] = None  # antigo: ignorado
    imagem_url: Optional[str] = None
    piso_id: Optional[int] = None  # nasce ligado neste piso (vazio: o padrao)
    categoria_id: Optional[int] = None
    descricao: Optional[str] = Field(default=None, max_length=120)

class AppUpdate(BaseModel):
    nome: Optional[str] = None
    processo: Optional[str] = None
    caminho: Optional[str] = None
    ativo: Optional[bool] = None
    imagem_url: Optional[str] = None
    # mapa (grupo): o que vier substitui (null = todos os mapas); o que nao vier fica
    grupo_id: Optional[int] = None
    # categoria: o que vier substitui (null = sem categoria); o que nao vier fica
    categoria_id: Optional[int] = None
    descricao: Optional[str] = Field(default=None, max_length=120)  # "" apaga

def validar_caminho(caminho: Optional[str]) -> Optional[str]:
    """O agente executa o caminho diretamente: precisa ser o arquivo .exe."""
    caminho = (caminho or "").strip().strip('"')
    if caminho and not caminho.lower().endswith(".exe"):
        raise HTTPException(400, "O caminho precisa ser o arquivo .exe, não a pasta. "
                                 r"Ex.: C:\Program Files\Google\Chrome\Application\chrome.exe")
    return caminho or None

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
        "categoria_id": a.categoria_id,
        "descricao": a.descricao,
        "categoria_nome": a.categoria.nome if a.categoria else None,
        # pisos em que o app esta ligado
        "pisos": sorted(p.piso_id for p in a.pisos_ligados),
    }


class PisoLigado(BaseModel):
    ligado: bool

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [serial(a) for a in db.query(AppPermitido).order_by(AppPermitido.nome).all()]

@router.post("/")
def criar(data: AppCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    processo = data.processo.strip().lower()
    if not processo.endswith(".exe"):
        processo += ".exe"

    piso = db.get(Piso, data.piso_id) if data.piso_id is not None else piso_padrao(db)
    if piso is None:
        raise HTTPException(404, "Piso não encontrado")
    if db.query(AppPermitido).filter(AppPermitido.processo == processo).first():
        raise HTTPException(400, "Esse app já está cadastrado: ligue-o no interruptor do piso")
    if data.categoria_id is not None and not db.get(CategoriaApp, data.categoria_id):
        raise HTTPException(404, "Categoria não encontrada")

    app_p = AppPermitido(
        nome=data.nome.strip(), processo=processo,
        caminho=validar_caminho(data.caminho),
        imagem_url=data.imagem_url.strip() if data.imagem_url else None,
        categoria_id=data.categoria_id,
        descricao=(data.descricao or "").strip() or None,
    )
    app_p.pisos_ligados.append(AppPiso(piso_id=piso.id))
    db.add(app_p); db.commit(); db.refresh(app_p)
    return serial(app_p)


@router.put("/{id}/pisos/{piso_id}")
def ligar_no_piso(id: int, piso_id: int, data: PisoLigado, db: Session = Depends(get_db),
                  _=Depends(requer_perfil("admin"))):
    """Liga ou desliga o app num piso (o interruptor do cartao)."""
    app_p = db.get(AppPermitido, id)
    if not app_p:
        raise HTTPException(404, "App não encontrado")
    if not db.get(Piso, piso_id):
        raise HTTPException(404, "Piso não encontrado")
    linha = db.get(AppPiso, (id, piso_id))
    if data.ligado and not linha:
        db.add(AppPiso(app_id=id, piso_id=piso_id))
    elif not data.ligado and linha:
        db.delete(linha)
    db.commit()
    db.refresh(app_p)
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
        app_p.caminho = validar_caminho(data.caminho)
    if data.imagem_url is not None:
        app_p.imagem_url = data.imagem_url.strip() or None
    if data.descricao is not None:
        app_p.descricao = data.descricao.strip() or None
    if data.ativo is not None: app_p.ativo = data.ativo
    if "grupo_id" in data.model_fields_set:
        if data.grupo_id is not None and not db.query(GrupoEstacao).filter(GrupoEstacao.id == data.grupo_id).first():
            raise HTTPException(404, "Grupo não encontrado")
        app_p.grupo_id = data.grupo_id
    if "categoria_id" in data.model_fields_set:
        if data.categoria_id is not None and not db.get(CategoriaApp, data.categoria_id):
            raise HTTPException(404, "Categoria não encontrada")
        app_p.categoria_id = data.categoria_id
    db.commit()
    db.refresh(app_p)
    return serial(app_p)

@router.delete("/{id}")
def remover(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    app_p = db.query(AppPermitido).filter(AppPermitido.id == id).first()
    if not app_p:
        raise HTTPException(404, "App não encontrado")
    db.delete(app_p); db.commit()
    return {"ok": True}
