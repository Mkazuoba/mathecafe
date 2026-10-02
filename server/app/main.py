from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
import asyncio, json, os

from app.database import get_db, init_db, SessionLocal
from app.models import Estacao, Sessao, Usuario, Autorizacao, GrupoEstacao, AppPermitido, ConfiguracaoSistema
from app.security import verificar_senha, decodificar_token
from app.websocket_manager import manager
from app.routers import auth, clientes, estacoes, sessoes, apps, operadores, config, relatorios

app = FastAPI(title="MatheCafé", version="1.0.0")

SEGUNDOS_ATE_OFFLINE = 8

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api")
app.include_router(clientes.router, prefix="/api")
app.include_router(estacoes.router, prefix="/api")
app.include_router(sessoes.router, prefix="/api")
app.include_router(apps.router, prefix="/api")
app.include_router(operadores.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(relatorios.router, prefix="/api")

@app.on_event("startup")
def startup():
    init_db()
    # Nenhum agente está conectado quando o servidor acaba de subir
    # (manutenção é mantida: vale mesmo com o PC desligado)
    db = SessionLocal()
    try:
        db.query(Estacao).filter(Estacao.status != "manutencao").update({Estacao.status: "desligada"})
        db.commit()
    finally:
        db.close()

# ── WebSocket: painel ─────────────────────────────────────────────────────────
@app.websocket("/ws/painel")
async def ws_painel(ws: WebSocket, token: str = ""):
    # Os eventos trazem nomes de clientes: só admin/operador logado recebe
    try:
        usuario = decodificar_token(token)
    except HTTPException:
        usuario = {}
    if usuario.get("perfil") not in ("admin", "operador"):
        await ws.close(code=4401, reason="Não autenticado")
        return
    await manager.conectar_painel(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.desconectar_painel(ws)

# ── WebSocket: agente da estação ──────────────────────────────────────────────
async def _encerrar_sessao_orfa(db: Session, estacao: Estacao, fim: datetime):
    """Encerra a sessão que ficou aberta quando a conexão do agente caiu,
    devolvendo ao cliente o tempo não usado até a queda."""
    sessao = db.query(Sessao).filter(
        Sessao.estacao_id == estacao.id, Sessao.encerrada_em == None).first()
    if not sessao:
        return
    total = sessao.tempo_total_segundos or 0
    consumido = min(total, max(0, int((fim - sessao.iniciada_em).total_seconds())))
    restante = total - consumido
    sessao.encerrada_em = fim
    sessao.tempo_consumido_segundos = consumido
    sessao.motivo_encerramento = "conexao_perdida"
    sessao.cliente.saldo_segundos = restante
    db.commit()
    await manager.broadcast_paineis("sessao_encerrada", {
        "estacao": estacao.nome,
        "cliente": sessao.cliente.login,
        "motivo": "conexao_perdida",
        "saldo_restante": restante
    })


@app.websocket("/ws/estacao/{nome}")
async def ws_estacao(nome: str, ws: WebSocket, db: Session = Depends(get_db)):
    estacao = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if not estacao:
        # Aceita antes de fechar: assim o agente recebe o código 4004 e o
        # motivo, em vez de um "HTTP 403" genérico
        await ws.accept()
        await ws.close(code=4004, reason="Estação não cadastrada")
        return

    await manager.conectar_estacao(nome, ws)
    estacao.ultimo_ping = datetime.utcnow()
    # Ao perder a conexão o agente volta para a tela de login, então uma
    # sessão ainda aberta nesta estação ficou órfã.
    await _encerrar_sessao_orfa(db, estacao, datetime.utcnow())
    if estacao.status != "manutencao":
        estacao.status = "livre"
    db.commit()
    await manager.broadcast_paineis("estacao_online", {"nome": nome})

    try:
        while True:
            raw = await ws.receive_text()
            # Esta sessão do banco vive a conexão inteira; o painel altera os
            # mesmos registros por outras sessões (liberar, encerrar, saldo).
            # Descarta o cache para ler o estado atual a cada mensagem.
            db.expire_all()
            dados = json.loads(raw)
            evento = dados.get("evento")

            if evento == "ping":
                estacao.ultimo_ping = datetime.utcnow()
                db.commit()
                await ws.send_text(json.dumps({"evento": "pong"}))

            elif evento == "login_cliente":
                login = dados.get("login")
                senha = dados.get("senha")

                cliente = db.query(Usuario).filter(
                    Usuario.login == login,
                    Usuario.perfil == "cliente",
                    Usuario.ativo == True
                ).first()

                if not cliente or not verificar_senha(senha, cliente.senha_hash):
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": "Usuário ou senha inválidos"}
                    }))
                    continue

                autorizacao = db.query(Autorizacao).filter(
                    Autorizacao.cliente_id == cliente.id,
                    Autorizacao.usado == False
                ).first()

                if not autorizacao:
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": "Solicite liberação ao operador"}
                    }))
                    continue

                if estacao.status != "livre":
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": "Estação não está disponível"}
                    }))
                    continue

                if cliente.saldo_segundos > 0:
                    tempo = cliente.saldo_segundos
                else:
                    config_tempo = db.query(ConfiguracaoSistema).filter(
                        ConfiguracaoSistema.chave == "tempo_padrao_segundos").first()
                    if config_tempo:
                        tempo = int(config_tempo.valor)
                    else:
                        grupo = db.query(GrupoEstacao).filter(
                            GrupoEstacao.id == estacao.grupo_id).first()
                        tempo = grupo.tempo_padrao_segundos if grupo else 7200

                sessao = Sessao(
                    cliente_id=cliente.id,
                    estacao_id=estacao.id,
                    tempo_total_segundos=tempo
                )
                db.add(sessao)
                autorizacao.usado = True
                cliente.saldo_segundos = 0
                estacao.status = "ocupada"
                db.commit()
                db.refresh(sessao)

                apps_permitidos = db.query(AppPermitido).filter(
                    AppPermitido.ativo == True,
                    (AppPermitido.grupo_id == estacao.grupo_id) | (AppPermitido.grupo_id == None)
                ).all()
                whitelist = [
                    {
                        "nome": a.nome,
                        "processo": a.processo,
                        "caminho": a.caminho,
                        "imagem_url": a.imagem_url
                    }
                    for a in apps_permitidos
                ]

                config_reiniciar = db.query(ConfiguracaoSistema).filter(
                    ConfiguracaoSistema.chave == "reiniciar_ao_encerrar").first()
                reiniciar = config_reiniciar.valor == "true" if config_reiniciar else False

                await ws.send_text(json.dumps({
                    "evento": "login_resultado",
                    "dados": {
                        "ok": True,
                        "sessao_id": sessao.id,
                        "cliente_nome": cliente.nome,
                        "tempo_segundos": tempo,
                        "whitelist": whitelist,
                        "reiniciar_ao_encerrar": reiniciar
                    }
                }))

                await manager.broadcast_paineis("sessao_iniciada", {
                    "estacao": nome,
                    "cliente_login": login,
                    "cliente_nome": cliente.nome,
                    "tempo_segundos": tempo,
                    "sessao_id": sessao.id
                })
                await manager.broadcast_paineis("fila_atualizada", {
                    "acao": "removido", "cliente_id": cliente.id
                })

            elif evento == "sessao_encerrada":
                sessao_id = dados.get("sessao_id")
                motivo = dados.get("motivo", "cliente")
                consumido = dados.get("tempo_consumido_segundos", 0)

                sessao = db.query(Sessao).filter(
                    Sessao.id == sessao_id, Sessao.encerrada_em == None).first()

                if sessao:
                    agora = datetime.utcnow()
                    restante = max(0, sessao.tempo_total_segundos - consumido)
                    sessao.encerrada_em = agora
                    sessao.tempo_consumido_segundos = consumido
                    sessao.motivo_encerramento = motivo
                    sessao.cliente.saldo_segundos = restante if motivo == "cliente" else 0
                    # Manutenção: status será atualizado pelo evento status_estacao na sequência
                    sessao.estacao.status = "livre"
                    db.commit()

                    await manager.broadcast_paineis("sessao_encerrada", {
                        "estacao": nome,
                        "cliente": sessao.cliente.login,
                        "motivo": motivo,
                        "saldo_restante": restante if motivo == "cliente" else 0
                    })
                    await manager.broadcast_paineis("estacao_online", {"nome": nome})

            elif evento == "status_estacao":
                # O agente só alterna entre manutenção e livre
                novo_status = dados.get("status")
                if novo_status in ("manutencao", "livre"):
                    estacao.status = novo_status
                    db.commit()
                    await manager.broadcast_paineis("estacao_online", {"nome": nome})

            elif evento == "validar_manutencao":
                # Modo manutenção exige login de admin ou operador, conferido
                # aqui — assim não existe senha fixa gravada no agente.
                usuario = db.query(Usuario).filter(
                    Usuario.login == dados.get("login"),
                    Usuario.perfil.in_(("admin", "operador")),
                    Usuario.ativo == True
                ).first()
                ok = bool(usuario and verificar_senha(dados.get("senha") or "", usuario.senha_hash))
                await ws.send_text(json.dumps({"evento": "validar_manutencao_resultado", "dados": {"ok": ok}}))

    except WebSocketDisconnect:
        desconectou_em = datetime.utcnow()
        manager.desconectar_estacao(nome, ws)
        # Espera antes de marcar offline: uma queda rápida de rede não deve
        # fazer a estação "piscar" no painel. Se o agente voltar nesse
        # intervalo, a nova conexão cuida da sessão órfã.
        await asyncio.sleep(SEGUNDOS_ATE_OFFLINE)
        if not manager.estacao_conectada(nome):
            db.expire_all()
            await _encerrar_sessao_orfa(db, estacao, desconectou_em)
            if estacao.status != "manutencao":
                estacao.status = "desligada"
            db.commit()
            await manager.broadcast_paineis("estacao_offline", {"nome": nome})

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

