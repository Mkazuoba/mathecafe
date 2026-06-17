from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime
import asyncio, json, os

from database import get_db, init_db
from models import Estacao, Sessao, Usuario, Autorizacao, GrupoEstacao, AppPermitido, ConfiguracaoSistema
from auth import verificar_senha, requer_perfil
from websocket_manager import manager
from routes import auth, clientes, estacoes, sessoes, apps, operadores, config, relatorios

app = FastAPI(title="MatheCafé", version="1.0.0")

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

# Caminhos possíveis para o frontend
_BASE = os.path.dirname(os.path.abspath(__file__))
FRONTEND_PATHS = [
    os.path.join(_BASE, "../frontend"),
    os.path.join(_BASE, "frontend"),
    "/opt/render/project/src/frontend",
]
frontend_path = next((p for p in FRONTEND_PATHS if os.path.isdir(p)), None)
if frontend_path:
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.on_event("startup")
def startup():
    init_db()
    print(f"Frontend path: {frontend_path}")

# ── WebSocket: painel ─────────────────────────────────────────────────────────
@app.websocket("/ws/painel")
async def ws_painel(ws: WebSocket):
    await manager.conectar_painel(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.desconectar_painel(ws)

# ── WebSocket: agente da estação ──────────────────────────────────────────────
@app.websocket("/ws/estacao/{nome}")
async def ws_estacao(nome: str, ws: WebSocket, db: Session = Depends(get_db)):
    estacao = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == True).first()
    if not estacao:
        await ws.close(code=4004, reason="Estação não cadastrada")
        return

    await manager.conectar_estacao(nome, ws)
    estacao.ultimo_ping = datetime.utcnow()
    if estacao.status == "desligada":
        estacao.status = "livre"
    db.commit()
    await manager.broadcast_paineis("estacao_online", {"nome": nome})

    try:
        while True:
            raw = await ws.receive_text()
            dados = json.loads(raw)
            evento = dados.get("evento")

            if evento == "ping":
                estacao.ultimo_ping = datetime.utcnow()
                db.commit()
                await ws.send_text(json.dumps({"evento": "pong"}))

            elif evento == "login_cliente":
                db.refresh(estacao)  # força releitura do banco, evitando cache stale
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
                novo_status = dados.get("status", "livre")
                db.refresh(estacao)
                estacao.status = novo_status
                db.commit()
                await manager.broadcast_paineis("estacao_online", {"nome": nome})

    except WebSocketDisconnect:
        manager.desconectar_estacao(nome)
        # Aguarda 8s antes de marcar offline — permite reconexão rápida do agente
        await asyncio.sleep(8)
        if nome not in manager.estacoes_online():
            estacao.status = "desligada"
            db.commit()
            await manager.broadcast_paineis("estacao_offline", {"nome": nome})

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    if frontend_path:
        index = os.path.join(frontend_path, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
    return HTMLResponse("<h1>MatheCafé</h1><p>Acesse <a href='/docs'>/docs</a></p>")
