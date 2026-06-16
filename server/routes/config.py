from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import ConfiguracaoSistema
from auth import requer_perfil

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