# ── Painel web ────────────────────────────────────────────────────────────────
# static/ é o build do React (server/frontend → `npm run build`).
# static_antigo/ é o painel HTML anterior, mantido em /antigo na transição.
_STATIC = os.path.realpath(os.path.join(os.path.dirname(__file__), "static"))
_ANTIGO = os.path.join(os.path.dirname(__file__), "static_antigo")

app.mount("/antigo", StaticFiles(directory=_ANTIGO, html=True), name="antigo")


@app.get("/{caminho:path}", include_in_schema=False)
def painel(caminho: str):
    """Arquivos do build do React; qualquer outra rota (ex.: /clientes)
    devolve o index.html e o React Router assume a partir daí."""
    if caminho.startswith(("api/", "ws/")):
        raise HTTPException(404)
    arquivo = os.path.realpath(os.path.join(_STATIC, caminho))
    if caminho and arquivo.startswith(_STATIC + os.sep) and os.path.isfile(arquivo):
        return FileResponse(arquivo)
    index = os.path.join(_STATIC, "index.html")
    if not os.path.isfile(index):
        return HTMLResponse("<p>Painel não compilado. Rode <code>npm run build</code> em server/frontend "
                            "ou use o <a href='/antigo/'>painel antigo</a>.</p>", status_code=503)
    # index.html sem cache: um build novo aparece no próximo carregamento
    return FileResponse(index, headers={"Cache-Control": "no-store"})
