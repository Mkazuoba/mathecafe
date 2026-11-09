from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import asyncio, json, os
from typing import Optional

from app.database import get_db, init_db, SessionLocal
from app.models import Estacao, Sessao, Usuario, Autorizacao, GrupoEstacao, AppPermitido, ConfiguracaoSistema
from app.security import verificar_senha, decodificar_token
from app.websocket_manager import manager
from app.pisos import apps_do_piso, cor_para_o_agente, piso_da_estacao, recusa_de_piso
from app import horario
from app.estacoes_novas import AGUARDANDO, estacao_do_agente, info_para_o_agente
from app.tempo_diario import ESGOTADO_CLIENTE, fechar_tempo_da_sessao, reservar_tempo
from app.routers import auth, clientes, estacoes, sessoes, apps, operadores, config, relatorios, programacao, pisos as pisos_router, agente as agente_router

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
app.include_router(programacao.router, prefix="/api")
app.include_router(pisos_router.router, prefix="/api")
app.include_router(agente_router.router, prefix="/api")

# A cada minuto o servidor grava que esta vivo. Ao subir de novo, isso diz
# quando ele caiu: as sessoes abertas ficam "sem conexao" desde ali (o cliente
# segue usando no PC; se o PC nunca voltar, so se cobra ate a queda).
SEGUNDOS_BATIMENTO = 60
CHAVE_BATIMENTO = "servidor_vivo_em"


def _gravar_batimento(db: Session, quando: datetime):
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE_BATIMENTO).first()
    if cfg:
        cfg.valor = quando.isoformat()
    else:
        db.add(ConfiguracaoSistema(chave=CHAVE_BATIMENTO, valor=quando.isoformat()))
    db.commit()


def marcar_sessoes_sem_conexao(db: Session) -> int:
    """Na subida: as sessoes abertas continuam (o cliente segue usando no PC e o
    agente retoma ao reconectar). Ficam marcadas sem conexao desde o ultimo
    batimento, que e quando o servidor caiu. Sem batimento, desde o inicio: um
    PC que nunca voltar nao paga nada."""
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE_BATIMENTO).first()
    try:
        caiu_em = datetime.fromisoformat(cfg.valor) if cfg else None
    except ValueError:
        caiu_em = None
    abertas = db.query(Sessao).filter(Sessao.encerrada_em == None, Sessao.sem_conexao_desde == None).all()
    for sessao in abertas:
        sessao.sem_conexao_desde = (max(sessao.iniciada_em, min(caiu_em, datetime.utcnow())) if caiu_em
                                    else sessao.iniciada_em)
    db.commit()
    return len(abertas)


def _tempo_acabou(sessao, agora: datetime) -> bool:
    """Pelo relogio do servidor, o tempo concedido ja terminou? (sem gravar nada)"""
    pausas = sessao.tempo_pausado_segundos or 0
    concedido = max(0, (sessao.tempo_total_segundos or 0) - pausas)
    if sessao.pausada and sessao.pausada_em:
        pausas += max(0, int((agora - sessao.pausada_em).total_seconds()))
    return (agora - sessao.iniciada_em).total_seconds() - pausas >= concedido


def encerrar_sessoes_vencidas(db: Session, agora: datetime) -> int:
    """PC sem conexao que nunca voltou (desligado): encerra a sessao quando o tempo
    dela acabaria, cobrando so ate a queda e devolvendo o resto ao cliente."""
    vencidas = [s for s in db.query(Sessao).filter(Sessao.encerrada_em == None, Sessao.sem_conexao_desde != None)
                if _tempo_acabou(s, agora)]
    for sessao in vencidas:
        _fechar_sessao_sem_conexao(sessao)
        if not manager.estacao_conectada(sessao.estacao.nome) and sessao.estacao.status == "ocupada":
            sessao.estacao.status = "desligada"
    db.commit()
    return len(vencidas)


def _fechar_sessao_sem_conexao(sessao) -> int:
    """Encerra como conexao_perdida, contando o uso ate a queda. Devolve o restante."""
    fim = max(sessao.iniciada_em, sessao.sem_conexao_desde or datetime.utcnow())
    _, restante = fechar_tempo_da_sessao(sessao, fim)
    sessao.encerrada_em = fim
    sessao.motivo_encerramento = "conexao_perdida"
    sessao.cliente.saldo_segundos = restante
    sessao.sem_conexao_desde = None
    return restante


# avisos de fechamento ja dados hoje: {(data, minutos)}
_avisos_do_horario: set = set()


