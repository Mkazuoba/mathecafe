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
os.environ["ADMIN_LOGIN"] = "admin.teste"
os.environ["ADMIN_SENHA"] = "senha-admin-teste"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Usuario
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


def _encerrar_pelo_pc(ws, sessao_id, consumido):
    ws.send_json({"evento": "sessao_encerrada", "sessao_id": sessao_id,
                  "motivo": "cliente", "tempo_consumido_segundos": consumido})
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


def test_queda_durante_sessao_devolve_saldo_e_libera_estacao(c, admin, cenario):
    """O agente volta ao login quando a conexão cai; o servidor não pode deixar
    a sessão aberta nem a estação presa como ocupada."""
    cid = cenario["cliente_id"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"]
    with c.websocket_connect(f"/ws/estacao/{cenario['estacao']}") as ws:
        assert not [s for s in c.get("/api/sessoes/ativas", headers=admin).json()
                    if s["estacao_nome"] == cenario["estacao"]]
        saldo = c.get(f"/api/clientes/{cid}", headers=admin).json()["saldo_segundos"]
        assert saldo >= dados["tempo_segundos"] - 5

        c.post(f"/api/estacoes/fila/{cid}", headers=admin)
        dados = _logar_no_pc(ws, cenario["cliente"])
        assert dados["ok"], dados
        assert dados["tempo_segundos"] == saldo


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
        assert ws.receive_json() == {"evento": "manutencao_resultado", "dados": {"ok": True}}

        ws.send_json({"evento": "validar_manutencao", "login": cenario["cliente"]["login"],
                      "senha": cenario["cliente"]["senha"]})
        assert ws.receive_json()["dados"]["ok"] is False

        ws.send_json({"evento": "validar_manutencao", "login": "operador.teste", "senha": "errada"})
        assert ws.receive_json()["dados"]["ok"] is False


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


def test_painel_antigo_continua_disponivel(c):
    r = c.get("/antigo/")
    assert r.status_code == 200
    assert "MatheCafé" in r.text
