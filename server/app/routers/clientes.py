from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime, time as dt_time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from app.database import _eh_sqlite, get_db, sem_acento
from app.imagens import ler_imagem
from app.tempo_diario import cota_diaria, hoje_br, saldo_do_dia, saldo_do_dia_sql
from app.models import FotoCliente, Usuario, Sessao
from app.security import hash_senha, requer_perfil

router = APIRouter(prefix="/clientes", tags=["clientes"])

class ClienteCreate(BaseModel):
    login: str
    nome: str
    senha: str
    observacao: Optional[str] = None
    documento: Optional[str] = None
    data_nascimento: Optional[date] = None

class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    senha: Optional[str] = None
    ativo: Optional[bool] = None
    observacao: Optional[str] = None
    saldo_segundos: Optional[int] = None
    # documento e nascimento: o que vier (mesmo vazio/null) substitui; o que nao vier fica
    documento: Optional[str] = None
    data_nascimento: Optional[date] = None

class FotoBody(BaseModel):
    imagem: str  # data URL (o painel reduz a imagem antes de enviar)

FOTO_MAX_BYTES = 2_000_000

def _uso_hoje(db: Session, cliente_id: int) -> int:
    """Retorna segundos consumidos hoje (fuso Brasil UTC-3) em sessoes encerradas."""
    tz_br = ZoneInfo("America/Sao_Paulo")
    hoje_br = datetime.now(tz=tz_br).date()
    inicio_hoje_utc = (
        datetime.combine(hoje_br, dt_time.min)
        .replace(tzinfo=tz_br)
        .astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
    )
    total = db.query(func.sum(Sessao.tempo_consumido_segundos)).filter(
        Sessao.cliente_id == cliente_id,
        Sessao.iniciada_em >= inicio_hoje_utc,
        Sessao.encerrada_em != None
    ).scalar() or 0
    return int(total)


def serializar(u: Usuario, db: Session = None, cota: Optional[int] = None):
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "ativo": u.ativo,
        "saldo_segundos": saldo_do_dia(u, cota),  # tempo que ainda pode usar hoje
        "observacao": u.observacao,
        "documento": u.documento,
        "data_nascimento": u.data_nascimento.isoformat() if u.data_nascimento else None,
        "tem_foto": u.foto_em is not None,
        "foto_em": u.foto_em.isoformat() if u.foto_em else None,
        "criado_em": u.criado_em.isoformat() if u.criado_em else None,
        "na_fila": u.autorizacao is not None and not u.autorizacao.usado,
        "uso_hoje_segundos": _uso_hoje(db, u.id) if db is not None else 0,
    }

ORDENS = {"nome": Usuario.nome, "login": Usuario.login, "criado": Usuario.criado_em}


def _filtro_texto(q: str, campo: str, modo: str):
    colunas = {"nome": [Usuario.nome], "login": [Usuario.login]}.get(campo, [Usuario.nome, Usuario.login])
    # sem acento e em minusculas dos dois lados: "jose" acha "José"
    if _eh_sqlite:
        colunas = [func.sem_acento(col) for col in colunas]
        q = sem_acento(q)
    else:
        colunas = [func.lower(col) for col in colunas]
        q = q.lower()
    if modo == "exato":
        return or_(*[col == q for col in colunas])
    if modo == "comeca":
        return or_(*[col.like(f"{q}%") for col in colunas])
    # contem: cada palavra em qualquer lugar ("maria silva" acha "Maria Jose da Silva")
    return and_(*[or_(*[col.like(f"%{p}%") for col in colunas]) for p in q.split()])


