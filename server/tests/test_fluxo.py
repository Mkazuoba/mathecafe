"""Testes do fluxo principal do MatheCafé.

Rodar de dentro de server/:  python -m pytest -q
Usa um banco SQLite temporário; não toca no cybercafe.db.

A espera de 8s antes de marcar a estação offline não é testada aqui: o
TestClient cancela o handler assim que a conexão fecha. Teste com o
servidor rodando (ver COMO_RODAR.md).
"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/teste.db"
os.environ["BACKUP_PASTA"] = f"{_tmp}/backups"  # o backup diario roda ao subir
os.environ["ADMIN_LOGIN"] = "admin.teste"
os.environ["ADMIN_SENHA"] = "senha-admin-teste"
os.environ["SECRET_KEY"] = "chave-so-dos-testes-" + "x" * 40  # sem gerar server/.secret_key

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Usuario, Sessao
from app.security import hash_senha
from app.websocket_manager import manager


def _login(c, login, senha):
    r = c.post("/api/auth/login", json={"login": login, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin(c):
    return _login(c, "admin.teste", "senha-admin-teste")


@pytest.fixture(scope="module")
def operador(c, admin):
    r = c.post("/api/operadores/", headers=admin,
               json={"login": "operador.teste", "nome": "Operador", "senha": "senha-operador"})
    assert r.status_code == 200, r.text
    return _login(c, "operador.teste", "senha-operador")


_contador = iter(range(1, 1000))


@pytest.fixture
def cenario(c, admin):
    """Uma estação e um cliente novos para cada teste."""
    n = next(_contador)
    estacao = f"PC-{n:02d}"
    assert c.post(f"/api/estacoes/?nome={estacao}", headers=admin).status_code == 200
    cliente = {"login": f"leitor{n}", "nome": f"Leitor {n}", "senha": "senha-leitor"}
    r = c.post("/api/clientes/", headers=admin, json=cliente)
    assert r.status_code == 200, r.text
    return {"estacao": estacao, "cliente": cliente, "cliente_id": r.json()["id"]}


def _logar_no_pc(ws, cliente):
    ws.send_json({"evento": "login_cliente", "login": cliente["login"], "senha": cliente["senha"]})
    return ws.receive_json()["dados"]


def _encerrar_pelo_pc(ws, sessao_id, consumido, motivo="cliente"):
    # O servidor calcula o consumo pelo proprio relogio: recua o inicio da sessao
    db = SessionLocal()
    sessao = db.get(Sessao, sessao_id)
    sessao.iniciada_em = datetime.utcnow() - timedelta(seconds=consumido)
    db.commit()
    db.close()
    ws.send_json({"evento": "sessao_encerrada", "sessao_id": sessao_id,
                  "motivo": motivo, "tempo_consumido_segundos": consumido})
    ws.send_json({"evento": "ping"})
    assert ws.receive_json()["evento"] == "pong"


# ── Fluxo básico ──────────────────────────────────────────────────────────────

def test_liberar_duas_vezes_e_saldo(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        for rodada in (1, 2):
            r = c.post(f"/api/estacoes/fila/{cid}", headers=admin)
            assert r.status_code == 200, f"rodada {rodada}: {r.text}"
            assert c.post(f"/api/estacoes/fila/{cid}", headers=admin).status_code == 400

            dados = _logar_no_pc(ws, cenario["cliente"])
            assert dados["ok"], f"rodada {rodada}: {dados}"
            _encerrar_pelo_pc(ws, dados["sessao_id"], 600)

            saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
            assert saldo == dados["tempo_segundos"] - 600


def test_login_sem_liberacao_e_recusado(c, cenario):
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert not dados["ok"]
        assert "liberação" in dados["motivo"]


def test_operador_cria_e_edita_mas_nao_exclui_cliente(c, admin, operador):
    r = c.post("/api/clientes/", headers=operador,
               json={"login": "novo", "nome": "Novo", "senha": "senha-novo"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert c.put(f"/api/clientes/{cid}", headers=operador, json={"nome": "Novo 2"}).status_code == 200
    assert c.delete(f"/api/clientes/{cid}", headers=operador).status_code == 403
    assert c.delete(f"/api/clientes/{cid}", headers=admin).status_code == 200


# ── 1.1 Saldo ignorado depois que o operador encerra ─────────────────────────

def test_operador_encerra_e_pc_usa_saldo_devolvido(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        _encerrar_pelo_pc(ws, dados["sessao_id"], 1200)  # saldo 6000

        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["tempo_segundos"] == 6000

        r = c.post(f"/api/sessoes/encerrar/{dados['sessao_id']}", headers=admin)
        assert r.status_code == 200
        assert ws.receive_json()["evento"] == "encerrar_sessao"
        saldo_devolvido = r.json()["saldo_restante"]

        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"], dados
        assert abs(dados["tempo_segundos"] - saldo_devolvido) <= 1, \
            f"recebeu {dados['tempo_segundos']}s, esperado o saldo devolvido ({saldo_devolvido}s)"


# ── 1.2 / 1.3 Exclusões com histórico ────────────────────────────────────────

def _criar_historico(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        _encerrar_pelo_pc(ws, dados["sessao_id"], 60)


def _id_estacao(c, admin, nome):
    return next(e["id"] for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == nome)


def test_excluir_cliente_com_historico_pede_desativar(c, admin, cenario):
    _criar_historico(c, admin, cenario)
    r = c.delete(f"/api/clientes/{cenario['cliente_id']}", headers=admin)
    assert r.status_code == 409, r.text
    assert "Desative" in r.json()["detail"]


def test_excluir_estacao_com_historico_desativa_e_mantem_historico(c, admin, cenario):
    _criar_historico(c, admin, cenario)
    nome = cenario["estacao"]
    r = c.delete(f"/api/estacoes/{_id_estacao(c, admin, nome)}", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json().get("desativada") is True
    assert nome not in [e["nome"] for e in c.get("/api/estacoes/", headers=admin).json()]
    assert c.get(f"/api/sessoes/historico?estacao_nome={nome}", headers=admin).json()

    # Cadastrar de novo com o mesmo nome reativa a estação
    assert c.post(f"/api/estacoes/?nome={nome}", headers=admin).status_code == 200
    assert nome in [e["nome"] for e in c.get("/api/estacoes/", headers=admin).json()]


def test_excluir_estacao_sem_historico(c, admin, cenario):
    r = c.delete(f"/api/estacoes/{_id_estacao(c, admin, cenario['estacao'])}", headers=admin)
    assert r.status_code == 200, r.text


def test_excluir_operador_que_ja_liberou_pede_desativar(c, admin, operador, cenario):
    assert c.post(f"/api/estacoes/fila/{cenario['cliente_id']}", headers=operador).status_code == 200
    op_id = next(o["id"] for o in c.get("/api/operadores/", headers=admin).json()
                 if o["login"] == "operador.teste")
    r = c.delete(f"/api/operadores/{op_id}", headers=admin)
    assert r.status_code == 409, r.text
    assert "Desative" in r.json()["detail"]


# ── 1.4 Reconexão ─────────────────────────────────────────────────────────────

def test_conexao_antiga_nao_derruba_a_nova(c, cenario):
    nome = cenario["estacao"]
    # Ordem real de uma queda de rede: o agente abre uma conexão nova
    # antes de o servidor perceber que a antiga morreu.
    antiga = c.websocket_connect(f"/ws/estacao/{nome}").__enter__()
    nova = c.websocket_connect(f"/ws/estacao/{nome}").__enter__()
    antiga.__exit__(None, None, None)
    try:
        assert nome in manager.estacoes_online(), "a queda da conexão antiga removeu a nova"
        nova.send_json({"evento": "ping"})
        assert nova.receive_json()["evento"] == "pong"
    finally:
        nova.__exit__(None, None, None)


def _estado(ws, sessao_id=None):
    """O que o agente manda ao (re)conectar: a sessao em andamento ou nenhuma."""
    ws.send_json({"evento": "estado", "sessao_id": sessao_id})
    return ws.receive_json()


def _sessao_ativa_da(c, admin, estacao):
    return [s for s in c.get("/api/sessoes/ativas", headers=admin).json() if s["estacao_nome"] == estacao]


def test_pc_que_volta_no_login_encerra_a_sessao_e_devolve_saldo(c, admin, cenario):
    """O PC reiniciou (o agente volta sem sessao): a sessao que ficou aberta e
    encerrada, devolvendo ao cliente o tempo nao usado."""
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        assert _estado(ws)["evento"] == "pong"
        assert not _sessao_ativa_da(c, admin, cenario["estacao"])
        saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
        assert saldo >= dados["tempo_segundos"] - 5

        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"], dados
        assert dados["tempo_segundos"] == saldo


def test_servidor_cai_e_o_cliente_continua_na_sessao(c, admin, cenario):
    """O servidor (ou a rede) caiu com o cliente logado: o agente segue a sessao e,
    ao reconectar, ela continua a mesma no servidor."""
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"]
    sid = dados["sessao_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        assert _estado(ws, sid)["evento"] == "pong"
        ativas = _sessao_ativa_da(c, admin, cenario["estacao"])
        assert [s["id"] for s in ativas] == [sid]
        estacao = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == cenario["estacao"])
        assert estacao["status"] == "ocupada"
        assert _sessao(sid).sem_conexao_desde is None  # retomada
        _encerrar_pelo_pc(ws, sid, 300)  # e termina normalmente
        assert _sessao(sid).motivo_encerramento == "cliente"


def test_agente_antigo_que_so_manda_ping_encerra_a_sessao_orfa(c, admin, cenario):
    # agente < 1.8 volta ao login quando cai e reconecta mandando so "ping"
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        assert _logar_no_pc(ws, cenario["cliente"])["ok"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        ws.send_json({"evento": "ping"})
        assert ws.receive_json()["evento"] == "pong"
        assert not _sessao_ativa_da(c, admin, cenario["estacao"])


def test_sessao_encerrada_sem_conexao_conta_ate_o_fim_no_pc(c, admin, cenario):
    """O cliente saiu (ou o tempo acabou) com o servidor fora do ar: o agente manda
    o fim ao reconectar, dizendo ha quanto tempo foi; o uso vai ate la."""
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
    sid = dados["sessao_id"]
    db = SessionLocal()
    db.get(Sessao, sid).iniciada_em = datetime.utcnow() - timedelta(minutes=30)
    db.commit()
    db.close()
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        ws.send_json({"evento": "sessao_encerrada", "sessao_id": sid, "motivo": "cliente", "segundos_atras": 600})
        assert _estado(ws)["evento"] == "pong"
    s = _sessao(sid)
    assert s.motivo_encerramento == "cliente"
    assert abs(s.tempo_consumido_segundos - 1200) <= 3  # 30 min - os 10 em que ja estava encerrada
    saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
    assert abs(saldo - (dados["tempo_segundos"] - 1200)) <= 3


def test_operador_encerrou_enquanto_o_pc_estava_sem_conexao(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        sid = _logar_no_pc(ws, cenario["cliente"])["sessao_id"]
    assert c.post(f"/api/sessoes/encerrar/{sid}", headers=admin).status_code == 200
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        assert _estado(ws, sid)["evento"] == "encerrar_sessao"  # o agente volta ao login
        estacao = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == cenario["estacao"])
        assert estacao["status"] == "livre"


# ── 1.5 Status durante a espera de 8s ────────────────────────────────────────

def test_estacao_nao_aparece_desligada_logo_apos_cair(c, admin, cenario):
    nome = cenario["estacao"]
    with c.websocket_connect(f"/ws/estacao/{nome}"):
        pass
    e = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == nome)
    assert e["status"] == "livre", "dentro dos 8s a estação deve manter o último status"


# ── 1.6 Modo manutenção validado pelo servidor ───────────────────────────────

def test_manutencao_aceita_operador_e_recusa_cliente(c, operador, cenario):
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        ws.send_json({"evento": "validar_manutencao", "login": "operador.teste", "senha": "senha-operador"})
        assert ws.receive_json() == {"evento": "validar_manutencao_resultado", "dados": {"ok": True}}

        ws.send_json({"evento": "validar_manutencao", "login": cenario["cliente"]["login"],
                      "senha": cenario["cliente"]["senha"]})
        assert ws.receive_json()["dados"]["ok"] is False

        ws.send_json({"evento": "validar_manutencao", "login": "operador.teste", "senha": "errada"})
        assert ws.receive_json()["dados"]["ok"] is False


def test_login_de_operador_no_pc_entra_em_manutencao(c, operador, cenario):
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        dados = _logar_no_pc(ws, {"login": "operador.teste", "senha": "senha-operador"})
        assert dados == {"ok": True, "manutencao": True, "admin_nome": "Operador"}

        dados = _logar_no_pc(ws, {"login": "operador.teste", "senha": "errada"})
        assert dados["ok"] is False


def test_cliente_encerra_pelo_botao_e_mantem_saldo(c, admin, cenario):
    # Agente 1.5.2 manda motivo "cliente_encerrou"; o saldo nao pode zerar
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        _encerrar_pelo_pc(ws, dados["sessao_id"], 600, motivo="cliente_encerrou")

    saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
    assert abs(saldo - (dados["tempo_segundos"] - 600)) <= 1


# ── Painel web ────────────────────────────────────────────────────────────────

def test_ws_painel_exige_login(c, admin):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/painel") as ws:
            ws.receive_text()
    token = admin["Authorization"].removeprefix("Bearer ")
    with c.websocket_connect(f"/ws/painel?token={token}"):
        pass  # aceito


def test_rota_de_api_inexistente_continua_404(c, admin):
    r = c.get("/api/nao-existe", headers=admin)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_painel_nao_serve_arquivos_fora_da_pasta(c):
    r = c.get("/..%2Fmain.py")
    assert "from app.main import app" not in r.text


def test_painel_antigo_foi_aposentado(c):
    # /antigo/ agora cai no painel React como qualquer outra rota
    r = c.get("/antigo/")
    assert "static_antigo" not in r.text
    from pathlib import Path
    assert not (Path(__file__).resolve().parent.parent / "app" / "static_antigo").exists()


def test_main_da_raiz_so_reexporta_o_app():
    # server/main.py ja voltou a ser uma copia velha do app inteiro (upload pelo
    # GitHub): quem subisse com `uvicorn main:app` rodaria o codigo antigo
    import main as raiz
    from app.main import app
    assert raiz.app is app


# ── Nome da estação ──────────────────────────────────────────────────────────

def test_estacao_nao_cadastrada_recebe_motivo(c):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as erro:
        with c.websocket_connect("/ws/estacao/PC-QUE-NAO-EXISTE") as ws:
            ws.receive_text()
    assert erro.value.code == 4004


def test_nome_com_espaco_e_acento(c, admin):
    from urllib.parse import quote
    nome = "Sala Leitura 1"
    assert c.post("/api/estacoes/", params={"nome": nome}, headers=admin).status_code == 200
    with c.websocket_connect(f"/ws/estacao/{quote(nome)}") as ws:
        ws.send_json({"evento": "ping"})
        assert ws.receive_json()["evento"] == "pong"
    nome = "Estação 2"
    assert c.post("/api/estacoes/", params={"nome": nome}, headers=admin).status_code == 200
    with c.websocket_connect(f"/ws/estacao/{quote(nome)}") as ws:
        ws.send_json({"evento": "ping"})
        assert ws.receive_json()["evento"] == "pong"


# ── Apps permitidos ──────────────────────────────────────────────────────────

def test_app_exige_caminho_do_exe(c, admin):
    r = c.post("/api/apps/", headers=admin, json={"nome": "Chrome", "processo": "chrome.exe",
               "caminho": r"C:\Program Files\Google\Chrome\Application"})
    assert r.status_code == 400
    assert ".exe" in r.json()["detail"]
    r = c.post("/api/apps/", headers=admin, json={"nome": "Chrome", "processo": "chrome",
               "caminho": r'"C:\Program Files\Google\Chrome\Application\chrome.exe"'})
    assert r.status_code == 200, r.text
    assert r.json()["processo"] == "chrome.exe"
    assert r.json()["caminho"] == r"C:\Program Files\Google\Chrome\Application\chrome.exe"


# ── Auto-update do agente ─────────────────────────────────────────────────────

def test_versao_do_agente_vem_do_agente_dist(c):
    # server/agente_dist/agente.py, não server/app/agente_dist
    dist = os.path.join(os.path.dirname(__file__), "..", "agente_dist", "agente.py")
    with open(dist, encoding="utf-8") as f:
        linhas = [l for l in f if l.startswith("VERSAO")]
    # Duas declaracoes divergentes fazem o agente se atualizar em loop
    assert len(linhas) == 1, linhas
    esperada = linhas[0].partition("=")[2].strip().strip('"')
    r = c.get("/api/agente/versao")
    assert r.json() == {"versao": esperada}
    assert c.get("/api/agente/download").status_code == 200


# ── Migração do SQLite ────────────────────────────────────────────────────────

def test_banco_antigo_ganha_colunas_novas(c, admin):
    # cybercafe.db de antes do Ciclo 5 nao tinha grupos_estacao.cor: a lista de
    # estacoes dava 500 e nenhuma estacao aparecia no painel
    from sqlalchemy import text
    from app.database import engine, _migrar_colunas_faltantes

    piso = c.get("/api/pisos/", headers=admin).json()[0]["id"]
    r = c.post("/api/estacoes/grupos", headers=admin, params={"nome": "Sala antiga", "piso_id": piso})
    assert r.status_code == 200, r.text
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE grupos_estacao DROP COLUMN cor"))
        conn.commit()

    _migrar_colunas_faltantes()

    with engine.connect() as conn:
        colunas = {r[1] for r in conn.execute(text("PRAGMA table_info(grupos_estacao)"))}
    assert "cor" in colunas
    assert c.get("/api/estacoes/", headers=admin).status_code == 200
    grupos = c.get("/api/estacoes/grupos", headers=admin).json()
    assert all(g["cor"] for g in grupos)  # linhas antigas recebem a cor padrao


def test_busca_refinada_de_clientes(c, admin):
    criados = {}
    for login, nome, saldo, ativo in [
        ("bz100200", "Maria Jose da Silva", 0, True),
        ("bz100201", "Joao Silva", 600, True),
        ("xz300", "Silvana Prado", 0, True),
        ("bz100299", "Pedro Inativo", 0, False),
        ("bz100300", "Joana Conceição", 0, True),
    ]:
        r = c.post("/api/clientes/", headers=admin, json={"login": login, "nome": nome, "senha": "x12345"})
        assert r.status_code == 200, r.text
        criados[login] = r.json()["id"]
        # saldo editado vale para hoje (quem nao usou nada hoje tem o tempo cheio)
        r = c.put(f"/api/clientes/{criados[login]}", headers=admin, json={"saldo_segundos": saldo, "ativo": ativo})
        assert r.status_code == 200, r.text

    def logins(**params):
        r = c.get("/api/clientes/", headers=admin, params=params)
        assert r.status_code == 200, r.text
        return [x["login"] for x in r.json()]

    # palavras em qualquer ordem e posicao (antes "maria silva" nao achava nada)
    assert logins(busca="maria silva") == ["bz100200"]
    # sem acento acha com acento, e vice-versa (no SQLite o ILIKE nao ignora acentos)
    assert logins(busca="conceicao") == ["bz100300"]
    assert logins(busca="CONCEIÇÃO", campo="nome") == ["bz100300"]
    assert logins(busca="joana conce", modo="comeca") == ["bz100300"]
    assert logins(busca="silva", campo="login") == []
    assert set(logins(busca="silva", campo="nome")) >= {"bz100200", "bz100201", "xz300"}
    assert sorted(logins(busca="bz1002", campo="login", modo="comeca")) == ["bz100200", "bz100201", "bz100299"]
    assert logins(busca="1002", campo="login", modo="comeca") == []
    assert logins(busca="BZ100201", modo="exato") == ["bz100201"]
    assert sorted(logins(busca="bz1002", status="ativos")) == ["bz100200", "bz100201"]
    assert logins(busca="bz1002", status="inativos") == ["bz100299"]
    assert logins(busca="bz1002", saldo="com") == ["bz100201"]

    # sem termo: vazio no Painel, lista ordenada na aba Clientes
    assert logins() == []
    todos = c.get("/api/clientes/", headers=admin, params={"tudo": True, "ordem": "saldo", "desc": True}).json()
    assert todos[0]["saldo_segundos"] >= 600
    assert logins(busca="bz1002", ordem="login", desc=True) == ["bz100299", "bz100201", "bz100200"]


# ── Tempo do dia: zera a meia-noite (Brasilia) e acaba de verdade ────────────

def _cota(c, admin):
    return c.get("/api/config/", headers=admin).json()["tempo_padrao_segundos"]


def _mudar_dia_do_saldo(cliente_id, saldo, dias_atras):
    from app.tempo_diario import hoje_br
    db = SessionLocal()
    u = db.get(Usuario, cliente_id)
    u.saldo_segundos = saldo
    u.saldo_dia = hoje_br() - timedelta(days=dias_atras)
    db.commit()
    db.close()


def test_dia_vira_a_meia_noite_de_brasilia():
    from datetime import date, timezone
    from app.tempo_diario import hoje_br
    # 01:00 UTC ainda e 22:00 do dia anterior em Sao Paulo (o reset antigo usava UTC)
    assert hoje_br(datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc)) == date(2026, 10, 29)
    assert hoje_br(datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 30)


def test_tempo_do_dia_acaba_e_bloqueia_ate_amanha(c, admin, cenario):
    cid, cota = cenario["cliente_id"], _cota(c, admin)
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        assert c.post(f"/api/estacoes/fila/{cid}", headers=admin).status_code == 200
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"] and dados["tempo_segundos"] == cota
        _encerrar_pelo_pc(ws, dados["sessao_id"], cota, motivo="tempo_esgotado")

        # antes: saldo 0 virava "tempo padrao de novo" e o cliente ganhava mais 2h
        r = c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        assert r.status_code == 400 and "hoje" in r.json()["detail"]
        r = c.post(f"/api/estacoes/{cenario['estacao']}/iniciar_direto", headers=admin, json={"cliente_id": cid})
        assert r.status_code == 400 and "hoje" in r.json()["detail"]

        # o operador ainda pode dar tempo extra editando o saldo
        assert c.put(f"/api/clientes/{cid}", headers=admin, json={"saldo_segundos": 600}).status_code == 200
        assert c.post(f"/api/estacoes/fila/{cid}", headers=admin).status_code == 200
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"] and dados["tempo_segundos"] == 600


def test_sobra_de_ontem_nao_passa_para_hoje(c, admin, cenario):
    cid, cota = cenario["cliente_id"], _cota(c, admin)
    _mudar_dia_do_saldo(cid, 1000, dias_atras=1)
    assert c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"] == cota
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"] and dados["tempo_segundos"] == cota


def test_esgotou_ontem_usa_hoje(c, admin, cenario):
    cid, cota = cenario["cliente_id"], _cota(c, admin)
    _mudar_dia_do_saldo(cid, 0, dias_atras=1)
    assert c.post(f"/api/estacoes/fila/{cid}", headers=admin).status_code == 200
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        assert _logar_no_pc(ws, cenario["cliente"])["tempo_segundos"] == cota


def test_admin_zera_o_tempo_de_hoje(c, admin, operador, cenario):
    cid, cota = cenario["cliente_id"], _cota(c, admin)
    _mudar_dia_do_saldo(cid, 0, dias_atras=0)  # esgotou hoje
    assert c.post(f"/api/estacoes/fila/{cid}", headers=admin).status_code == 400
    assert c.post("/api/config/zerar_tempo_hoje", headers=operador).status_code == 403
    r = c.post("/api/config/zerar_tempo_hoje", headers=admin)
    assert r.status_code == 200 and r.json()["clientes"] >= 1
    assert c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"] == cota
    assert c.post(f"/api/estacoes/fila/{cid}", headers=admin).status_code == 200


def test_manutencao_devolve_o_tempo(c, admin, cenario):
    # com o limite diario, perder o tempo na manutencao bloquearia o cliente o dia todo
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        _encerrar_pelo_pc(ws, dados["sessao_id"], 600, motivo="manutencao")
    assert c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"] == dados["tempo_segundos"] - 600


# ── Historicos: maquinas de um cliente e clientes de uma maquina ─────────────

def test_historico_por_cliente_e_por_estacao(c, admin, operador):
    from app.models import Estacao
    sufixo = next(_contador)
    nomes = [f"HX-{sufixo}-A", f"HX-{sufixo}-B"]
    for n in nomes:
        assert c.post(f"/api/estacoes/?nome={n}", headers=admin).status_code == 200
    ids = []
    for i in (1, 2):
        r = c.post("/api/clientes/", headers=admin,
                   json={"login": f"hx{sufixo}{i}", "nome": f"Hist {i}", "senha": "x12345"})
        ids.append(r.json()["id"])
    db = SessionLocal()
    est = {e.nome: e.id for e in db.query(Estacao).filter(Estacao.nome.in_(nomes))}
    base = datetime(2026, 10, 20, 15, 0)  # 12:00 em Brasilia
    for cliente, estacao, dia, minutos in [
        (ids[0], nomes[0], 0, 30), (ids[0], nomes[0], 1, 60), (ids[0], nomes[1], 2, 10),
        (ids[1], nomes[0], 2, 20),
    ]:
        inicio = base + timedelta(days=dia)
        db.add(Sessao(cliente_id=cliente, estacao_id=est[estacao], tempo_total_segundos=7200,
                      iniciada_em=inicio, encerrada_em=inicio + timedelta(minutes=minutos),
                      tempo_consumido_segundos=minutos * 60, motivo_encerramento="cliente"))
    db.commit()
    db.close()

    # Quais maquinas o cliente ja usou (operador tambem ve)
    r = c.get(f"/api/relatorios/cliente/{ids[0]}", headers=operador)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cliente"]["login"] == f"hx{sufixo}1"
    assert d["sessoes"] == 3 and d["tempo_segundos"] == 100 * 60
    assert [(e["estacao"], e["sessoes"], e["tempo_segundos"]) for e in d["itens"]] == [
        (nomes[1], 1, 600), (nomes[0], 2, 5400)]  # mais recente primeiro
    assert d["itens"][0]["ultima_vez"].startswith("2026-10-22")

    # Quais clientes ja passaram pela maquina
    d = c.get(f"/api/relatorios/estacao/{nomes[0]}", headers=operador).json()
    assert d["sessoes"] == 3 and d["clientes"] == 2
    assert [(x["login"], x["sessoes"]) for x in d["itens"]] == [(f"hx{sufixo}2", 1), (f"hx{sufixo}1", 2)]

    # Periodo em dias de Brasilia: 21/10 a 21/10 pega so a sessao do meio
    d = c.get(f"/api/relatorios/cliente/{ids[0]}", headers=admin,
              params={"de": "2026-10-21", "ate": "2026-10-21"}).json()
    assert d["sessoes"] == 1 and d["itens"][0]["tempo_segundos"] == 3600

    assert c.get("/api/relatorios/cliente/999999", headers=admin).status_code == 404
    assert c.get("/api/relatorios/estacao/nao-existe", headers=admin).status_code == 404


# ── 6.2 Pausa nao conta como uso ─────────────────────────────────────────────

def _recuar(sessao_id, inicio_min, pausa_min=None):
    """Simula o relogio: a sessao comecou ha inicio_min e a pausa ha pausa_min."""
    db = SessionLocal()
    s = db.get(Sessao, sessao_id)
    agora = datetime.utcnow()
    s.iniciada_em = agora - timedelta(minutes=inicio_min)
    if pausa_min is not None:
        s.pausada_em = agora - timedelta(minutes=pausa_min)
    db.commit()
    db.close()


def _sessao(sessao_id):
    db = SessionLocal()
    s = db.get(Sessao, sessao_id)
    db.expunge(s)
    db.close()
    return s


def test_encerrar_sessao_pausada_nao_cobra_a_pausa(c, admin, cenario):
    # 14:00 entra, 14:30 pausa, 15:30 o operador encerra: usou 30 min, nao 1h30
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        sid, total = dados["sessao_id"], dados["tempo_segundos"]
        assert c.post(f"/api/sessoes/pausar/{sid}", headers=admin).status_code == 200
        assert ws.receive_json()["evento"] == "pausar_sessao"
        _recuar(sid, inicio_min=90, pausa_min=60)

        r = c.post(f"/api/sessoes/encerrar/{sid}", headers=admin)
        assert r.status_code == 200
        assert abs(r.json()["saldo_restante"] - (total - 1800)) <= 2, r.json()
    s = _sessao(sid)
    assert abs(s.tempo_consumido_segundos - 1800) <= 2
    assert not s.pausada


def test_pausa_retomada_nao_conta_no_uso(c, admin, cenario):
    # usou 60 min de 100 na parede, com 40 min de pausa retomada; o PC encerra
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        sid, total = dados["sessao_id"], dados["tempo_segundos"]
        c.post(f"/api/sessoes/pausar/{sid}", headers=admin)
        assert ws.receive_json()["evento"] == "pausar_sessao"
        _recuar(sid, inicio_min=100, pausa_min=40)
        assert c.post(f"/api/sessoes/retomar/{sid}", headers=admin).status_code == 200
        assert ws.receive_json()["evento"] == "retomar_sessao"

        ws.send_json({"evento": "sessao_encerrada", "sessao_id": sid, "motivo": "cliente",
                      "tempo_consumido_segundos": 0})
        ws.send_json({"evento": "ping"})
        assert ws.receive_json()["evento"] == "pong"
    s = _sessao(sid)
    assert abs(s.tempo_consumido_segundos - 3600) <= 2, s.tempo_consumido_segundos  # antes: 6000
    assert s.tempo_total_segundos == total  # o tempo concedido, sem a pausa somada
    saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
    assert abs(saldo - (total - 3600)) <= 2


def test_painel_recebe_inicio_da_pausa(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        sid = _logar_no_pc(ws, cenario["cliente"])["sessao_id"]
        c.post(f"/api/sessoes/pausar/{sid}", headers=admin)
        ativa = next(s for s in c.get("/api/sessoes/ativas", headers=admin).json() if s["id"] == sid)
        assert ativa["pausada"] and ativa["pausada_em"]
        c.post(f"/api/sessoes/encerrar/{sid}", headers=admin)


# ── Ficha do cliente: documento, nascimento e foto ───────────────────────────

# JPEG minimo valido (1x1)
_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c"
    "20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100"
    "000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114"
    "328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465"
    "666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9ca"
    "d2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd3ffd9")


def test_ficha_documento_e_nascimento(c, admin, operador):
    r = c.post("/api/clientes/", headers=operador, json={
        "login": "ficha1", "nome": "Ficha Um", "senha": "x12345",
        "documento": "123.456.789-00", "data_nascimento": "2010-05-20"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["documento"] == "123.456.789-00" and d["data_nascimento"] == "2010-05-20"
    assert d["tem_foto"] is False
    cid = d["id"]
    # editar mantem o que nao veio e limpa o que veio vazio
    d = c.put(f"/api/clientes/{cid}", headers=operador, json={"nome": "Ficha 1"}).json()
    assert d["documento"] == "123.456.789-00"
    d = c.put(f"/api/clientes/{cid}", headers=operador, json={"documento": "", "data_nascimento": None}).json()
    assert d["documento"] is None and d["data_nascimento"] is None
    assert c.put(f"/api/clientes/{cid}", headers=operador, json={"data_nascimento": "20/05/2010"}).status_code == 422


def test_foto_do_cliente(c, admin, operador):
    import base64
    cid = c.post("/api/clientes/", headers=admin,
                 json={"login": "foto1", "nome": "Foto Um", "senha": "x12345"}).json()["id"]
    assert c.get(f"/api/clientes/{cid}/foto", headers=operador).status_code == 404

    url = "data:image/jpeg;base64," + base64.b64encode(_JPEG).decode()
    r = c.put(f"/api/clientes/{cid}/foto", headers=operador, json={"imagem": url})
    assert r.status_code == 200, r.text
    assert r.json()["tem_foto"] and r.json()["foto_em"]
    r = c.get(f"/api/clientes/{cid}/foto", headers=operador)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == _JPEG
    assert c.get(f"/api/clientes/{cid}/foto").status_code in (401, 403)  # exige login

    # so imagem de verdade, e nao gigante
    falsa = "data:image/jpeg;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
    assert c.put(f"/api/clientes/{cid}/foto", headers=operador, json={"imagem": falsa}).status_code == 400
    grande = "data:image/jpeg;base64," + base64.b64encode(_JPEG + b"0" * 3_000_000).decode()
    assert c.put(f"/api/clientes/{cid}/foto", headers=operador, json={"imagem": grande}).status_code == 400

    assert c.delete(f"/api/clientes/{cid}/foto", headers=operador).status_code == 200
    assert c.get(f"/api/clientes/{cid}", headers=operador).json()["tem_foto"] is False
    # excluir o cliente leva a foto junto
    c.put(f"/api/clientes/{cid}/foto", headers=operador, json={"imagem": url})
    assert c.delete(f"/api/clientes/{cid}", headers=admin).status_code == 200


# ── Captura de tela e acesso remoto (ver a tela ao vivo) ─────────────────────

def _receber_no_painel(ws, evento):
    for _ in range(20):
        msg = ws.receive_json()
        if msg["evento"] == evento:
            return msg
    raise AssertionError(f"painel nao recebeu {evento}")


def test_captura_e_tela_ao_vivo_chegam_ao_painel(c, admin, cenario):
    # O agente manda a imagem em "dados"; o servidor lia do nivel de cima e
    # repassava ao painel uma imagem vazia (captura e acesso remoto em branco)
    token = admin["Authorization"].split()[1]
    with c.websocket_connect(f"/ws/painel?token={token}") as painel, \
         c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as pc:
        pc.send_json({"evento": "ping"})
        assert pc.receive_json()["evento"] == "pong"

        assert c.post(f"/api/estacoes/{cenario['estacao']}/capturar_tela", headers=admin).status_code == 200
        assert pc.receive_json()["evento"] == "capturar_tela"
        pc.send_json({"evento": "captura_tela_resultado", "dados": {"imagem": "QUJD"}})
        msg = _receber_no_painel(painel, "captura_tela")
        assert msg["dados"] == {"estacao": cenario["estacao"], "imagem": "QUJD"}

        assert c.post(f"/api/estacoes/{cenario['estacao']}/iniciar_streaming", headers=admin).status_code == 200
        assert pc.receive_json()["evento"] == "iniciar_streaming"
        pc.send_json({"evento": "tela_frame", "dados": {"imagem": "RlJBTUU="}})
        assert _receber_no_painel(painel, "tela_frame")["dados"]["imagem"] == "RlJBTUU="
        c.post(f"/api/estacoes/{cenario['estacao']}/parar_streaming", headers=admin)
        assert pc.receive_json()["evento"] == "parar_streaming"


# ── 6.3 Sessao presa depois de reiniciar o servidor ──────────────────────────

def _sessao_aberta(cenario, inicio_min):
    from app.models import Estacao
    from app.tempo_diario import reservar_tempo
    db = SessionLocal()
    est = db.query(Estacao).filter(Estacao.nome == cenario["estacao"]).one()
    est.status = "ocupada"
    s = Sessao(cliente_id=cenario["cliente_id"], estacao_id=est.id, tempo_total_segundos=7200,
               iniciada_em=datetime.utcnow() - timedelta(minutes=inicio_min))
    db.add(s)
    reservar_tempo(db, db.get(Usuario, cenario["cliente_id"]))  # como o login no PC faz
    db.commit()
    sid = s.id
    db.close()
    return sid


def _batimento(minutos_atras):
    from app.models import ConfiguracaoSistema
    db = SessionLocal()
    cfg = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == "servidor_vivo_em").first()
    if minutos_atras is None:
        if cfg:
            db.delete(cfg)
    else:
        valor = (datetime.utcnow() - timedelta(minutes=minutos_atras)).isoformat()
        if cfg:
            cfg.valor = valor
        else:
            db.add(ConfiguracaoSistema(chave="servidor_vivo_em", valor=valor))
    db.commit()
    db.close()


def test_servidor_reinicia_e_mantem_a_sessao_aberta(c, admin, cenario):
    # Comecou ha 90 min e o servidor caiu ha 30 (ultimo batimento). O cliente
    # continua usando no PC: a sessao fica aberta, marcada sem conexao desde a queda.
    from app.main import marcar_sessoes_sem_conexao
    sid = _sessao_aberta(cenario, inicio_min=90)
    _batimento(30)
    db = SessionLocal()
    assert marcar_sessoes_sem_conexao(db) >= 1
    db.close()
    s = _sessao(sid)
    assert s.encerrada_em is None
    assert abs((datetime.utcnow() - s.sem_conexao_desde).total_seconds() - 1800) <= 5
    assert any(x["id"] == sid for x in c.get("/api/sessoes/ativas", headers=admin).json())


def test_sem_batimento_a_queda_conta_desde_o_inicio(c, admin, cenario):
    # sem saber quando o servidor caiu, um PC que nunca voltar nao paga nada
    from app.main import marcar_sessoes_sem_conexao
    sid = _sessao_aberta(cenario, inicio_min=50)
    _batimento(None)
    db = SessionLocal()
    marcar_sessoes_sem_conexao(db)
    db.close()
    s = _sessao(sid)
    assert s.sem_conexao_desde == s.iniciada_em


def test_pc_que_nunca_volta_encerra_quando_o_tempo_acabaria(c, admin, cenario):
    # 2h concedidas, comecou ha 130 min, caiu aos 30 min de uso: o tempo ja teria
    # acabado. Encerra cobrando so ate a queda e devolve o resto.
    from app.main import encerrar_sessoes_vencidas
    sid = _sessao_aberta(cenario, inicio_min=130)
    db = SessionLocal()
    db.get(Sessao, sid).sem_conexao_desde = datetime.utcnow() - timedelta(minutes=100)
    db.commit()
    assert encerrar_sessoes_vencidas(db, datetime.utcnow()) >= 1
    db.close()
    s = _sessao(sid)
    assert s.encerrada_em is not None and s.motivo_encerramento == "conexao_perdida"
    assert abs(s.tempo_consumido_segundos - 1800) <= 3
    saldo = c.get(f"/api/clientes/{cenario['cliente_id']}", headers=admin).json()["saldo_segundos"]
    assert abs(saldo - 5400) <= 3


def test_sessao_sem_conexao_com_tempo_sobrando_continua(c, admin, cenario):
    from app.main import encerrar_sessoes_vencidas
    sid = _sessao_aberta(cenario, inicio_min=40)
    db = SessionLocal()
    db.get(Sessao, sid).sem_conexao_desde = datetime.utcnow() - timedelta(minutes=10)
    db.commit()
    encerrar_sessoes_vencidas(db, datetime.utcnow())
    db.close()
    assert _sessao(sid).encerrada_em is None


# ── Programacao da biblioteca (carrossel no agente) ──────────────────────────

def test_programacao_admin_cadastra_e_agente_ve(c, admin, operador, cenario):
    import base64
    url = "data:image/jpeg;base64," + base64.b64encode(_JPEG).decode()
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as pc:
        pc.send_json({"evento": "ping"})
        assert pc.receive_json()["evento"] == "pong"

        assert c.post("/api/programacao/", headers=operador, json={"titulo": "x", "imagem": url}).status_code == 403
        r1 = c.post("/api/programacao/", headers=admin, json={"titulo": "Oficina de HQ", "imagem": url})
        assert r1.status_code == 200, r1.text
        assert pc.receive_json()["evento"] == "programacao_atualizada"  # o agente recarrega
        r2 = c.post("/api/programacao/", headers=admin, json={"titulo": "Contacao de historias", "imagem": url})
        assert pc.receive_json()["evento"] == "programacao_atualizada"
        id1, id2 = r1.json()["id"], r2.json()["id"]

        # o agente nao tem login: lista e imagens sao abertas
        d = c.get("/api/programacao/agente").json()
        assert d["segundos"] >= 3
        ids = [i["id"] for i in d["itens"]]
        assert ids.index(id1) < ids.index(id2)
        img = c.get(f"/api/programacao/{id1}/imagem")
        assert img.status_code == 200 and img.content == _JPEG and img.headers["content-type"] == "image/jpeg"

        # reordenar, desativar e apagar
        assert c.put("/api/programacao/ordem", headers=admin, json={"ids": [id2, id1]}).status_code == 200
        pc.receive_json()
        ids = [i["id"] for i in c.get("/api/programacao/agente").json()["itens"]]
        assert ids.index(id2) < ids.index(id1)
        assert c.put(f"/api/programacao/{id2}", headers=admin, json={"ativo": False}).status_code == 200
        pc.receive_json()
        assert id2 not in [i["id"] for i in c.get("/api/programacao/agente").json()["itens"]]
        assert any(i["id"] == id2 for i in c.get("/api/programacao/", headers=operador).json()["itens"])
        assert c.delete(f"/api/programacao/{id2}", headers=admin).status_code == 200
        pc.receive_json()
        assert c.get(f"/api/programacao/{id2}/imagem").status_code == 404

    # so imagem de verdade
    falsa = "data:image/png;base64," + base64.b64encode(b"nao sou imagem").decode()
    assert c.post("/api/programacao/", headers=admin, json={"titulo": "x", "imagem": falsa}).status_code == 400
    # tempo de cada cartaz
    assert c.put("/api/programacao/config", headers=admin, json={"segundos": 15}).status_code == 200
    assert c.get("/api/programacao/agente").json()["segundos"] == 15
    assert c.put("/api/programacao/config", headers=admin, json={"segundos": 1}).status_code == 422


def test_banco_do_servidor_pelo_painel(c, admin, operador, tmp_path, monkeypatch):
    from app.routers import config as rota
    h = admin
    assert c.get("/api/config/banco", headers=operador).status_code == 403

    atual = c.get("/api/config/banco", headers=h).json()
    assert atual["tipo"] == "SQLite"
    # nos testes a URL vem da variável de ambiente: o .env não manda nela
    assert atual["no_ambiente"] is True

    # banco novo: conecta, mas está vazio
    novo = f"sqlite:///{(tmp_path / 'novo.db').as_posix()}"
    r = c.post("/api/config/banco/testar", json={"url": novo}, headers=h).json()
    assert r["ok"] and r["vazio"] is True
    # o banco atual já tem os dados do MatheCafé
    r = c.post("/api/config/banco/testar", json={"url": os.environ["DATABASE_URL"]}, headers=h).json()
    assert r["ok"] and r["vazio"] is False
    # servidor fora do ar: erro sem mostrar a senha
    r = c.post("/api/config/banco/testar", json={"url": "postgresql://u:senhasecreta@127.0.0.1:1/x"}, headers=h).json()
    assert not r["ok"] and "senhasecreta" not in r["mensagem"]
    assert c.post("/api/config/banco/testar", json={"url": "abc"}, headers=h).status_code == 400

    # com DATABASE_URL no ambiente (Render), gravar no .env não adiantaria
    assert c.put("/api/config/banco", json={"url": novo}, headers=h).status_code == 409

    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=abc\n", encoding="utf-8")
    monkeypatch.setattr(rota, "banco_no_ambiente", lambda: False)
    monkeypatch.setattr(rota, "ARQUIVO_ENV", env)
    assert c.put("/api/config/banco", json={"url": "postgresql://u:senhasecreta@127.0.0.1:1/x"},
                 headers=h).status_code == 400  # não grava um banco que não conecta
    r = c.put("/api/config/banco", json={"url": novo}, headers=h)
    assert r.status_code == 200 and r.json()["reiniciar"] is True
    assert env.read_text(encoding="utf-8") == f"SECRET_KEY=abc\nDATABASE_URL={novo}\n"


def test_agente_que_reabre_sai_da_manutencao(c, admin, cenario):
    # Agente fechado (ou reiniciado) no modo manutencao volta na tela de login,
    # mas o banco seguia "manutencao": painel travado e login recusado com
    # "Estacao nao esta disponivel"
    from app.models import Estacao
    db = SessionLocal()
    db.query(Estacao).filter(Estacao.nome == cenario["estacao"]).update({Estacao.status: "manutencao"})
    db.commit()
    db.close()
    # desligado, continua aparecendo em manutencao
    lista = {e["nome"]: e for e in c.get("/api/estacoes/", headers=admin).json()}
    assert lista[cenario["estacao"]]["status"] == "manutencao"

    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        ws.send_json({"evento": "ping"})
        assert ws.receive_json()["evento"] == "pong"
        lista = {e["nome"]: e for e in c.get("/api/estacoes/", headers=admin).json()}
        assert lista[cenario["estacao"]]["status"] == "livre"

        assert c.post(f"/api/estacoes/fila/{cenario['cliente_id']}", headers=admin).status_code == 200
        assert _logar_no_pc(ws, cenario["cliente"])["ok"]


def test_backup_pelo_painel(c, admin, operador, tmp_path, monkeypatch):
    from app.routers import config as rota
    monkeypatch.setattr(rota, "PASTA_BACKUP", tmp_path)
    assert c.get("/api/config/backup", headers=operador).status_code == 403
    assert c.post("/api/config/backup", headers=operador).status_code == 403

    info = c.get("/api/config/backup", headers=admin).json()
    assert info["ativo"] is True and info["backups"] == [] and info["dias"] >= 1

    r = c.post("/api/config/backup", headers=admin)
    assert r.status_code == 200, r.text
    nome = r.json()["nome"]
    assert [b["nome"] for b in c.get("/api/config/backup", headers=admin).json()["backups"]] == [nome]

    baixado = c.get(f"/api/config/backup/{nome}", headers=admin)
    assert baixado.status_code == 200 and baixado.content.startswith(b"SQLite format 3")
    assert c.get(f"/api/config/backup/{nome}", headers=operador).status_code == 403
    # só nomes de backup: nada de sair da pasta
    for ruim in ("..%2F.env", "cybercafe.db", "outro-2026-11-05-0001.db"):
        assert c.get(f"/api/config/backup/{ruim}", headers=admin).status_code == 404


# ── 4.7 Pisos (cadastrados no sistema; o mapa/grupo e o cliente pertencem a um) ──

def _pisos(c, admin):
    return {p["nome"]: p for p in c.get("/api/pisos/", headers=admin).json()}


def _id_piso(c, admin, nome):
    return _pisos(c, admin)[nome]["id"]


def _estacao_infantil(c, admin):
    """Estação nova num grupo do piso Infantil."""
    infantil = _id_piso(c, admin, "Infantil")
    r = c.post(f"/api/estacoes/grupos?nome=Sala%20Infantil&piso_id={infantil}", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["piso_id"] == infantil
    nome = f"INF-{next(_contador):02d}"
    r = c.post(f"/api/estacoes/?nome={nome}&grupo_id={r.json()['id']}", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["piso_id"] == infantil
    return nome


def _cliente_infantil(c, admin):
    n = next(_contador)
    cliente = {"login": f"crianca{n}", "nome": f"Crianca {n}", "senha": "senha-crianca",
               "piso_id": _id_piso(c, admin, "Infantil")}
    r = c.post("/api/clientes/", headers=admin, json=cliente)
    assert r.status_code == 200, r.text
    assert r.json()["piso_nome"] == "Infantil"
    return cliente, r.json()["id"]


def test_adulto_e_infantil_ja_existem_e_adulto_e_o_padrao(c, admin):
    pisos = _pisos(c, admin)
    assert pisos["Adulto"]["padrao"] and not pisos["Infantil"]["padrao"]
    assert pisos["Adulto"]["cor"].startswith("#")


def test_cliente_e_estacao_sem_grupo_ficam_no_piso_padrao(c, admin, cenario):
    adulto = _id_piso(c, admin, "Adulto")
    cliente = c.get(f"/api/clientes/{cenario['cliente_id']}", headers=admin).json()
    assert cliente["piso_id"] == adulto  # gravado no cadastro, nao so "vazio = padrao"
    estacoes = {e["nome"]: e for e in c.get("/api/estacoes/", headers=admin).json()}
    assert estacoes[cenario["estacao"]]["piso_id"] == adulto  # sem grupo


def test_criar_renomear_e_excluir_piso(c, admin, operador):
    assert c.post("/api/pisos/", headers=operador, json={"nome": "Juvenil", "cor": "#22c55e"}).status_code == 403
    r = c.post("/api/pisos/", headers=admin, json={"nome": "Juvenil", "cor": "#22c55e"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert c.post("/api/pisos/", headers=admin, json={"nome": "juvenil", "cor": "#000000"}).status_code == 400
    assert c.post("/api/pisos/", headers=admin, json={"nome": "Cor ruim", "cor": "verde"}).status_code == 422
    r = c.put(f"/api/pisos/{pid}", headers=admin, json={"nome": "Juvenil 2"})
    assert r.status_code == 200 and r.json()["nome"] == "Juvenil 2"
    assert c.delete(f"/api/pisos/{pid}", headers=admin).status_code == 200
    assert "Juvenil 2" not in _pisos(c, admin)


def test_piso_em_uso_ou_padrao_nao_se_exclui(c, admin):
    _cliente_infantil(c, admin)
    r = c.delete(f"/api/pisos/{_id_piso(c, admin, 'Infantil')}", headers=admin)
    assert r.status_code == 400 and "cliente" in r.json()["detail"]
    r = c.delete(f"/api/pisos/{_id_piso(c, admin, 'Adulto')}", headers=admin)
    assert r.status_code == 400


def test_trocar_o_piso_padrao(c, admin):
    r = c.post("/api/pisos/", headers=admin, json={"nome": "Temporario", "cor": "#123456"})
    pid = r.json()["id"]
    assert c.put(f"/api/pisos/{pid}", headers=admin, json={"padrao": True}).status_code == 200
    pisos = _pisos(c, admin)
    assert pisos["Temporario"]["padrao"] and not pisos["Adulto"]["padrao"]  # so um padrao
    c.put(f"/api/pisos/{pisos['Adulto']['id']}", headers=admin, json={"padrao": True})
    assert c.delete(f"/api/pisos/{pid}", headers=admin).status_code == 200


def test_mapa_novo_exige_piso(c, admin):
    assert c.post("/api/estacoes/grupos?nome=Sem%20piso", headers=admin).status_code == 422
    assert c.post("/api/estacoes/grupos?nome=X&piso_id=99999", headers=admin).status_code == 400


def test_mapa_antigo_sem_piso_aparece_como_sem_piso(c, admin):
    from app.models import GrupoEstacao
    db = SessionLocal()
    g = GrupoEstacao(nome="Mapa antigo")  # como os grupos criados antes dos pisos
    db.add(g)
    db.commit()
    gid = g.id
    db.close()
    grupo = next(x for x in c.get("/api/estacoes/grupos", headers=admin).json() if x["id"] == gid)
    assert grupo["piso_id"] is None  # o painel avisa: escolha o piso deste mapa


def test_piso_inexistente_e_recusado_no_cliente(c, admin, cenario):
    r = c.put(f"/api/clientes/{cenario['cliente_id']}", headers=admin, json={"piso_id": 99999})
    assert r.status_code == 400


def test_trocar_piso_registra_quem_trocou(c, admin, operador, cenario):
    cid = cenario["cliente_id"]
    r = c.put(f"/api/clientes/{cid}", headers=operador, json={"nome": "Outro nome"})
    assert r.json()["piso_alterado_por"] is None  # editar outra coisa nao conta
    r = c.put(f"/api/clientes/{cid}", headers=operador, json={"piso_id": _id_piso(c, admin, "Infantil")})
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["piso_nome"] == "Infantil"
    assert dados["piso_alterado_por"] == "Operador"
    assert dados["piso_alterado_em"]


def test_grupo_troca_de_piso(c, admin):
    nome = _estacao_infantil(c, admin)
    adulto = _id_piso(c, admin, "Adulto")
    estacao = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == nome)
    r = c.put(f"/api/estacoes/grupos/{estacao['grupo_id']}", headers=admin, json={"piso_id": adulto})
    assert r.status_code == 200 and r.json()["piso_id"] == adulto
    estacao = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == nome)
    assert estacao["piso_id"] == adulto


def test_crianca_nao_loga_no_pc_do_adulto(c, admin, cenario):
    cliente, cid = _cliente_infantil(c, admin)
    c.post(f"/api/estacoes/fila/{cid}", headers=admin)
    fila = {a["cliente_id"]: a for a in c.get("/api/estacoes/fila", headers=admin).json()}
    assert fila[cid]["cliente_piso_id"] == _id_piso(c, admin, "Infantil")
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        dados = _logar_no_pc(ws, cliente)
        assert not dados["ok"]
        assert "Infantil" in dados["motivo"]
    # a liberacao continua valendo para um PC do piso certo
    with c.websocket_connect(f"/ws/estacao/{_estacao_infantil(c, admin)}") as ws:
        dados = _logar_no_pc(ws, cliente)
        assert dados["ok"], dados
        _encerrar_pelo_pc(ws, dados["sessao_id"], 60)


def test_adulto_nao_loga_no_pc_do_infantil(c, admin, cenario):
    c.post(f"/api/estacoes/fila/{cenario['cliente_id']}", headers=admin)
    with c.websocket_connect(f"/ws/estacao/{_estacao_infantil(c, admin)}") as ws:
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert not dados["ok"]
        assert "Adulto" in dados["motivo"]


def test_iniciar_direto_recusa_outro_piso(c, admin, cenario):
    _, cid = _cliente_infantil(c, admin)
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}"):
        r = c.post(f"/api/estacoes/{cenario['estacao']}/iniciar_direto", headers=admin, json={"cliente_id": cid})
        assert r.status_code == 400
        assert "Infantil" in r.json()["detail"]
        estacao = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == cenario["estacao"])
        assert estacao["status"] == "livre"


def test_busca_de_clientes_filtra_pelo_piso(c, admin):
    cliente, cid = _cliente_infantil(c, admin)
    def ids(piso_id):
        r = c.get(f"/api/clientes/?busca={cliente['login']}&piso_id={piso_id}", headers=admin)
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()]
    assert ids(_id_piso(c, admin, "Infantil")) == [cid]
    assert ids(_id_piso(c, admin, "Adulto")) == []
    r = c.get(f"/api/clientes/?busca={cliente['login']}", headers=admin)  # sem piso: todos
    assert [x["id"] for x in r.json()] == [cid]


def test_piso_de_texto_do_4_7a_vira_piso_id(c, admin, cenario):
    # o 4.7a gravava o piso como texto (usuarios.piso = "infantil"); ao subir, vira piso_id
    from sqlalchemy import text
    from app.database import engine
    from app.pisos import garantir_pisos
    with engine.connect() as conn:
        colunas = {r[1] for r in conn.execute(text("PRAGMA table_info(usuarios)"))}
        if "piso" not in colunas:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN piso VARCHAR(10)"))
        conn.execute(text("UPDATE usuarios SET piso = 'infantil', piso_id = NULL WHERE id = :id"),
                     {"id": cenario["cliente_id"]})
        conn.commit()
    db = SessionLocal()
    garantir_pisos(db)
    db.commit()
    db.close()
    cliente = c.get(f"/api/clientes/{cenario['cliente_id']}", headers=admin).json()
    assert cliente["piso_nome"] == "Infantil"


def test_teste_de_conexao_nao_encerra_a_sessao(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        sid = _logar_no_pc(ws, cenario["cliente"])["sessao_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:  # Configurar conexao -> Testar
        ws.send_json({"evento": "teste_conexao"})
        assert ws.receive_json()["evento"] == "pong"
    assert _sessao(sid).encerrada_em is None


# ── 7.1 / 7.2 Desligar pelo painel e acoes em massa ──────────────────────────

def _estacao_nova(c, admin):
    nome = f"PC-{next(_contador):02d}"
    assert c.post(f"/api/estacoes/?nome={nome}", headers=admin).status_code == 200
    return nome


def test_desligar_pc_encerra_a_sessao_e_manda_o_comando(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        r = c.post(f"/api/estacoes/{cenario['estacao']}/desligar", headers=admin)
        assert r.status_code == 200, r.text
        assert ws.receive_json()["evento"] == "desligar_pc"
    s = _sessao(dados["sessao_id"])
    assert s.encerrada_em is not None and s.motivo_encerramento == "operador"
    saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
    assert saldo >= dados["tempo_segundos"] - 5  # o tempo que sobrou volta


def test_reiniciar_tambem_encerra_a_sessao(c, admin, cenario):
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        sid = _logar_no_pc(ws, cenario["cliente"])["sessao_id"]
        assert c.post(f"/api/estacoes/{cenario['estacao']}/reiniciar", headers=admin).status_code == 200
        assert ws.receive_json()["evento"] == "reiniciar_pc"
    assert _sessao(sid).motivo_encerramento == "operador"


def test_desligar_estacao_offline_e_recusado(c, admin, cenario):
    r = c.post(f"/api/estacoes/{cenario['estacao']}/desligar", headers=admin)
    assert r.status_code == 400


def test_acao_em_massa_diz_o_resultado_de_cada_estacao(c, operador, admin, cenario):
    offline = _estacao_nova(c, admin)
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        _estado(ws)
        r = c.post("/api/estacoes/acoes", headers=operador, json={
            "acao": "mensagem", "texto": "A biblioteca fecha em 10 minutos",
            "estacoes": [cenario["estacao"], offline, "NAO-EXISTE"]})
        assert r.status_code == 200, r.text
        res = r.json()["resultados"]
        assert res[cenario["estacao"]] == "ok"
        assert "offline" in res[offline].lower()
        assert "encontrada" in res["NAO-EXISTE"]
        msg = ws.receive_json()
        assert msg["evento"] == "mensagem_tela" and msg["dados"]["texto"] == "A biblioteca fecha em 10 minutos"


def test_desligar_em_massa(c, admin, cenario):
    outra = _estacao_nova(c, admin)
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as a, \
            c.websocket_connect(f"/ws/estacao/{outra}") as b:
        _estado(a)
        _estado(b)
        r = c.post("/api/estacoes/acoes", headers=admin,
                   json={"acao": "desligar", "estacoes": [cenario["estacao"], outra]})
        assert r.json()["resultados"] == {cenario["estacao"]: "ok", outra: "ok"}
        assert a.receive_json()["evento"] == "desligar_pc"
        assert b.receive_json()["evento"] == "desligar_pc"


def test_encerrar_em_massa_so_onde_ha_sessao(c, admin, cenario):
    vazia = _estacao_nova(c, admin)
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws, \
            c.websocket_connect(f"/ws/estacao/{vazia}") as ws2:
        _estado(ws2)
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        sid = _logar_no_pc(ws, cenario["cliente"])["sessao_id"]
        r = c.post("/api/estacoes/acoes", headers=admin,
                   json={"acao": "encerrar", "estacoes": [cenario["estacao"], vazia]})
        res = r.json()["resultados"]
        assert res[cenario["estacao"]] == "ok"
        assert "sess" in res[vazia].lower()
        assert ws.receive_json()["evento"] == "encerrar_sessao"
    assert _sessao(sid).motivo_encerramento == "operador"


def test_acao_em_massa_invalida(c, admin, cenario):
    r = c.post("/api/estacoes/acoes", headers=admin, json={"acao": "formatar", "estacoes": [cenario["estacao"]]})
    assert r.status_code == 422
    r = c.post("/api/estacoes/acoes", headers=admin, json={"acao": "mensagem", "estacoes": [cenario["estacao"]]})
    assert r.status_code == 400  # mensagem sem texto


# ── 8.3 E-mail no cadastro ───────────────────────────────────────────────────

def test_email_no_cadastro_do_cliente(c, admin):
    n = next(_contador)
    r = c.post("/api/clientes/", headers=admin, json={
        "login": f"comemail{n}", "nome": "Com Email", "senha": "senha-x", "email": "  Leitor@Exemplo.com.br "})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["email"] == "leitor@exemplo.com.br"
    r = c.put(f"/api/clientes/{cid}", headers=admin, json={"email": "outro@exemplo.com"})
    assert r.json()["email"] == "outro@exemplo.com"
    r = c.put(f"/api/clientes/{cid}", headers=admin, json={"email": ""})  # vazio apaga
    assert r.json()["email"] is None
    r = c.put(f"/api/clientes/{cid}", headers=admin, json={"nome": "Sem mexer no email"})
    assert r.json()["email"] is None


def test_email_invalido_e_recusado(c, admin, cenario):
    r = c.put(f"/api/clientes/{cenario['cliente_id']}", headers=admin, json={"email": "sem-arroba"})
    assert r.status_code == 422


# ── 8.4 Horario de funcionamento ─────────────────────────────────────────────

def _semana(abre="08:00", fecha="20:00", aberto=True):
    return [{"aberto": aberto, "abre": abre, "fecha": fecha} for _ in range(7)]


def test_horario_comeca_desligado_e_se_configura(c, admin, operador):
    r = c.get("/api/config/horario", headers=admin)
    assert r.status_code == 200
    assert r.json()["ativo"] is False and len(r.json()["dias"]) == 7
    assert c.get("/api/config/horario", headers=operador).status_code == 403
    dias = _semana()
    dias[6] = {"aberto": False, "abre": "08:00", "fecha": "20:00"}  # domingo fechado
    dias[5] = {"aberto": True, "abre": "09:00", "fecha": "16:00"}
    try:
        r = c.put("/api/config/horario", headers=admin, json={"ativo": True, "dias": dias})
        assert r.status_code == 200, r.text
        assert c.get("/api/config/horario", headers=admin).json() == {"ativo": True, "dias": dias}
    finally:
        c.put("/api/config/horario", headers=admin, json={"ativo": False, "dias": _semana()})


def test_horario_invalido_e_recusado(c, admin):
    ruins = [
        {"ativo": True, "dias": _semana()[:6]},                      # faltando um dia
        {"ativo": True, "dias": _semana(abre="20:00", fecha="08:00")},  # fecha antes de abrir
        {"ativo": True, "dias": _semana(fecha="25:00")},
    ]
    for corpo in ruins:
        assert c.put("/api/config/horario", headers=admin, json=corpo).status_code == 422, corpo


def test_decide_avisar_e_encerrar_pelo_relogio():
    from app.horario import decidir
    horario = {"ativo": True, "dias": _semana(fecha="20:00")}
    dia = datetime(2026, 11, 9)  # segunda
    avisados = set()
    assert decidir(horario, dia.replace(hour=15), avisados) == {"aviso": None, "encerrar": False}
    d = decidir(horario, dia.replace(hour=19, minute=51), avisados)
    assert d == {"aviso": 10, "encerrar": False}
    assert decidir(horario, dia.replace(hour=19, minute=52), avisados)["aviso"] is None  # uma vez so
    assert decidir(horario, dia.replace(hour=19, minute=55), avisados)["aviso"] == 5
    assert decidir(horario, dia.replace(hour=20), avisados) == {"aviso": None, "encerrar": True}
    assert decidir(horario, dia.replace(hour=7), avisados)["encerrar"] is True  # antes de abrir
    # desligado: nunca avisa nem encerra
    assert decidir({"ativo": False, "dias": _semana()}, dia.replace(hour=23), set())["encerrar"] is False
    # dia fechado
    fechado = {"ativo": True, "dias": _semana(aberto=False)}
    assert decidir(fechado, dia.replace(hour=12), set())["encerrar"] is True


def test_no_fechamento_encerra_e_devolve_o_tempo(c, admin, cenario):
    from app.horario import encerrar_sessoes_do_fechamento
    sid = _sessao_aberta(cenario, inicio_min=30)
    db = SessionLocal()
    encerradas = encerrar_sessoes_do_fechamento(db)
    db.close()
    assert cenario["estacao"] in [e for e, _ in encerradas]
    s = _sessao(sid)
    assert s.motivo_encerramento == "horario"
    assert abs(s.tempo_consumido_segundos - 1800) <= 3
    saldo = c.get(f"/api/clientes/{cenario['cliente_id']}", headers=admin).json()["saldo_segundos"]
    assert abs(saldo - 5400) <= 3


def test_biblioteca_fechada_recusa_login_e_liberar_direto(c, admin, cenario):
    cid = cenario["cliente_id"]
    try:
        assert c.put("/api/config/horario", headers=admin,
                     json={"ativo": True, "dias": _semana(aberto=False)}).status_code == 200
        with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
            _estado(ws)
            c.post(f"/api/estacoes/fila/{cid}", headers=admin)
            dados = _logar_no_pc(ws, cenario["cliente"])
            assert not dados["ok"] and "fechada" in dados["motivo"]
            r = c.post(f"/api/estacoes/{cenario['estacao']}/iniciar_direto", headers=admin, json={"cliente_id": cid})
            assert r.status_code == 400 and "fechada" in r.json()["detail"]
    finally:
        c.put("/api/config/horario", headers=admin, json={"ativo": False, "dias": _semana()})


# ── 8.1 Registro de acoes dos operadores ─────────────────────────────────────

def _acoes(c, admin, **filtros):
    r = c.get("/api/relatorios/acoes", headers=admin, params=filtros)
    assert r.status_code == 200, r.text
    return r.json()


def test_acoes_do_operador_ficam_registradas(c, admin, operador, cenario):
    cid = cenario["cliente_id"]
    login = cenario["cliente"]["login"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        _estado(ws)
        assert c.post(f"/api/estacoes/fila/{cid}", headers=operador).status_code == 200
        sid = _logar_no_pc(ws, cenario["cliente"])["sessao_id"]
        assert c.post(f"/api/sessoes/encerrar/{sid}", headers=operador).status_code == 200
        ws.receive_json()  # encerrar_sessao
        assert c.put(f"/api/clientes/{cid}", headers=operador, json={"saldo_segundos": 3600}).status_code == 200
        assert c.post(f"/api/estacoes/{cenario['estacao']}/mensagem", headers=operador,
                      json={"texto": "Oi"}).status_code == 200
    acoes = _acoes(c, admin, cliente=login)
    feitas = [a["acao"] for a in acoes]
    assert {"liberar", "encerrar_sessao", "tempo_extra"} <= set(feitas)
    a = next(x for x in acoes if x["acao"] == "tempo_extra")
    assert a["operador"] == "Operador" and a["cliente_login"] == login and "01:00:00" in a["detalhe"]
    enc = next(x for x in acoes if x["acao"] == "encerrar_sessao")
    assert enc["estacao"] == cenario["estacao"]
    msgs = _acoes(c, admin, estacao=cenario["estacao"], acao="mensagem")
    assert msgs and msgs[0]["detalhe"] == "Oi"
    # o mais recente primeiro
    assert acoes == sorted(acoes, key=lambda x: x["quando"], reverse=True)


def test_filtrar_acoes_por_operador_e_data(c, admin, operador, cenario):
    c.post(f"/api/estacoes/fila/{cenario['cliente_id']}", headers=operador)
    op_id = next(o["id"] for o in c.get("/api/operadores/", headers=admin).json() if o["login"] == "operador.teste")
    acoes = _acoes(c, admin, operador_id=op_id)
    assert acoes and all(a["operador"] == "Operador" for a in acoes)
    hoje = datetime.utcnow().date()
    assert _acoes(c, admin, operador_id=op_id, de=str(hoje - timedelta(days=1)), ate=str(hoje + timedelta(days=1)))
    assert _acoes(c, admin, operador_id=op_id, de=str(hoje + timedelta(days=2))) == []


def test_so_o_admin_ve_o_registro_e_exporta_csv(c, admin, operador, cenario):
    assert c.get("/api/relatorios/acoes", headers=operador).status_code == 403
    c.post(f"/api/estacoes/fila/{cenario['cliente_id']}", headers=operador)
    r = c.get("/api/relatorios/acoes.csv", headers=admin)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    primeira = r.text.lstrip("﻿").splitlines()[0]
    assert "Operador" in primeira and "Ação" in primeira


def test_acao_em_massa_registra_cada_estacao(c, admin, cenario):
    outra = _estacao_nova(c, admin)
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as a, \
            c.websocket_connect(f"/ws/estacao/{outra}") as b:
        _estado(a)
        _estado(b)
        c.post("/api/estacoes/acoes", headers=admin,
               json={"acao": "mensagem", "texto": "Fecha logo", "estacoes": [cenario["estacao"], outra]})
    for nome in (cenario["estacao"], outra):
        assert _acoes(c, admin, estacao=nome, acao="mensagem")


# ── 8.2 Relatorio de uso ─────────────────────────────────────────────────────

def _sessao_encerrada(cliente_id, estacao_nome, inicio_utc, minutos):
    from app.models import Estacao
    db = SessionLocal()
    est = db.query(Estacao).filter(Estacao.nome == estacao_nome).one()
    s = Sessao(cliente_id=cliente_id, estacao_id=est.id, iniciada_em=inicio_utc,
               encerrada_em=inicio_utc + timedelta(minutes=minutos), tempo_total_segundos=7200,
               tempo_consumido_segundos=minutos * 60, motivo_encerramento="cliente")
    db.add(s)
    db.commit()
    db.close()


def test_relatorio_de_uso(c, admin, operador, cenario):
    # periodo no futuro distante: so as sessoes deste teste entram
    outra = _estacao_nova(c, admin)
    cid = cenario["cliente_id"]
    r = c.post("/api/clientes/", headers=admin, json={"login": f"uso{next(_contador)}", "nome": "Uso", "senha": "senha-x"})
    cid2 = r.json()["id"]
    # 10/03/2031 (segunda) 14:00 em Brasilia = 17:00 UTC
    base = datetime(2031, 3, 10, 17, 0)
    _sessao_encerrada(cid, cenario["estacao"], base, 90)                       # 14:00-15:30
    _sessao_encerrada(cid2, cenario["estacao"], base + timedelta(hours=2), 30)  # 16:00-16:30
    _sessao_encerrada(cid, outra, base + timedelta(days=1), 60)                 # terca 14:00-15:00
    assert c.get("/api/relatorios/uso", headers=operador).status_code == 403
    r = c.get("/api/relatorios/uso", headers=admin, params={"de": "2031-03-10", "ate": "2031-03-11"})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["resumo"] == {"sessoes": 3, "segundos": 180 * 60, "clientes": 2, "media_segundos": 60 * 60}
    assert u["por_dia"] == [
        {"dia": "2031-03-10", "sessoes": 2, "segundos": 120 * 60, "clientes": 2},
        {"dia": "2031-03-11", "sessoes": 1, "segundos": 60 * 60, "clientes": 1},
    ]
    # pico: segundos de uso por dia da semana (0 = segunda) e hora de Brasilia
    pico = {(p["dia_semana"], p["hora"]): p["segundos"] for p in u["pico"]}
    assert pico[(0, 14)] == 3600 and pico[(0, 15)] == 1800 and pico[(0, 16)] == 1800
    assert pico[(1, 14)] == 3600
    assert u["estacoes"][0] == {"estacao": cenario["estacao"], "sessoes": 2, "segundos": 120 * 60}
    # sem nada no periodo: tudo zerado, sem erro
    vazio = c.get("/api/relatorios/uso", headers=admin, params={"de": "2031-04-01", "ate": "2031-04-02"}).json()
    assert vazio["resumo"]["sessoes"] == 0 and vazio["por_dia"] == [] and vazio["estacoes"] == []


def test_relatorio_de_uso_por_piso(c, admin, cenario):
    infantil = _estacao_infantil(c, admin)
    base = datetime(2031, 5, 5, 17, 0)
    _sessao_encerrada(cenario["cliente_id"], cenario["estacao"], base, 30)
    _, crianca = _cliente_infantil(c, admin)
    _sessao_encerrada(crianca, infantil, base, 45)
    params = {"de": "2031-05-05", "ate": "2031-05-05"}
    so_infantil = c.get("/api/relatorios/uso", headers=admin,
                        params={**params, "piso_id": _id_piso(c, admin, "Infantil")}).json()
    assert so_infantil["resumo"]["segundos"] == 45 * 60
    assert [e["estacao"] for e in so_infantil["estacoes"]] == [infantil]
    todos = c.get("/api/relatorios/uso", headers=admin, params=params).json()
    assert todos["resumo"]["segundos"] == 75 * 60


# ── 8.5 Historico do VSCyber guardado, mas escondido por enquanto ───────────

def test_historico_do_vscyber_fica_escondido(c, admin, cenario):
    from app.models import ConfiguracaoSistema, Estacao
    cid, nome = cenario["cliente_id"], cenario["estacao"]
    _sessao_encerrada(cid, nome, datetime(2031, 7, 7, 17, 0), 40)  # do MatheCafe: aparece
    db = SessionLocal()
    est = db.query(Estacao).filter(Estacao.nome == nome).one()
    db.add(Sessao(cliente_id=cid, estacao_id=est.id, iniciada_em=datetime(2031, 7, 8, 17, 0),
                  encerrada_em=datetime(2031, 7, 8, 18, 0), tempo_total_segundos=3600,
                  tempo_consumido_segundos=3600, motivo_encerramento="vscyber"))
    db.commit()
    db.close()
    periodo = {"de": "2031-07-01", "ate": "2031-07-31"}

    def visto():
        uso = c.get("/api/relatorios/uso", headers=admin, params=periodo).json()["resumo"]["sessoes"]
        cli = c.get(f"/api/relatorios/cliente/{cid}", headers=admin, params=periodo).json()["sessoes"]
        est = c.get(f"/api/relatorios/estacao/{nome}", headers=admin, params=periodo).json()["sessoes"]
        hist = [s for s in c.get(f"/api/sessoes/historico?cliente_id={cid}&limit=500", headers=admin).json()
                if s["iniciada_em"].startswith("2031-07")]
        csv_ = c.get(f"/api/relatorios/csv?cliente_id={cid}&data_inicio=2031-07-01&data_fim=2031-07-31",
                     headers=admin).text.lstrip("﻿").strip().splitlines()
        return uso, cli, est, len(hist), len(csv_) - 1

    assert visto() == (1, 1, 1, 1, 1)  # so a do MatheCafe
    db = SessionLocal()
    db.add(ConfiguracaoSistema(chave="historico_vscyber_visivel", valor="true"))
    db.commit()
    try:
        assert visto() == (2, 2, 2, 2, 2)  # ligado: as importadas voltam a aparecer
    finally:
        db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == "historico_vscyber_visivel").delete()
        db.commit()
        db.close()


# ── 7.3 Mapa: zonas (grupos) com posicao e tamanho ──────────────────────────

def test_zona_guarda_posicao_e_tamanho_no_mapa(c, admin, operador):
    adulto = _id_piso(c, admin, "Adulto")
    r = c.post(f"/api/estacoes/grupos?nome=Sala%20Zona&piso_id={adulto}", headers=admin)
    g = r.json()
    assert g["zona"] is None  # sem posicao: o mapa arruma sozinho
    zona = {"x": 40, "y": 60, "largura": 520, "altura": 300}
    r = c.put(f"/api/estacoes/grupos/{g['id']}", headers=admin, json={"zona": zona})
    assert r.status_code == 200, r.text
    assert r.json()["zona"] == zona
    lista = {x["id"]: x for x in c.get("/api/estacoes/grupos", headers=operador).json()}
    assert lista[g["id"]]["zona"] == zona
    # operador nao mexe no mapa
    assert c.put(f"/api/estacoes/grupos/{g['id']}", headers=operador, json={"zona": zona}).status_code == 403


def test_zona_com_tamanho_invalido_e_recusada(c, admin):
    adulto = _id_piso(c, admin, "Adulto")
    g = c.post(f"/api/estacoes/grupos?nome=Sala%20Ruim&piso_id={adulto}", headers=admin).json()
    for zona in ({"x": -5, "y": 0, "largura": 300, "altura": 200},
                 {"x": 0, "y": 0, "largura": 50, "altura": 200}):
        assert c.put(f"/api/estacoes/grupos/{g['id']}", headers=admin, json={"zona": zona}).status_code == 422


def test_mover_estacao_para_outra_zona_com_posicao(c, admin):
    adulto = _id_piso(c, admin, "Adulto")
    g = c.post(f"/api/estacoes/grupos?nome=Sala%20Destino&piso_id={adulto}", headers=admin).json()
    nome = _estacao_nova(c, admin)
    est = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == nome)
    r = c.put(f"/api/estacoes/{est['id']}", headers=admin, json={"grupo_id": g["id"], "pos_x": 72, "pos_y": 16})
    assert r.status_code == 200, r.text
    est = next(e for e in c.get("/api/estacoes/", headers=admin).json() if e["nome"] == nome)
    assert (est["grupo_id"], est["pos_x"], est["pos_y"]) == (g["id"], 72, 16)
