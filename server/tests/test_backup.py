"""Backup diario do SQLite (4.6): copia consistente, um arquivo por dia,
guardando os ultimos dias."""
import sqlite3
from datetime import date, datetime

from app.backup import backup_de_hoje_feito, fazer_backup, listar_backups


def _banco(caminho, n=3):
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome TEXT)")
    con.executemany("INSERT INTO usuarios (nome) VALUES (?)", [(f"cliente {i}",) for i in range(n)])
    con.commit()
    return con


def test_backup_e_uma_copia_que_abre(tmp_path):
    origem = tmp_path / "cybercafe.db"
    con = _banco(origem)  # servidor com o banco aberto, como em produção
    pasta = tmp_path / "backups"
    destino = fazer_backup(origem, pasta, datetime(2026, 11, 5, 0, 1), manter_dias=14)
    con.close()
    assert destino.name == "cybercafe-2026-11-05-0001.db"
    copia = sqlite3.connect(destino)
    assert copia.execute("SELECT count(*) FROM usuarios").fetchone()[0] == 3
    assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copia.close()
    assert not list(pasta.glob("*.tmp"))


def test_um_por_dia_e_apaga_os_antigos(tmp_path):
    origem = tmp_path / "cybercafe.db"
    _banco(origem).close()
    pasta = tmp_path / "backups"
    assert not backup_de_hoje_feito(pasta, date(2026, 11, 5))  # pasta nem existe
    for dia in range(1, 21):
        fazer_backup(origem, pasta, datetime(2026, 10, dia, 0, 1), manter_dias=7)
    fazer_backup(origem, pasta, datetime(2026, 10, 20, 15, 30), manter_dias=7)  # "fazer agora"
    nomes = [b["nome"] for b in listar_backups(pasta)]
    # mais novo primeiro; só os 7 últimos dias (14 a 20/10)
    assert nomes[0] == "cybercafe-2026-10-20-1530.db"
    assert nomes[-1] == "cybercafe-2026-10-14-0001.db" and len(nomes) == 8
    assert backup_de_hoje_feito(pasta, date(2026, 10, 20))
    assert not backup_de_hoje_feito(pasta, date(2026, 10, 21))
    # arquivo que não é backup na mesma pasta não é tocado nem listado
    (pasta / "leia-me.txt").write_text("x")
    fazer_backup(origem, pasta, datetime(2026, 10, 30, 0, 1), manter_dias=7)
    assert (pasta / "leia-me.txt").exists()
    assert all(b["nome"].startswith("cybercafe-") for b in listar_backups(pasta))


# ── Restaurar um backup (10.2) ───────────────────────────────────────────────

def _banco_do_sistema(caminho, clientes=2):
    """Um banco com as tabelas que a restauracao exige."""
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome TEXT, perfil TEXT)")
    con.execute("CREATE TABLE estacoes (id INTEGER PRIMARY KEY, nome TEXT)")
    con.execute("CREATE TABLE sessoes (id INTEGER PRIMARY KEY, estacao_id INTEGER)")
    con.executemany("INSERT INTO usuarios (nome, perfil) VALUES (?, 'cliente')", [(f"c{i}",) for i in range(clientes)])
    con.commit()
    return con


def test_conferir_banco_aceita_so_um_banco_do_sistema(tmp_path):
    import pytest
    from app.backup import conferir_banco
    bom = tmp_path / "bom.db"
    _banco_do_sistema(bom, clientes=5).close()
    assert conferir_banco(bom)["clientes"] == 5
    lixo = tmp_path / "lixo.db"
    lixo.write_bytes(b"isto nao e um banco")
    with pytest.raises(ValueError):
        conferir_banco(lixo)
    outro = tmp_path / "outro.db"
    _banco(outro).close()  # SQLite, mas sem as tabelas do MatheCafe
    with pytest.raises(ValueError, match="MatheCafé"):
        conferir_banco(outro)


def test_restauracao_pendente_troca_o_banco_e_guarda_o_de_antes(tmp_path):
    import json
    from app.backup import aplicar_restauracao_pendente, listar_outros
    banco = tmp_path / "cybercafe.db"
    _banco_do_sistema(banco, clientes=10).close()
    (tmp_path / "cybercafe.db-wal").write_bytes(b"")  # sobra do servidor anterior
    pasta = tmp_path / "backups"
    pasta.mkdir()
    velho = pasta / "cybercafe-2026-11-01-0001.db"
    _banco_do_sistema(velho, clientes=3).close()
    pedido = tmp_path / "restaurar.pedido"
    pedido.write_text(json.dumps({"arquivo": str(velho), "quem": {"sub": "1", "nome": "Admin"}}), encoding="utf-8")

    feito = aplicar_restauracao_pendente(banco, pedido, pasta, datetime(2026, 11, 11, 16, 30, 5))

    assert feito["arquivo"] == velho.name and feito["quem"]["nome"] == "Admin"
    assert not pedido.exists() and not (tmp_path / "cybercafe.db-wal").exists()
    con = sqlite3.connect(banco)
    assert con.execute("SELECT count(*) FROM usuarios").fetchone()[0] == 3  # o do backup
    con.close()
    # o banco de antes fica guardado (para desfazer) e aparece na lista
    antes = pasta / "antes-da-restauracao-2026-11-11-163005.db"
    con = sqlite3.connect(antes)
    assert con.execute("SELECT count(*) FROM usuarios").fetchone()[0] == 10
    con.close()
    assert feito["copia_antes"] == antes.name
    assert [b["nome"] for b in listar_outros(pasta)] == [antes.name]


def test_restauracao_com_arquivo_ruim_nao_mexe_no_banco(tmp_path):
    import json
    from app.backup import aplicar_restauracao_pendente
    banco = tmp_path / "cybercafe.db"
    _banco_do_sistema(banco, clientes=10).close()
    ruim = tmp_path / "ruim.db"
    ruim.write_bytes(b"x" * 100)
    pedido = tmp_path / "restaurar.pedido"
    pedido.write_text(json.dumps({"arquivo": str(ruim)}), encoding="utf-8")
    feito = aplicar_restauracao_pendente(banco, pedido, tmp_path / "backups", datetime(2026, 11, 11))
    assert feito["erro"] and not pedido.exists()
    con = sqlite3.connect(banco)
    assert con.execute("SELECT count(*) FROM usuarios").fetchone()[0] == 10
    con.close()
    # sem pedido: nada a fazer
    assert aplicar_restauracao_pendente(banco, pedido, tmp_path / "backups", datetime(2026, 11, 11)) is None
