from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.models import Usuario, Autorizacao, GrupoOperadores, Piso
from app.security import hash_senha, requer_perfil
from app.registro import registrar
from app.permissoes import PERMISSOES, ler as ler_permissoes, ler_pisos, requer_permissao

router = APIRouter(prefix="/operadores", tags=["operadores"])

class OperadorCreate(BaseModel):
    login: str
    nome: str
    senha: str
    perfil: Optional[str] = "operador"
    grupo_id: Optional[int] = None

class OperadorUpdate(BaseModel):
    nome: Optional[str] = None
    senha: Optional[str] = None
    ativo: Optional[bool] = None
    perfil: Optional[str] = None
    grupo_id: Optional[int] = None  # 0 tira do grupo

class GrupoBody(BaseModel):
    nome: str
    permissoes: List[str] = []
    pisos: List[int] = []  # vazio = todos os pisos

def serializar(u: Usuario):
    return {
        "id": u.id,
        "login": u.login,
        "nome": u.nome,
        "ativo": u.ativo,
        "perfil": u.perfil,
        "grupo_id": u.grupo_operadores_id,
        "criado_em": u.criado_em.isoformat() if u.criado_em else None,
    }

# ── Grupos de operadores (app/permissoes.py) ──────────────────────────────
@router.get("/permissoes")
def permissoes(_=Depends(requer_perfil("admin"))):
    return [{"chave": k, "rotulo": v} for k, v in PERMISSOES.items()]

def _grupo_serial(db: Session, g: GrupoOperadores):
    return {"id": g.id, "nome": g.nome, "permissoes": ler_permissoes(g.permissoes),
            "pisos": ler_pisos(g.pisos),
            "operadores": db.query(Usuario).filter(Usuario.grupo_operadores_id == g.id).count()}

def _validar_grupo(db: Session, body: GrupoBody, id_atual=None) -> str:
    nome = body.nome.strip()
    if not nome or len(nome) > 40:
        raise HTTPException(status_code=400, detail="Dê um nome ao grupo (até 40 letras)")
    invalidas = [p for p in body.permissoes if p not in PERMISSOES]
    if invalidas:
        raise HTTPException(status_code=400, detail=f"Permissão desconhecida: {', '.join(invalidas)}")
    if any(db.get(Piso, p) is None for p in body.pisos):
        raise HTTPException(status_code=400, detail="Piso não encontrado")
    for g in db.query(GrupoOperadores).all():
        if g.nome.lower() == nome.lower() and g.id != id_atual:
            raise HTTPException(status_code=400, detail="Já existe um grupo com esse nome")
    return nome

@router.get("/grupos")
def listar_grupos(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    return [_grupo_serial(db, g) for g in db.query(GrupoOperadores).order_by(GrupoOperadores.nome)]

@router.post("/grupos")
def criar_grupo(body: GrupoBody, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    g = GrupoOperadores(nome=_validar_grupo(db, body),
                        permissoes=",".join(p for p in PERMISSOES if p in body.permissoes),
                        pisos=",".join(str(p) for p in sorted(set(body.pisos))))
    db.add(g)
    db.commit()
    registrar(db, quem, "criar_grupo_operadores", detalhe=f"{g.nome}: {_rotulos(db, g)}")
    return _grupo_serial(db, g)

@router.put("/grupos/{id}")
def editar_grupo(id: int, body: GrupoBody, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    g = db.get(GrupoOperadores, id)
    if not g:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")
    g.nome = _validar_grupo(db, body, id)
    g.permissoes = ",".join(p for p in PERMISSOES if p in body.permissoes)
    g.pisos = ",".join(str(p) for p in sorted(set(body.pisos)))
    db.commit()
    registrar(db, quem, "editar_grupo_operadores", detalhe=f"{g.nome}: {_rotulos(db, g)}")
    return _grupo_serial(db, g)

@router.delete("/grupos/{id}")
def excluir_grupo(id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    g = db.get(GrupoOperadores, id)
    if not g:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")
    # os operadores do grupo voltam a operador comum
    db.query(Usuario).filter(Usuario.grupo_operadores_id == id).update({Usuario.grupo_operadores_id: None})
    registrar(db, quem, "excluir_grupo_operadores", detalhe=g.nome)
    db.delete(g)
    db.commit()
    return {"ok": True}

def _rotulos(db: Session, g: GrupoOperadores) -> str:
    texto = ", ".join(PERMISSOES[p] for p in ler_permissoes(g.permissoes)) or "nenhuma permissão"
    pisos = [db.get(Piso, p) for p in ler_pisos(g.pisos)]
    nomes = [p.nome for p in pisos if p]
    return texto + ("; pisos: " + ", ".join(nomes) if nomes else "; todos os pisos")

@router.get("/nomes")
def nomes(db: Session = Depends(get_db), _=Depends(requer_permissao("relatorios"))):
    """Só id e nome: o filtro de operador do registro de ações."""
    ops = db.query(Usuario).filter(Usuario.perfil.in_(["operador", "admin"])).order_by(Usuario.nome).all()
    return [{"id": o.id, "nome": o.nome, "login": o.login, "perfil": o.perfil, "ativo": o.ativo} for o in ops]

def _grupo_valido(db: Session, grupo_id):
    if grupo_id and not db.get(GrupoOperadores, grupo_id):
        raise HTTPException(status_code=400, detail="Grupo nao encontrado")
    return grupo_id or None

@router.get("/")
def listar(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    operadores = db.query(Usuario).filter(
        Usuario.perfil.in_(["operador", "admin"])
    ).order_by(Usuario.perfil, Usuario.nome).all()
    return [serializar(o) for o in operadores]

@router.post("/")
def criar(data: OperadorCreate, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    if db.query(Usuario).filter(Usuario.login == data.login).first():
        raise HTTPException(status_code=400, detail="Login ja existe")
    perfil_val = data.perfil if data.perfil in ("admin", "operador") else "operador"
    operador = Usuario(
        login=data.login, nome=data.nome,
        senha_hash=hash_senha(data.senha),
        perfil=perfil_val,
        grupo_operadores_id=_grupo_valido(db, data.grupo_id) if perfil_val == "operador" else None,
    )
    db.add(operador)
    db.commit()
    db.refresh(operador)
    registrar(db, quem, "criar_operador", detalhe=f"{operador.nome} ({operador.login}, {operador.perfil})")
    return serializar(operador)

@router.put("/{id}")
def atualizar(id: int, data: OperadorUpdate, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    operador = db.query(Usuario).filter(Usuario.id == id).first()
    if not operador:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    if data.nome: operador.nome = data.nome
    if data.senha: operador.senha_hash = hash_senha(data.senha)
    if data.ativo is not None: operador.ativo = data.ativo
    if data.perfil in ("admin", "operador"): operador.perfil = data.perfil
    if data.grupo_id is not None: operador.grupo_operadores_id = _grupo_valido(db, data.grupo_id)
    if operador.perfil == "admin": operador.grupo_operadores_id = None
    db.commit()
    registrar(db, quem, "editar_operador", detalhe=f"{operador.nome} ({operador.login})")
    return serializar(operador)

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    operador = db.query(Usuario).filter(Usuario.id == id).first()
    if not operador:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    # A fila guarda quem liberou cada cliente
    if db.query(Autorizacao).filter(Autorizacao.autorizado_por_id == id).first():
        raise HTTPException(status_code=409,
                            detail="Operador ja liberou clientes. Desative-o em vez de excluir.")
    registrar(db, quem, "excluir_operador", detalhe=f"{operador.nome} ({operador.login})")
    db.delete(operador)
    db.commit()
    return {"ok": True}
