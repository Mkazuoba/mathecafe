"""Backup diario do banco SQLite (cybercafe.db).

Um arquivo por dia em BACKUP_PASTA (padrao server/backups), feito pela API de
backup do proprio SQLite: a copia fica consistente mesmo com o servidor
gravando. Guarda os ultimos BACKUP_DIAS dias. Para restaurar: parar o servidor,
copiar o backup por cima do cybercafe.db e subir de novo.
"""
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

PREFIXO = "cybercafe-"
# cybercafe-AAAA-MM-DD-HHMM.db
NOME_BACKUP = re.compile(r"^cybercafe-(\d{4}-\d{2}-\d{2})-\d{4}\.db$")


def _dia(nome: str):
    m = NOME_BACKUP.match(nome)
    return date.fromisoformat(m.group(1)) if m else None


def listar_backups(pasta: Path) -> list:
    """Backups da pasta, o mais novo primeiro."""
    if not pasta.is_dir():
        return []
    itens = []
    for arq in pasta.iterdir():
        if arq.is_file() and _dia(arq.name):
            st = arq.stat()
            itens.append({"nome": arq.name, "bytes": st.st_size,
                          "feito_em": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return sorted(itens, key=lambda b: b["nome"], reverse=True)


def backup_de_hoje_feito(pasta: Path, hoje: date) -> bool:
    return any(_dia(b["nome"]) == hoje for b in listar_backups(pasta))


def apagar_antigos(pasta: Path, hoje: date, manter_dias: int):
    limite = hoje - timedelta(days=manter_dias - 1)
    for b in listar_backups(pasta):
        if _dia(b["nome"]) < limite:
            (pasta / b["nome"]).unlink(missing_ok=True)


def fazer_backup(origem: Path, pasta: Path, quando: datetime, manter_dias: int) -> Path:
    """Copia o banco para pasta/cybercafe-AAAA-MM-DD-HHMM.db (quando = horario
    de Brasilia) e apaga os backups mais velhos que manter_dias."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{PREFIXO}{quando:%Y-%m-%d-%H%M}.db"
    temporario = destino.with_suffix(".tmp")
    fonte = sqlite3.connect(str(origem))
    try:
        copia = sqlite3.connect(str(temporario))
        try:
            fonte.backup(copia)
        finally:
            copia.close()
    finally:
        fonte.close()
    # So aparece com o nome final depois de completo
    os.replace(temporario, destino)
    apagar_antigos(pasta, quando.date(), manter_dias)
    return destino
