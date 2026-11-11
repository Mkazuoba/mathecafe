"""
Router de auto-update do agente.

O agente verifica GET /api/agente/versao antes de conectar.
Se a versao do servidor for maior, baixa GET /api/agente/download,
salva sobre si mesmo e reinicia o processo.

A versao e definida pela constante VERSAO no topo do agente.py.
Para publicar uma nova versao: incremente VERSAO no agente.py
e copie o arquivo para server/agente_dist/agente.py.
"""
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(prefix="/agente", tags=["agente"])

# Pasta onde fica o agente.py que o servidor distribui (server/agente_dist)
DIST_DIR = Path(__file__).resolve().parents[2] / "agente_dist"
DIST_FILE = DIST_DIR / "agente.py"


_cache_versao = {"mtime": None, "versao": "0.0.0"}


def _versao_dist() -> str:
    """Le a constante VERSAO = "x.y.z" do arquivo distribuido (relida so quando o
    arquivo muda: a lista de estacoes pergunta uma vez por estacao)."""
    if not DIST_FILE.exists():
        return "0.0.0"
    mtime = DIST_FILE.stat().st_mtime
    if _cache_versao["mtime"] != mtime:
        _cache_versao.update(mtime=mtime, versao=_ler_versao_dist())
    return _cache_versao["versao"]


def _ler_versao_dist() -> str:
    try:
        for linha in DIST_FILE.read_text(encoding="utf-8").splitlines():
            stripped = linha.strip()
            if stripped.startswith("VERSAO") and "=" in stripped:
                _, _, v = stripped.partition("=")
                return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return "0.0.0"


def _numeros(v: str):
    try:
        return tuple(int(x) for x in (v or "").strip().split("."))
    except ValueError:
        return (0,)


def desatualizado(versao_agente) -> bool:
    """O agente informou uma versao mais velha que a que o servidor distribui?
    (Sem versao: agente antigo, de antes do evento estado, tambem e.)"""
    return _numeros(versao_agente or "0") < _numeros(_versao_dist())


@router.get("/versao")
def versao():
    """Retorna a versao do agente que o servidor esta distribuindo."""
    return {"versao": _versao_dist()}


@router.get("/pisos", response_class=PlainTextResponse)
def pisos_para_o_instalador(db: Session = Depends(get_db)):
    """Os pisos, uma linha "id;nome" cada (o instalador.bat le sem JSON e sem
    login: so os nomes dos pisos). O PC instalado conecta com ?piso=id (6.18)."""
    from app.models import Piso
    pisos = db.query(Piso).order_by(Piso.id).all()
    return "".join(f"{p.id};{p.nome}\r\n" for p in pisos)  # CRLF: o cmd le direito


@router.get("/download")
def download():
    """Baixa o agente.py atual. Sem autenticacao — o agente ainda nao tem token."""
    if not DIST_FILE.exists():
        raise HTTPException(status_code=404, detail="Agente nao disponivel no servidor")
    return FileResponse(
        path=str(DIST_FILE),
        filename="agente.py",
        media_type="text/x-python",
    )
