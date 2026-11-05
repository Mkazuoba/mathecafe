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
