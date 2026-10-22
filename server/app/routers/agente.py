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
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/agente", tags=["agente"])

# Pasta onde fica o agente.py que o servidor distribui
DIST_DIR = Path(__file__).parent.parent / "agente_dist"
DIST_FILE = DIST_DIR / "agente.py"


def _versao_dist() -> str:
    """Le a constante VERSAO = "x.y.z" do arquivo distribuido."""
    if not DIST_FILE.exists():
        return "0.0.0"
    try:
        for linha in DIST_FILE.read_text(encoding="utf-8").splitlines():
            stripped = linha.strip()
            if stripped.startswith("VERSAO") and "=" in stripped:
                _, _, v = stripped.partition("=")
                return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return "0.0.0"


@router.get("/versao")
def versao():
    """Retorna a versao do agente que o servidor esta distribuindo."""
    return {"versao": _versao_dist()}


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
