import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.config import _ENV_FILE, descrever_banco, gravar_no_env, normalizar_url_banco
from app.database import _db_url, get_db
from app.models import ConfiguracaoSistema
from app.security import requer_perfil
from app.tempo_diario import zerar_tempo_de_hoje

router = APIRouter(prefix="/config", tags=["config"])

class ConfigUpdate(BaseModel):
    reiniciar_ao_encerrar: Optional[bool] = None
    tempo_padrao_segundos: Optional[int] = None

def _set(db: Session, chave: str, valor: str):
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == chave).first()
    if cfg:
        cfg.valor = valor
    else:
        db.add(ConfiguracaoSistema(chave=chave, valor=valor))

@router.get("/")
def obter(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    configs = db.query(ConfiguracaoSistema).all()
    valores = {c.chave: c.valor for c in configs}
    return {
        "reiniciar_ao_encerrar": valores.get("reiniciar_ao_encerrar", "false") == "true",
        "tempo_padrao_segundos": int(valores.get("tempo_padrao_segundos", "7200")),
    }

@router.put("/")
def atualizar(data: ConfigUpdate, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    if data.reiniciar_ao_encerrar is not None:
        _set(db, "reiniciar_ao_encerrar", "true" if data.reiniciar_ao_encerrar else "false")
    if data.tempo_padrao_segundos is not None:
        _set(db, "tempo_padrao_segundos", str(data.tempo_padrao_segundos))
    db.commit()

    configs = db.query(ConfiguracaoSistema).all()
    valores = {c.chave: c.valor for c in configs}
    return {
        "reiniciar_ao_encerrar": valores.get("reiniciar_ao_encerrar", "false") == "true",
        "tempo_padrao_segundos": int(valores.get("tempo_padrao_segundos", "7200")),
    }


@router.post("/zerar_tempo_hoje")
def zerar_tempo_hoje(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    """Faz agora o que a meia-noite faria: todos os clientes voltam ao tempo cheio."""
    return {"ok": True, "clientes": zerar_tempo_de_hoje(db)}


# ── Banco do servidor ────────────────────────────────────────────────────────
# Trocar o banco sem reinstalar: o admin testa a URL nova e ela vai para o
# server/.env, que vale na proxima subida do servidor.
ARQUIVO_ENV = _ENV_FILE


def banco_no_ambiente() -> bool:
    """DATABASE_URL definida no ambiente (Render) vale mais que o .env."""
    return bool(os.environ.get("DATABASE_URL"))


class BancoUrl(BaseModel):
    url: str


def _normalizar(url: str) -> str:
    try:
        return normalizar_url_banco(url)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _testar_banco(url: str) -> dict:
    """Conecta na URL e diz se ja ha dados do MatheCafe (tabela usuarios)."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    args = {} if url.startswith("sqlite") else {"connect_timeout": 5}
    engine = None
    try:
        engine = create_engine(url, connect_args=args)
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
            vazio = not inspect(con).has_table("usuarios")
        return {"ok": True, "vazio": vazio, "mensagem": "Conectou. " + (
            "Banco vazio: o servidor cria as tabelas, mas sera preciso criar o admin "
            "(python -m app.cli ou ADMIN_LOGIN/ADMIN_SENHA no .env)." if vazio
            else "O banco ja tem dados do MatheCafe.")}
    except Exception as e:
        mensagem = str(getattr(e, "orig", None) or e).strip().splitlines()[0]
        try:
            senha = make_url(url).password
        except Exception:
            senha = None
        if senha:
            mensagem = mensagem.replace(senha, "***")
        return {"ok": False, "vazio": None, "mensagem": f"Nao conectou: {mensagem}"}
    finally:
        if engine is not None:
            engine.dispose()


@router.get("/banco")
def banco_atual(_=Depends(requer_perfil("admin"))):
    return {**descrever_banco(_db_url), "no_ambiente": banco_no_ambiente()}


@router.post("/banco/testar")
def testar_banco(data: BancoUrl, _=Depends(requer_perfil("admin"))):
    return _testar_banco(_normalizar(data.url))


@router.put("/banco")
def trocar_banco(data: BancoUrl, _=Depends(requer_perfil("admin"))):
    url = _normalizar(data.url)
    if banco_no_ambiente():
        raise HTTPException(409, "O banco deste servidor vem da variavel de ambiente DATABASE_URL "
                                 "(no Render: Environment). Troque por la.")
    teste = _testar_banco(url)
    if not teste["ok"]:
        raise HTTPException(400, teste["mensagem"])
    gravar_no_env(ARQUIVO_ENV, "DATABASE_URL", url)
    return {**teste, "reiniciar": True}
