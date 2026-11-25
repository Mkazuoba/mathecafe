"""Avisos da biblioteca (9.11): comunicados, regras do espaço e eventos do dia
no widget à direita da tela de apps do agente. Iguais em todas as estações.

O agente não tem login: a lista dos ativos é aberta, como /api/programacao/agente."""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AvisoBiblioteca
from app.security import requer_perfil
from app.permissoes import requer_permissao
from app.websocket_manager import manager

router = APIRouter(prefix="/avisos", tags=["avisos"])


Tipo = Literal["alerta", "evento", "info"]


class AvisoNovo(BaseModel):
    titulo: str = Field(default="", max_length=80)
    texto: str = Field(default="", max_length=400)
    tipo: Tipo = "info"
    horario: Optional[str] = Field(default=None, max_length=20)
    mostrar_de: Optional[str] = None  # "AAAA-MM-DDTHH:MM" (Brasilia)
    mostrar_ate: Optional[str] = None

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
    tipo: Optional[Tipo] = None
    horario: Optional[str] = Field(default=None, max_length=20)  # "" apaga
    mostrar_de: Optional[str] = None  # "" apaga
    mostrar_ate: Optional[str] = None


def _agora() -> datetime:
    """Agora em Brasilia, sem fuso (como mostrar_de/mostrar_ate sao gravados)."""
    from app.routers.config import _agora_br
    return _agora_br()


def situacao(a: AvisoBiblioteca, agora: datetime) -> str:
    """desligado, agendado (ainda nao comecou), encerrado (ja passou) ou no_ar."""
    if not a.ativo:
        return "desligado"
    if a.mostrar_de and agora < a.mostrar_de:
        return "agendado"
    if a.mostrar_ate and agora >= a.mostrar_ate:
        return "encerrado"
    return "no_ar"


def _data(texto: Optional[str]) -> Optional[datetime]:
    if not texto or not texto.strip():
        return None
    try:
        return datetime.fromisoformat(texto.strip()).replace(tzinfo=None, second=0, microsecond=0)
    except ValueError:
        raise HTTPException(400, "Data inválida (use dia e hora)")


def _fmt(d: Optional[datetime]) -> Optional[str]:
    return d.strftime("%Y-%m-%dT%H:%M") if d else None


def _conferir_periodo(a: AvisoBiblioteca):
    if a.mostrar_de and a.mostrar_ate and a.mostrar_ate <= a.mostrar_de:
        raise HTTPException(400, "O fim tem de ser depois do início")


def _serial(a: AvisoBiblioteca, agora: Optional[datetime] = None) -> dict:
    return {"id": a.id, "titulo": a.titulo or "", "texto": a.texto or "", "ativo": bool(a.ativo), "ordem": a.ordem,
            "tipo": a.tipo or "info", "horario": a.horario or None,
            "mostrar_de": _fmt(a.mostrar_de), "mostrar_ate": _fmt(a.mostrar_ate),
            "situacao": situacao(a, agora or _agora())}


def _no_ar(db: Session, agora: datetime) -> list:
    return [a for a in _ordenados(db).filter(AvisoBiblioteca.ativo == True) if situacao(a, agora) == "no_ar"]


_aparecendo = None  # ids que o batimento viu no ar da ultima vez


def mudou_o_que_aparece(db: Session, agora: datetime) -> bool:
    """O batimento (a cada minuto) pergunta: algum aviso entrou ou saiu do ar
    pelo periodo? Se sim, os agentes recarregam. A primeira vez so guarda."""
    global _aparecendo
    ids = frozenset(a.id for a in _no_ar(db, agora))
    antes, _aparecendo = _aparecendo, ids
    return antes is not None and antes != ids


def _ordenados(db: Session):
    return db.query(AvisoBiblioteca).order_by(AvisoBiblioteca.ordem, AvisoBiblioteca.id)


async def _avisar_agentes():
    await manager.broadcast_estacoes("avisos_atualizados", {})


@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [_serial(a) for a in _ordenados(db)]


@router.get("/agente")
def para_o_agente(db: Session = Depends(get_db)):
    """Só os ativos dentro do período (9.19), na ordem."""
    agora = _agora()
    return [_serial(a, agora) for a in _no_ar(db, agora)]


@router.post("/")
async def criar(body: AvisoNovo, db: Session = Depends(get_db), _=Depends(requer_permissao("divulgacao"))):
    ultima = db.query(func.max(AvisoBiblioteca.ordem)).scalar()
    a = AvisoBiblioteca(titulo=body.titulo.strip(), texto=body.texto.strip(), ordem=(ultima or 0) + 1,
                        tipo=body.tipo, horario=(body.horario or "").strip() or None,
                        mostrar_de=_data(body.mostrar_de), mostrar_ate=_data(body.mostrar_ate))
    _conferir_periodo(a)
    db.add(a)
    db.commit()
    db.refresh(a)
    await _avisar_agentes()
    return _serial(a)


@router.put("/{aviso_id}")
async def alterar(aviso_id: int, body: AvisoAlterado, db: Session = Depends(get_db),
                  _=Depends(requer_permissao("divulgacao"))):
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
    if body.tipo is not None:
        a.tipo = body.tipo
    if body.horario is not None:
        a.horario = body.horario.strip() or None
    if body.mostrar_de is not None:
        a.mostrar_de = _data(body.mostrar_de)
    if body.mostrar_ate is not None:
        a.mostrar_ate = _data(body.mostrar_ate)
    _conferir_periodo(a)
    db.commit()
    await _avisar_agentes()
    return _serial(a)


@router.delete("/{aviso_id}")
async def excluir(aviso_id: int, db: Session = Depends(get_db), _=Depends(requer_permissao("divulgacao"))):
    a = db.get(AvisoBiblioteca, aviso_id)
    if not a:
        raise HTTPException(404, "Aviso não encontrado")
    db.delete(a)
    db.commit()
    await _avisar_agentes()
    return {"ok": True}
