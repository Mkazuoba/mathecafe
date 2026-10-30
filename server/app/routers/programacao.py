"""Programação da biblioteca: cartazes que o agente mostra em carrossel ao
lado dos apps, durante a sessão. Iguais em todas as estações.

O agente não tem login: a lista e as imagens são abertas (são cartazes
públicos), como /api/agente/versao."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.imagens import ler_imagem
from app.models import ConfiguracaoSistema, ItemProgramacao
from app.security import requer_perfil
from app.websocket_manager import manager

router = APIRouter(prefix="/programacao", tags=["programacao"])

IMAGEM_MAX_BYTES = 4_000_000
CHAVE_SEGUNDOS = "programacao_segundos"
SEGUNDOS_PADRAO = 10


class NovoItem(BaseModel):
    titulo: str = ""
    imagem: str  # data URL (o painel reduz antes de enviar)


class EditarItem(BaseModel):
    titulo: Optional[str] = None
    ativo: Optional[bool] = None


class Ordem(BaseModel):
    ids: list[int]


class ConfigProgramacao(BaseModel):
    segundos: int = Field(ge=3, le=120)  # tempo de cada cartaz no carrossel


def _serial(i: ItemProgramacao):
    return {
        "id": i.id,
        "titulo": i.titulo,
        "ativo": i.ativo,
        "ordem": i.ordem,
        # vai na URL da imagem: o agente e o navegador não usam a antiga
        "versao": int(i.atualizado_em.timestamp()) if i.atualizado_em else 0,
    }


def _segundos(db: Session) -> int:
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE_SEGUNDOS).first()
    try:
        return int(cfg.valor) if cfg else SEGUNDOS_PADRAO
    except ValueError:
        return SEGUNDOS_PADRAO


async def _avisar_agentes():
    await manager.broadcast_estacoes("programacao_atualizada", {})


def _ordenados(db: Session):
    return db.query(ItemProgramacao).order_by(ItemProgramacao.ordem, ItemProgramacao.id)


@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return {"segundos": _segundos(db), "itens": [_serial(i) for i in _ordenados(db)]}


@router.get("/agente")
def para_o_agente(db: Session = Depends(get_db)):
    """Só os ativos, na ordem do carrossel."""
    itens = _ordenados(db).filter(ItemProgramacao.ativo == True)
    return {"segundos": _segundos(db), "itens": [_serial(i) for i in itens]}


@router.get("/{id}/imagem")
def imagem(id: int, db: Session = Depends(get_db)):
    item = db.get(ItemProgramacao, id)
    if not item:
        raise HTTPException(404, "Cartaz não encontrado")
    return Response(content=item.conteudo, media_type=item.tipo, headers={"Cache-Control": "public, max-age=86400"})


@router.post("/")
async def criar(body: NovoItem, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    tipo, dados = ler_imagem(body.imagem, IMAGEM_MAX_BYTES)
    ultimo = _ordenados(db).order_by(None).order_by(ItemProgramacao.ordem.desc()).first()
    item = ItemProgramacao(titulo=body.titulo.strip(), tipo=tipo, conteudo=dados,
                           ordem=(ultimo.ordem + 1) if ultimo else 0, atualizado_em=datetime.utcnow())
    db.add(item)
    db.commit()
    db.refresh(item)
    await _avisar_agentes()
    return _serial(item)


@router.put("/config")
async def configurar(body: ConfigProgramacao, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE_SEGUNDOS).first()
    if cfg:
        cfg.valor = str(body.segundos)
    else:
        db.add(ConfiguracaoSistema(chave=CHAVE_SEGUNDOS, valor=str(body.segundos)))
    db.commit()
    await _avisar_agentes()
    return {"segundos": body.segundos}


@router.put("/ordem")
async def reordenar(body: Ordem, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    itens = {i.id: i for i in db.query(ItemProgramacao).filter(ItemProgramacao.id.in_(body.ids))}
    for posicao, id_ in enumerate(body.ids):
        if id_ in itens:
            itens[id_].ordem = posicao
    db.commit()
    await _avisar_agentes()
    return {"ok": True}


@router.put("/{id}")
async def editar(id: int, body: EditarItem, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    item = db.get(ItemProgramacao, id)
    if not item:
        raise HTTPException(404, "Cartaz não encontrado")
    if body.titulo is not None:
        item.titulo = body.titulo.strip()
    if body.ativo is not None:
        item.ativo = body.ativo
    db.commit()
    await _avisar_agentes()
    return _serial(item)


@router.delete("/{id}")
async def apagar(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    item = db.get(ItemProgramacao, id)
    if not item:
        raise HTTPException(404, "Cartaz não encontrado")
    db.delete(item)
    db.commit()
    await _avisar_agentes()
    return {"ok": True}