async def _aplicar_horario(db: Session):
    config_horario = horario.carregar(db)
    agora = horario.agora_local()
    decisao = horario.decidir(config_horario, agora, _avisos_do_horario)
    if decisao["aviso"]:
        texto = horario.texto_do_aviso(config_horario, agora, decisao["aviso"])
        for sessao in db.query(Sessao).filter(Sessao.encerrada_em == None):
            await manager.enviar_estacao(sessao.estacao.nome, "mensagem_tela", {"texto": texto, "origem": "horario"})
    if decisao["encerrar"]:
        encerradas = horario.encerrar_sessoes_do_fechamento(db)
        for nome, restante in encerradas:
            await manager.enviar_estacao(nome, "encerrar_sessao", {"motivo": "horario", "saldo_restante": restante})
        if encerradas:
            print(f"Horario de funcionamento: {len(encerradas)} sessao(oes) encerrada(s)")
            await manager.broadcast_paineis("sessao_encerrada", {"motivo": "horario"})


async def _batimento():
    while True:
        db = SessionLocal()
        try:
            _gravar_batimento(db, datetime.utcnow())
        except Exception as e:
            print(f"Batimento: erro ao gravar ({e})")
        finally:
            db.close()
        # Backup do dia: o primeiro batimento depois da meia-noite (ou da
        # subida do servidor, se o de hoje ainda nao foi feito)
        try:
            if config.backup_diario_pendente():
                destino = await asyncio.to_thread(config.backup_agora)
                print(f"Backup do banco: {destino}")
        except Exception as e:
            print(f"Backup do banco: erro ({e})")
        # Horario de funcionamento: avisa antes de fechar e encerra no horario
        db = SessionLocal()
        try:
            await _aplicar_horario(db)
        except Exception as e:
            print(f"Horario de funcionamento: erro ({e})")
        finally:
            db.close()
        # PC sem conexao que nao voltou ate o fim do tempo do cliente
        db = SessionLocal()
        try:
            if encerrar_sessoes_vencidas(db, datetime.utcnow()):
                await manager.broadcast_paineis("sessao_encerrada", {"motivo": "conexao_perdida"})
        except Exception as e:
            print(f"Sessoes sem conexao: erro ao encerrar ({e})")
        finally:
            db.close()
        await asyncio.sleep(SEGUNDOS_BATIMENTO)


@app.on_event("startup")
async def startup():
    init_db()
    db = SessionLocal()
    try:
        n = marcar_sessoes_sem_conexao(db)
        if n:
            print(f"{n} sessao(oes) seguem abertas: o agente retoma ao reconectar")
        # Nenhum agente está conectado quando o servidor acaba de subir
        # (manutenção é mantida: vale mesmo com o PC desligado). Com sessão
        # aberta continua ocupada: o cliente segue usando no PC.
        db.query(Estacao).filter(Estacao.status != "manutencao").update({Estacao.status: "desligada"})
        for sessao in db.query(Sessao).filter(Sessao.encerrada_em == None):
            if sessao.estacao.status != "manutencao":
                sessao.estacao.status = "ocupada"
        db.commit()
    finally:
        db.close()
    app.state.batimento = asyncio.create_task(_batimento())


@app.on_event("shutdown")
async def shutdown():
    tarefa = getattr(app.state, "batimento", None)
    if tarefa:
        tarefa.cancel()

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
async def _resolver_estado(db: Session, estacao: Estacao, sessao_id) -> dict:
    """O agente (re)conectou dizendo em que sessao esta (ou nenhuma).

    Mesma sessao aberta: retoma (o servidor caiu, ou a rede, e o cliente seguiu
    usando). Sessao aberta e o agente sem ela: o PC reiniciou e voltou ao login,
    encerra cobrando ate a queda. O agente numa sessao ja encerrada (o operador
    encerrou enquanto estava sem conexao): manda ele voltar ao login.
    """
    aberta = db.query(Sessao).filter(Sessao.estacao_id == estacao.id, Sessao.encerrada_em == None).first()
    if aberta and sessao_id == aberta.id:
        aberta.sem_conexao_desde = None
        estacao.status = "ocupada"
        db.commit()
        await manager.broadcast_paineis("estacao_online", {"nome": estacao.nome})
        return {"evento": "pong"}
    if aberta:
        restante = _fechar_sessao_sem_conexao(aberta)
        await manager.broadcast_paineis("sessao_encerrada", {
            "estacao": estacao.nome,
            "cliente": aberta.cliente.login,
            "motivo": "conexao_perdida",
            "saldo_restante": restante
        })
    if estacao.status != "manutencao":
        estacao.status = "livre"
    db.commit()
    await manager.broadcast_paineis("estacao_online", {"nome": estacao.nome})
    if sessao_id:
        sessao = db.get(Sessao, sessao_id)
        saldo = sessao.cliente.saldo_segundos if sessao and sessao.cliente else 0
        return {"evento": "encerrar_sessao", "dados": {"saldo_restante": saldo}}
    return {"evento": "pong"}


