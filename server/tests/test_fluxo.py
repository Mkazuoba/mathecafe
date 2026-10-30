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


def test_painel_antigo_continua_disponivel(c):
    r = c.get("/antigo/")
    assert r.status_code == 200
    assert "MatheCafé" in r.text


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

    r = c.post("/api/estacoes/grupos", headers=admin, params={"nome": "Sala antiga"})
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


def test_servidor_reinicia_e_encerra_sessao_aberta(c, admin, cenario):
    # Comecou ha 90 min, o servidor caiu ha 30 (ultimo batimento): usou 60 min.
    # Antes a sessao ficava aberta para sempre e o cliente aparecia "em uso".
    from app.main import encerrar_sessoes_do_desligamento
    sid = _sessao_aberta(cenario, inicio_min=90)
    _batimento(30)
    db = SessionLocal()
    assert encerrar_sessoes_do_desligamento(db) >= 1
    db.close()
    s = _sessao(sid)
    assert s.encerrada_em is not None and s.motivo_encerramento == "servidor_desligado"
    assert abs(s.tempo_consumido_segundos - 3600) <= 2
    saldo = c.get(f"/api/clientes/{cenario['cliente_id']}", headers=admin).json()["saldo_segundos"]
    assert abs(saldo - 3600) <= 2
    assert all(x["id"] != sid for x in c.get("/api/sessoes/ativas", headers=admin).json())
    # e o cliente pode ser liberado de novo
    assert c.post(f"/api/estacoes/fila/{cenario['cliente_id']}", headers=admin).status_code == 200


def test_sem_batimento_nao_cobra_o_tempo_desligado(c, admin, cenario):
    from app.main import encerrar_sessoes_do_desligamento
    sid = _sessao_aberta(cenario, inicio_min=50)
    _batimento(None)
    db = SessionLocal()
    encerrar_sessoes_do_desligamento(db)
    db.close()
    assert _sessao(sid).tempo_consumido_segundos == 0
