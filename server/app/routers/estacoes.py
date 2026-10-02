from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models import Estacao, GrupoEstacao, Autorizacao, Usuario, Sessao
from app.security import requer_perfil
from app.websocket_manager import manager

router = APIRouter(prefix="/estacoes", tags=["estacoes"])

class EstacaoUpdate(BaseModel):
    nome: Optional[str] = None
    grupo_id: Optional[int] = None
    ativa: Optional[bool] = None
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None
    mac_address: Optional[str] = None

class PosicaoUpdate(BaseModel):
    pos_x: int
    pos_y: int

def serial_estacao(e: Estacao):
    online = e.nome in manager.estacoes_online()
    # Status do banco: respeita a espera antes de marcar offline (main.py) e
    # mantém "manutencao" mesmo com o agente desconectado.
    status = e.status
    return {
        "id": e.id,
        "nome": e.nome,
        "grupo_id": e.grupo_id,
        "grupo_nome": e.grupo.nome if e.grupo else None,
        "status": status,
        "online": online,
        "ip": e.ip,
        "ultimo_ping": e.ultimo_ping.isoformat() if e.ultimo_ping else None,
        "pos_x": e.pos_x,
        "pos_y": e.pos_y,
        "mac_address": e.mac_address,
    }

def serial_autorizacao(a: Autorizacao):
    return {
        "id": a.id,
        "cliente_id": a.cliente_id,
        "cliente_login": a.cliente.login,
        "cliente_nome": a.cliente.nome,
        "saldo_segundos": a.cliente.saldo_segundos,
        "autorizado_em": a.autorizado_em.isoformat(),
        "autorizado_por": a.autorizado_por.nome,
    }

