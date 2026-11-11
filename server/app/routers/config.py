import json
import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from datetime import datetime
from fastapi.responses import FileResponse
from app import backup, horario
from app.config import _ENV_FILE, descrever_banco, get_settings, gravar_no_env, normalizar_url_banco, pasta_de_backup
from app.database import ARQUIVO_SQLITE, PEDIDO_RESTAURACAO, _db_url, get_db
from app.tempo_diario import FUSO, hoje_br
from app.models import ConfiguracaoSistema, Sessao, Usuario
from app.security import requer_perfil
from app.registro import registrar
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
def atualizar(data: ConfigUpdate, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    if data.reiniciar_ao_encerrar is not None:
        _set(db, "reiniciar_ao_encerrar", "true" if data.reiniciar_ao_encerrar else "false")
    if data.tempo_padrao_segundos is not None:
        _set(db, "tempo_padrao_segundos", str(data.tempo_padrao_segundos))
    db.commit()
    registrar(db, quem, "configuracao", detalhe=", ".join(
        f"{k}={v}" for k, v in data.model_dump(exclude_none=True).items()))

    configs = db.query(ConfiguracaoSistema).all()
    valores = {c.chave: c.valor for c in configs}
    return {
        "reiniciar_ao_encerrar": valores.get("reiniciar_ao_encerrar", "false") == "true",
        "tempo_padrao_segundos": int(valores.get("tempo_padrao_segundos", "7200")),
    }


@router.post("/zerar_tempo_hoje")
def zerar_tempo_hoje(db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    """Faz agora o que a meia-noite faria: todos os clientes voltam ao tempo cheio."""
    n = zerar_tempo_de_hoje(db)
    registrar(db, quem, "zerar_tempo_dia", detalhe=f"{n} cliente(s)")
    return {"ok": True, "clientes": n}


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


# ── Backup diario (SQLite) ───────────────────────────────────────────────────
PASTA_BACKUP = pasta_de_backup(get_settings().BACKUP_PASTA)
DIAS_BACKUP = max(1, get_settings().BACKUP_DIAS)


def backup_agora():
    """Faz o backup do banco agora (horario de Brasilia no nome)."""
    agora = datetime.now(FUSO).replace(tzinfo=None)
    return backup.fazer_backup(ARQUIVO_SQLITE, PASTA_BACKUP, agora, DIAS_BACKUP)


def backup_diario_pendente() -> bool:
    return ARQUIVO_SQLITE is not None and not backup.backup_de_hoje_feito(PASTA_BACKUP, hoje_br())


@router.get("/backup")
def ver_backups(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    return {"ativo": ARQUIVO_SQLITE is not None, "pasta": str(PASTA_BACKUP), "dias": DIAS_BACKUP,
            "backups": backup.listar_backups(PASTA_BACKUP),
            # o banco de antes de cada restauracao (para desfazer) e os enviados
            "outros": backup.listar_outros(PASTA_BACKUP),
            "sessoes_abertas": _sessoes_abertas(db)}


def _sessoes_abertas(db: Session) -> int:
    return db.query(Sessao).filter(Sessao.encerrada_em == None).count()


class Restaurar(BaseModel):
    confirmar: bool = False  # com clientes usando os PCs


@router.post("/backup/enviar")
async def enviar_backup(arquivo: UploadFile = File(...), _=Depends(requer_perfil("admin"))):
    """Um banco trazido de fora (a copia guardada em outro lugar): confere e guarda
    na pasta dos backups como enviado-...db, para restaurar pela lista."""
    if ARQUIVO_SQLITE is None:
        raise HTTPException(400, "Restaurar é só para o SQLite")
    PASTA_BACKUP.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(FUSO).replace(tzinfo=None)
    destino = PASTA_BACKUP / f"enviado-{agora:%Y-%m-%d-%H%M%S}.db"
    temporario = destino.with_name(destino.name + ".tmp")
    try:
        with open(temporario, "wb") as f:
            while bloco := await arquivo.read(1024 * 1024):
                f.write(bloco)
        conferido = backup.conferir_banco(temporario)
    except ValueError as e:
        temporario.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    os.replace(temporario, destino)
    item = next(b for b in backup.listar_outros(PASTA_BACKUP) if b["nome"] == destino.name)
    return {**item, "conferido": conferido}


@router.post("/backup/{nome}/restaurar")
def restaurar_backup(nome: str, data: Restaurar, db: Session = Depends(get_db),
                     quem=Depends(requer_perfil("admin"))):
    """Confere o backup e pede a restauracao: o servidor reinicia e, ao subir,
    guarda o banco atual (antes-da-restauracao-...db) e poe o backup no lugar."""
    if ARQUIVO_SQLITE is None:
        raise HTTPException(400, "Restaurar é só para o SQLite")
    arquivo = backup.restauravel(PASTA_BACKUP, nome)
    if arquivo is None:
        raise HTTPException(404, "Backup não encontrado")
    try:
        conferido = backup.conferir_banco(arquivo)
    except ValueError as e:
        raise HTTPException(400, str(e))
    abertas = _sessoes_abertas(db)
    if abertas and not data.confirmar:
        raise HTTPException(409, f"{abertas} computador(es) em uso: as sessões voltam ao estado do backup. Confirme para restaurar")
    operador = db.get(Usuario, int(quem["sub"])) if quem.get("sub") else None
    PEDIDO_RESTAURACAO.write_text(json.dumps({
        "arquivo": str(arquivo.resolve()),
        "quem": {"sub": quem.get("sub"), "nome": operador.nome if operador else quem.get("nome")},
    }), encoding="utf-8")
    print(f"Restauracao pedida pelo painel: {nome}")
    reiniciando = _supervisionado()
    if reiniciando:
        import threading
        threading.Timer(1.0, _encerrar_processo).start()  # depois de responder
    return {"ok": True, "reiniciando": reiniciando, "conferido": conferido}


@router.post("/backup")
def fazer_backup_agora(_=Depends(requer_perfil("admin"))):
    if ARQUIVO_SQLITE is None:
        raise HTTPException(400, "Backup automatico so para o SQLite; o PostgreSQL tem o backup do proprio provedor")
    destino = backup_agora()
    return next(b for b in backup.listar_backups(PASTA_BACKUP) if b["nome"] == destino.name)


@router.get("/backup/{nome}")
def baixar_backup(nome: str, _=Depends(requer_perfil("admin"))):
    # So nomes no formato do backup: nada de caminho para fora da pasta
    arquivo = backup.restauravel(PASTA_BACKUP, nome)
    if arquivo is None:
        raise HTTPException(404, "Backup nao encontrado")
    return FileResponse(arquivo, filename=nome, media_type="application/octet-stream")


# ── Horario de funcionamento (app/horario.py) ────────────────────────────────


class HorarioDia(BaseModel):
    aberto: bool
    abre: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    fecha: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

    @model_validator(mode="after")
    def _fecha_depois(self):
        if self.aberto and self.fecha <= self.abre:
            raise ValueError("O horário de fechar tem de ser depois do de abrir")
        return self


class Horario(BaseModel):
    ativo: bool
    dias: List[HorarioDia] = Field(min_length=7, max_length=7)  # 0 = segunda


@router.get("/horario")
def ver_horario(db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    return horario.carregar(db)


@router.put("/horario")
def salvar_horario(data: Horario, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    horario.gravar(db, data.model_dump())
    registrar(db, quem, "horario", detalhe="ligado" if data.ativo else "desligado")
    return horario.carregar(db)


# ── Reiniciar o servidor pelo painel ─────────────────────────────────────────
# O iniciar_servidor.bat (tarefa MatheCafe-Servidor) sobe o servidor de novo
# sempre que ele termina e marca MATHECAFE_SUPERVISIONADO=1. Assim o admin do
# MatheCafe reinicia sem precisar de PowerShell de administrador do Windows.

NO_AR_DESDE = datetime.utcnow()


def _supervisionado() -> bool:
    return os.environ.get("MATHECAFE_SUPERVISIONADO") == "1"


def _encerrar_processo():
    os._exit(3)  # o .bat sobe de novo em seguida


# Reiniciar pelo Windows, sem administrador e sem o painel: o
# reiniciar_servidor.bat (clique duplo) cria este arquivo na pasta server/; o
# servidor da tarefa (que roda como SYSTEM) apaga e sai, e o .bat da tarefa o
# sobe de novo com o codigo novo.
from pathlib import Path
PEDIDO_REINICIO = Path(__file__).resolve().parents[2] / "reiniciar.pedido"


def pedido_de_reinicio() -> bool:
    """Ha um pedido de reinicio para atender? So com o servidor supervisionado
    (aberto a mao, ninguem o subiria de novo: o pedido fica la)."""
    if not _supervisionado() or not PEDIDO_REINICIO.exists():
        return False
    try:
        PEDIDO_REINICIO.unlink()
    except OSError:
        return False
    return True


async def vigiar_pedido_de_reinicio():
    import asyncio
    while True:
        await asyncio.sleep(2)
        if pedido_de_reinicio():
            print("Reiniciando o servidor a pedido do reiniciar_servidor.bat")
            _encerrar_processo()


@router.get("/servidor")
def ver_servidor(_=Depends(requer_perfil("admin"))):
    return {"pode_reiniciar": _supervisionado(), "no_ar_desde": NO_AR_DESDE.isoformat() + "Z"}


@router.post("/reiniciar")
async def reiniciar_servidor(db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    if not _supervisionado():
        raise HTTPException(400, "Este servidor foi aberto à mão (sem o iniciar_servidor.bat): "
                                 "ninguém o subiria de novo. Reinicie no terminal onde ele está rodando.")
    registrar(db, quem, "reiniciar_servidor")
    print("Reiniciando o servidor a pedido do painel")
    import asyncio
    asyncio.get_running_loop().call_later(1.0, _encerrar_processo)  # depois de responder
    return {"ok": True}