@router.get("/")
def listar(
    busca: str = Query(default="", alias="busca"),
    campo: Literal["tudo", "nome", "login"] = "tudo",
    modo: Literal["contem", "comeca", "exato"] = "contem",
    status: Literal["todos", "ativos", "inativos"] = "todos",
    saldo: Literal["todos", "com", "sem"] = "todos",
    ordem: Literal["nome", "login", "saldo", "criado"] = "nome",
    desc: bool = False,
    tudo: bool = False,
    limite: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(requer_perfil("admin", "operador"))
):
    """Busca server-side (são ~43k clientes). Sem termo devolve lista vazia,
    a não ser com tudo=true (aba Clientes, que lista pela ordem escolhida)."""
    q = busca.strip()
    if not q and not tudo:
        return []
    consulta = db.query(Usuario).filter(Usuario.perfil == "cliente")
    if q:
        consulta = consulta.filter(_filtro_texto(q, campo, modo))
    if status != "todos":
        consulta = consulta.filter(Usuario.ativo == (status == "ativos"))
    cota = cota_diaria(db)
    saldo_hoje = saldo_do_dia_sql(cota)
    if saldo == "com":
        consulta = consulta.filter(saldo_hoje > 0)
    elif saldo == "sem":
        consulta = consulta.filter(saldo_hoje <= 0)
    coluna = saldo_hoje if ordem == "saldo" else ORDENS[ordem]
    consulta = consulta.order_by(coluna.desc() if desc else coluna, Usuario.nome)
    return [serializar(c, db, cota) for c in consulta.limit(limite).all()]

@router.post("/")
def criar(data: ClienteCreate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    if db.query(Usuario).filter(Usuario.login == data.login).first():
        raise HTTPException(status_code=400, detail="Login já existe")
    cliente = Usuario(
        login=data.login, nome=data.nome,
        senha_hash=hash_senha(data.senha),
        perfil="cliente", observacao=data.observacao,
        documento=(data.documento or "").strip() or None, data_nascimento=data.data_nascimento,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return serializar(cliente, db)

@router.put("/{id}")
def atualizar(id: int, data: ClienteUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if data.nome: cliente.nome = data.nome
    if data.senha: cliente.senha_hash = hash_senha(data.senha)
    if data.ativo is not None: cliente.ativo = data.ativo
    if data.observacao is not None: cliente.observacao = data.observacao
    if "documento" in data.model_fields_set: cliente.documento = (data.documento or "").strip() or None
    if "data_nascimento" in data.model_fields_set: cliente.data_nascimento = data.data_nascimento
    if data.saldo_segundos is not None:
        # vale para hoje: e assim que o operador da tempo extra
        cliente.saldo_segundos = data.saldo_segundos
        cliente.saldo_dia = hoje_br()
    db.commit()
    return serializar(cliente, db)

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Quem já usou os computadores fica no histórico de sessões (e nos relatórios)
    if db.query(Sessao).filter(Sessao.cliente_id == id).first():
        raise HTTPException(status_code=409,
                            detail="Cliente tem histórico de uso. Desative-o em vez de excluir.")
    if cliente.autorizacao:
        db.delete(cliente.autorizacao)
    db.query(FotoCliente).filter(FotoCliente.cliente_id == id).delete()
    db.delete(cliente)
    db.commit()
    return {"ok": True}

@router.get("/{id}")
def obter(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return serializar(cliente, db)


# ── Foto ──────────────────────────────────────────────────────────────────────

def _cliente_ou_404(db: Session, id: int) -> Usuario:
    cliente = db.query(Usuario).filter(Usuario.id == id, Usuario.perfil == "cliente").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente

@router.get("/{id}/foto")
def obter_foto(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    foto = db.get(FotoCliente, id)
    if not foto:
        raise HTTPException(status_code=404, detail="Cliente sem foto")
    return Response(content=foto.conteudo, media_type=foto.tipo, headers={"Cache-Control": "private, max-age=86400"})

@router.put("/{id}/foto")
def salvar_foto(id: int, body: FotoBody, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = _cliente_ou_404(db, id)
    tipo, dados = ler_imagem(body.imagem, FOTO_MAX_BYTES)
    foto = db.get(FotoCliente, id) or FotoCliente(cliente_id=id)
    foto.tipo, foto.conteudo = tipo, dados
    db.add(foto)
    cliente.foto_em = datetime.utcnow()
    db.commit()
    return serializar(cliente, db)

@router.delete("/{id}/foto")
def remover_foto(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    cliente = _cliente_ou_404(db, id)
    db.query(FotoCliente).filter(FotoCliente.cliente_id == id).delete()
    cliente.foto_em = None
    db.commit()
    return serializar(cliente, db)