# ── Grupos ────────────────────────────────────────────────────────────────────
@router.get("/grupos")
def listar_grupos(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [{"id": g.id, "nome": g.nome, "tempo_padrao_segundos": g.tempo_padrao_segundos}
            for g in db.query(GrupoEstacao).filter(GrupoEstacao.ativo == True).all()]

@router.post("/grupos")
def criar_grupo(nome: str, tempo_padrao_segundos: int = 7200,
                db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    g = GrupoEstacao(nome=nome, tempo_padrao_segundos=tempo_padrao_segundos)
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, "nome": g.nome, "tempo_padrao_segundos": g.tempo_padrao_segundos}

class GrupoUpdate(BaseModel):
    nome: Optional[str] = None
    tempo_padrao_segundos: Optional[int] = None

@router.put("/grupos/{grupo_id}")
def atualizar_grupo(grupo_id: int, data: GrupoUpdate,
                    db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    g = db.query(GrupoEstacao).filter(GrupoEstacao.id == grupo_id, GrupoEstacao.ativo == True).first()
    if not g: raise HTTPException(404, "Grupo nao encontrado")
    if data.nome is not None: g.nome = data.nome
    if data.tempo_padrao_segundos is not None: g.tempo_padrao_segundos = data.tempo_padrao_segundos
    db.commit()
    return {"id": g.id, "nome": g.nome, "tempo_padrao_segundos": g.tempo_padrao_segundos}

# ── Estações ──────────────────────────────────────────────────────────────────
@router.get("/")
def listar(grupo_id: Optional[int] = None, db: Session = Depends(get_db),
           _=Depends(requer_perfil("admin", "operador"))):
    q = db.query(Estacao).filter(Estacao.ativa == True)
    if grupo_id:
        q = q.filter(Estacao.grupo_id == grupo_id)
    return [serial_estacao(e) for e in q.order_by(Estacao.nome).all()]

@router.post("/")
def criar(nome: str, grupo_id: Optional[int] = None,
          db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    existente = db.query(Estacao).filter(Estacao.nome == nome).first()
    if existente and existente.ativa:
        raise HTTPException(400, "Estação já existe")
    if existente:
        # Estação excluída que tinha histórico: reativa, mantendo o histórico
        existente.ativa = True
        existente.grupo_id = grupo_id
        e = existente
    else:
        e = Estacao(nome=nome, grupo_id=grupo_id)
        db.add(e)
    db.commit(); db.refresh(e)
    return serial_estacao(e)

@router.put("/{id}")
def atualizar(id: int, data: EstacaoUpdate, db: Session = Depends(get_db),
              _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if data.nome: e.nome = data.nome
    if data.grupo_id is not None: e.grupo_id = data.grupo_id
    if data.ativa is not None: e.ativa = data.ativa
    if data.pos_x is not None: e.pos_x = data.pos_x
    if data.pos_y is not None: e.pos_y = data.pos_y
    if "mac_address" in data.model_fields_set: e.mac_address = data.mac_address
    db.commit()
    return serial_estacao(e)

@router.put("/{id}/posicao")
def atualizar_posicao(id: int, data: PosicaoUpdate, db: Session = Depends(get_db),
                       _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    e.pos_x = data.pos_x
    e.pos_y = data.pos_y
    db.commit()
    return serial_estacao(e)


@router.post("/{nome}/ligar")
async def ligar_pc(nome: str, db: Session = Depends(get_db),
                   _=Depends(requer_perfil("admin", "operador"))):
    """Envia magic packet Wake-on-LAN para a estacao."""
    import socket, struct
    e = db.query(Estacao).filter(Estacao.nome == nome).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    mac = e.mac_address
    if not mac:
        raise HTTPException(400, "MAC address não configurado para esta estação")
    mac_limpo = mac.replace(":", "").replace("-", "")
    if len(mac_limpo) != 12:
        raise HTTPException(400, "MAC address inválido")
    payload = bytes.fromhex("F" * 12 + mac_limpo * 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(payload, ("255.255.255.255", 9))
    return {"ok": True}

@router.post("/{nome}/capturar_tela")
async def capturar_tela(nome: str, _=Depends(requer_perfil("admin", "operador"))):
    """Pede ao agente uma captura de tela silenciosa."""
    if nome not in manager.estacoes_online():
        raise HTTPException(400, "Estação offline")
    await manager.enviar_estacao(nome, "capturar_tela", {})
    return {"ok": True}

@router.delete("/{id}")
def excluir(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    # O histórico de sessões (e os relatórios) aponta para a estação: nesse
    # caso ela só é desativada, o que já a tira de todas as listas do painel.
    if db.query(Sessao).filter(Sessao.estacao_id == id).first():
        e.ativa = False
        db.commit()
        return {"ok": True, "desativada": True}
    db.delete(e); db.commit()
    return {"ok": True}

# ── Fila de espera ────────────────────────────────────────────────────────────
@router.get("/fila")
def ver_fila(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    fila = db.query(Autorizacao).filter(Autorizacao.usado == False)\
             .order_by(Autorizacao.autorizado_em).all()
    return [serial_autorizacao(a) for a in fila]

@router.post("/fila/{cliente_id}")
async def autorizar_cliente(cliente_id: int, db: Session = Depends(get_db),
                             operador=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(
        Usuario.id == cliente_id, Usuario.perfil == "cliente", Usuario.ativo == True).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    auth = db.query(Autorizacao).filter(Autorizacao.cliente_id == cliente_id).first()

    if auth and not auth.usado:
        raise HTTPException(400, "Cliente já está na fila")

    if auth:
        auth.usado = False
        auth.autorizado_por_id = int(operador["sub"])
        auth.autorizado_em = datetime.utcnow()
    else:
        auth = Autorizacao(
            cliente_id=cliente_id,
            autorizado_por_id=int(operador["sub"])
        )
        db.add(auth)

    db.commit()
    db.refresh(auth)

    await manager.broadcast_paineis("fila_atualizada", {
        "acao": "adicionado", "cliente": serial_autorizacao(auth)
    })
    return serial_autorizacao(auth)

@router.delete("/fila/{cliente_id}")
async def remover_fila(cliente_id: int, db: Session = Depends(get_db),
                        _=Depends(requer_perfil("admin", "operador"))):
    auth = db.query(Autorizacao).filter(
        Autorizacao.cliente_id == cliente_id, Autorizacao.usado == False).first()
    if not auth:
        raise HTTPException(404, "Cliente não está na fila")
    db.delete(auth); db.commit()
    await manager.broadcast_paineis("fila_atualizada", {"acao": "removido", "cliente_id": cliente_id})
    return {"ok": True}

# ── Comandos por estação ──────────────────────────────────────────────────────

class MensagemBody(BaseModel):
    texto: str

class LiberarDiretoBody(BaseModel):
    cliente_id: int

@router.post("/{nome}/reiniciar")
async def reiniciar_pc(nome: str, db: Session = Depends(get_db),
                        _=Depends(requer_perfil("admin", "operador"))):
    e = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if nome not in manager.estacoes_online():
        raise HTTPException(400, "Estação offline")
    await manager.enviar_estacao(nome, "reiniciar_pc", {})
    return {"ok": True}

@router.post("/{nome}/mensagem")
async def enviar_mensagem(nome: str, body: MensagemBody, db: Session = Depends(get_db),
                           _=Depends(requer_perfil("admin", "operador"))):
    e = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if nome not in manager.estacoes_online():
        raise HTTPException(400, "Estação offline")
    await manager.enviar_estacao(nome, "mensagem_tela", {"texto": body.texto})
    return {"ok": True}

@router.post("/{nome}/manutencao")
async def alternar_manutencao(nome: str, db: Session = Depends(get_db),
                               _=Depends(requer_perfil("admin", "operador"))):
    e = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if nome not in manager.estacoes_online():
        raise HTTPException(400, "Estação offline")
    if e.status == "manutencao":
        await manager.enviar_estacao(nome, "desativar_manutencao", {})
    else:
        await manager.enviar_estacao(nome, "ativar_manutencao", {})
    return {"ok": True}

@router.post("/{nome}/iniciar_direto")
async def iniciar_direto(nome: str, body: LiberarDiretoBody, db: Session = Depends(get_db),
                          operador=Depends(requer_perfil("admin", "operador"))):
    from datetime import datetime as dt
    from app.models import Sessao as SessaoModel

    e = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if nome not in manager.estacoes_online():
        raise HTTPException(400, "Estação offline")
    if e.status != "livre":
        raise HTTPException(400, "Estação não está livre")

    cliente = db.query(Usuario).filter(
        Usuario.id == body.cliente_id, Usuario.perfil == "cliente", Usuario.ativo == True).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    # Sessao ja ativa?
    sessao_existente = db.query(SessaoModel).filter(
        SessaoModel.cliente_id == cliente.id, SessaoModel.encerrada_em == None).first()
    if sessao_existente:
        raise HTTPException(400, "Cliente já tem sessão ativa")

    # Tempo: saldo do cliente ou tempo padrao do grupo
    if cliente.saldo_segundos > 0:
        tempo = cliente.saldo_segundos
    else:
        tempo = e.grupo.tempo_padrao_segundos if e.grupo else 7200

    # Cria/reusa autorizacao como usada
    auth = db.query(Autorizacao).filter(Autorizacao.cliente_id == cliente.id).first()
    if auth:
        auth.usado = True
        auth.autorizado_por_id = int(operador["sub"])
        auth.autorizado_em = dt.utcnow()
    else:
        auth = Autorizacao(
            cliente_id=cliente.id,
            autorizado_por_id=int(operador["sub"]),
            usado=True
        )
        db.add(auth)
    db.flush()

    # Cria sessao
    sessao = SessaoModel(
        cliente_id=cliente.id,
        estacao_id=e.id,
        tempo_total_segundos=tempo,
        iniciada_em=dt.utcnow()
    )
    db.add(sessao)
    e.status = "ocupada"
    db.commit()
    db.refresh(sessao)
    db.refresh(cliente)

    # Whitelist: apps do grupo da estacao + apps globais (grupo_id=None)
    from app.models import AppPermitido, ConfiguracaoSistema
    from sqlalchemy import or_ as _or
    apps = db.query(AppPermitido).filter(
        AppPermitido.ativo == True,
        _or(AppPermitido.grupo_id == e.grupo_id, AppPermitido.grupo_id == None)
    ).all()

    cfg_reiniciar = db.query(ConfiguracaoSistema).filter(
        ConfiguracaoSistema.chave == "reiniciar_ao_encerrar").first()
    reiniciar = cfg_reiniciar.valor == "true" if cfg_reiniciar else False

    payload = {
        "ok": True,
        "sessao_id": sessao.id,
        "cliente_nome": cliente.nome,
        "tempo_segundos": tempo,
        "reiniciar_ao_encerrar": reiniciar,
        "whitelist": [{"nome": a.nome, "processo": a.processo, "caminho": a.caminho,
                       "imagem_url": a.imagem_url} for a in apps],
    }
    await manager.enviar_estacao(nome, "iniciar_sessao_direta", payload)
    await manager.broadcast_paineis("estacao_atualizada", {"nome": nome})

    return {"ok": True, "sessao_id": sessao.id}


@router.post("/{nome}/iniciar_streaming")
async def iniciar_streaming(nome: str, _=Depends(requer_perfil("admin", "operador"))):
    if nome not in manager.estacoes_online():
        raise HTTPException(400, "Estacao offline")
    await manager.enviar_estacao(nome, "iniciar_streaming", {})
    return {"ok": True}


@router.post("/{nome}/parar_streaming")
async def parar_streaming(nome: str, _=Depends(requer_perfil("admin", "operador"))):
    if nome in manager.estacoes_online():
        await manager.enviar_estacao(nome, "parar_streaming", {})
    return {"ok": True}