def _nome_atual(estacao: Estacao, nome: str) -> str:
    """O nome no banco (o painel pode ter renomeado); o de antes se a estacao
    foi apagada com o agente conectado."""
    try:
        return estacao.nome
    except Exception:
        return nome


@app.websocket("/ws/estacao/{nome}")
async def ws_estacao(nome: str, ws: WebSocket, id: Optional[str] = None, db: Session = Depends(get_db)):
    # agente 1.14 manda ?id= (o UUID da instalacao): PC desconhecido vira estacao
    # pendente em "Novas estacoes" (app/estacoes_novas.py). Sem id, so pelo nome.
    estacao, nova = estacao_do_agente(db, nome, id)
    if not estacao:
        # Aceita antes de fechar: assim o agente recebe o código 4004 e o
        # motivo, em vez de um "HTTP 403" genérico
        await ws.accept()
        await ws.close(code=4004, reason="Estação não cadastrada")
        return

    # o nome cadastrado vale (o painel pode ter renomeado; o agente e avisado)
    nome = estacao.nome
    await manager.conectar_estacao(nome, ws)
    estacao.ultimo_ping = datetime.utcnow()
    # Com sessao aberta, segue ocupada ate o agente dizer em que estado esta
    # (evento "estado", a primeira mensagem do agente 1.8). Sem sessao, livre: um
    # "manutencao" que sobrou (agente fechado ou reiniciado na manutencao) travava
    # a estacao; se ele continua na manutencao, avisa logo em seguida.
    tem_sessao = db.query(Sessao).filter(Sessao.estacao_id == estacao.id, Sessao.encerrada_em == None).first()
    estacao.status = "ocupada" if tem_sessao else "livre"
    db.commit()
    await manager.broadcast_paineis("estacao_online", {"nome": nome})
    if not estacao.aprovada:
        await manager.broadcast_paineis("estacao_pendente", {"nome": nome, "nova": nova})
    estado_recebido = False

    try:
        while True:
            raw = await ws.receive_text()
            # Esta sessão do banco vive a conexão inteira; o painel altera os
            # mesmos registros por outras sessões (liberar, encerrar, saldo).
            # Descarta o cache para ler o estado atual a cada mensagem.
            db.expire_all()
            nome = _nome_atual(estacao, nome)  # renomeada no painel: a conexao ja mudou de nome
            dados = json.loads(raw)
            evento = dados.get("evento")

            if evento == "teste_conexao":
                # Configurar conexao -> Testar (agente 1.8): so responde, sem
                # mexer na sessao da estacao
                await ws.send_text(json.dumps({"evento": "pong"}))
                continue
            if evento == "estado":
                estado_recebido = True
                if dados.get("versao") and estacao.versao_agente != dados["versao"]:
                    estacao.versao_agente = str(dados["versao"])[:20]
                    db.commit()
                resposta = await _resolver_estado(db, estacao, dados.get("sessao_id"))
                await ws.send_text(json.dumps(resposta))
                # a cor do piso da estacao (o agente usa como destaque)
                await ws.send_text(json.dumps({"evento": "piso_estacao", "dados": cor_para_o_agente(estacao)}))
                if id:
                    # agente 1.14: o nome cadastrado e se ja foi aprovado
                    await ws.send_text(json.dumps({"evento": "estacao_info", "dados": info_para_o_agente(estacao)}))
                continue
            if not estado_recebido and evento in ("ping", "login_cliente"):
                # Agente antigo (< 1.8): volta ao login quando cai e nao manda
                # "estado"; a sessao que ficou aberta e de um PC sem ela
                estado_recebido = True
                await _resolver_estado(db, estacao, None)

            if evento == "ping":
                estacao.ultimo_ping = datetime.utcnow()
                db.commit()
                await ws.send_text(json.dumps({"evento": "pong"}))

            elif evento == "login_cliente":
                login = dados.get("login")
                senha = dados.get("senha")

                # Admin/operador entra direto no modo manutencao
                admin = db.query(Usuario).filter(
                    Usuario.login == login,
                    Usuario.perfil.in_(("admin", "operador")),
                    Usuario.ativo == True
                ).first()
                if admin and verificar_senha(senha, admin.senha_hash):
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": True, "manutencao": True, "admin_nome": admin.nome}
                    }))
                    continue

                if not estacao.aprovada:
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": AGUARDANDO}
                    }))
                    continue

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

                if horario.esta_fechada(horario.carregar(db), horario.agora_local()):
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": horario.FECHADA}
                    }))
                    continue

                # Piso (app/pisos.py): recusa sempre; a liberacao continua
                # valendo para um PC do piso certo
                motivo_piso = recusa_de_piso(cliente, estacao)
                if motivo_piso:
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": motivo_piso}
                    }))
                    continue

                # Tempo do dia (zera a meia-noite de Brasilia; ver tempo_diario.py)
                tempo = reservar_tempo(db, cliente)
                if tempo is None:
                    await ws.send_text(json.dumps({
                        "evento": "login_resultado",
                        "dados": {"ok": False, "motivo": ESGOTADO_CLIENTE}
                    }))
                    continue

                sessao = Sessao(
                    cliente_id=cliente.id,
                    estacao_id=estacao.id,
                    tempo_total_segundos=tempo
                )
                db.add(sessao)
                autorizacao.usado = True
                estacao.status = "ocupada"
                db.commit()
                db.refresh(sessao)

                # os apps ligados no piso desta estacao
                apps_permitidos = apps_do_piso(db, piso_da_estacao(estacao))
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
                        "reiniciar_ao_encerrar": reiniciar,
                        "piso": cor_para_o_agente(estacao),
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
                if motivo == "cliente_encerrou":  # botao do agente 1.5.2
                    motivo = "cliente"
                consumido = dados.get("tempo_consumido_segundos", 0)

                sessao = db.query(Sessao).filter(
                    Sessao.id == sessao_id, Sessao.encerrada_em == None).first()

                if sessao:
                    agora = datetime.utcnow()
                    # Encerrada com o PC sem conexao: o agente manda ao reconectar,
                    # dizendo ha quantos segundos foi (relogio dele, so a diferenca)
                    try:
                        atras = max(0, int(dados.get("segundos_atras") or 0))
                    except (TypeError, ValueError):
                        atras = 0
                    agora = max(sessao.iniciada_em, agora - timedelta(seconds=atras))
                    # Calculo pelo servidor — nao confia no valor do agente
                    _, restante = fechar_tempo_da_sessao(sessao, agora)
                    sessao.sem_conexao_desde = None
                    sessao.encerrada_em = agora
                    sessao.motivo_encerramento = motivo
                    # tempo esgotado zera; manutencao devolve o resto (senao o
                    # cliente ficaria sem tempo o resto do dia)
                    sessao.cliente.saldo_segundos = 0 if motivo == "tempo_esgotado" else restante
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

            # A imagem vem em "dados" ({"evento": ..., "dados": {"imagem": b64}}).
            # Lida do nivel de cima, chegava vazia ao painel.
            elif evento == "captura_tela_resultado":
                imagem_b64 = (dados.get("dados") or {}).get("imagem", "")
                await manager.broadcast_paineis("captura_tela", {"estacao": nome, "imagem": imagem_b64})

            elif evento == "tela_frame":
                imagem_b64 = (dados.get("dados") or {}).get("imagem", "")
                await manager.broadcast_paineis("tela_frame", {"estacao": nome, "imagem": imagem_b64})

    except WebSocketDisconnect:
        desconectou_em = datetime.utcnow()
        db.expire_all()
        nome = _nome_atual(estacao, nome)
        manager.desconectar_estacao(nome, ws)
        # O cliente segue usando no PC: a sessao continua aberta, marcada sem
        # conexao desde agora (o agente retoma ao reconectar)
        db.expire_all()
        aberta = db.query(Sessao).filter(Sessao.estacao_id == estacao.id, Sessao.encerrada_em == None).first()
        if aberta and aberta.sem_conexao_desde is None:
            aberta.sem_conexao_desde = desconectou_em
            db.commit()
        # Espera antes de marcar offline: uma queda rápida de rede não deve
        # fazer a estação "piscar" no painel.
        await asyncio.sleep(SEGUNDOS_ATE_OFFLINE)
        db.expire_all()
        nome = _nome_atual(estacao, nome)
        if not manager.estacao_conectada(nome):
            db.expire_all()
            aberta = db.query(Sessao).filter(Sessao.estacao_id == estacao.id, Sessao.encerrada_em == None).first()
            if estacao.status != "manutencao" and not aberta:
                estacao.status = "desligada"
            db.commit()
            await manager.broadcast_paineis("estacao_offline", {"nome": nome})

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

# ── Painel web ────────────────────────────────────────────────────────────────
# static/ é o build do React (server/frontend → `npm run build`).
_STATIC = os.path.realpath(os.path.join(os.path.dirname(__file__), "static"))

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
        return HTMLResponse("<p>Painel não compilado. Rode <code>npm run build</code> em server/frontend.</p>",
                            status_code=503)
    # index.html sem cache: um build novo aparece no próximo carregamento
    return FileResponse(index, headers={"Cache-Control": "no-store"})
