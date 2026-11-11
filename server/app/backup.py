"""Backup diario do banco SQLite (cybercafe.db).

Um arquivo por dia em BACKUP_PASTA (padrao server/backups), feito pela API de
backup do proprio SQLite: a copia fica consistente mesmo com o servidor
gravando. Guarda os ultimos BACKUP_DIAS dias.

Restaurar (10.2): o painel deixa o pedido em server/restaurar.pedido e reinicia;
ao subir, antes de abrir o banco, aplicar_restauracao_pendente guarda o banco
atual (antes-da-restauracao-...db, na pasta dos backups) e poe o backup no lugar.
"""
import json
import os
import shutil
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


# Outros arquivos da pasta que podem ser restaurados (nao sao apagados sozinhos):
# o banco de antes de uma restauracao (para desfazer) e os enviados pelo painel
NOME_OUTRO = re.compile(r"^(antes-da-restauracao|enviado)-\d{4}-\d{2}-\d{2}-\d{6}\.db$")
TABELAS = ("usuarios", "estacoes", "sessoes")


def listar_outros(pasta: Path) -> list:
    """Os bancos de antes de restaurar e os enviados, o mais novo primeiro."""
    if not pasta.is_dir():
        return []
    itens = []
    for arq in pasta.iterdir():
        if arq.is_file() and NOME_OUTRO.match(arq.name):
            st = arq.stat()
            itens.append({"nome": arq.name, "bytes": st.st_size,
                          "feito_em": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return sorted(itens, key=lambda b: b["feito_em"], reverse=True)


def restauravel(pasta: Path, nome: str):
    """O arquivo da pasta com esse nome, se e um backup (nada de caminho para fora)."""
    if not (NOME_BACKUP.match(nome) or NOME_OUTRO.match(nome)):
        return None
    arquivo = pasta / nome
    return arquivo if arquivo.is_file() else None


def conferir_banco(arquivo: Path) -> dict:
    """Confere se o arquivo e um banco do MatheCafe inteiro (abre so para ler).
    Devolve quantos clientes, estacoes e sessoes ele tem; ValueError se nao serve."""
    try:
        con = sqlite3.connect(f"file:{Path(arquivo).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise ValueError(f"Não foi possível abrir o arquivo: {e}")
    try:
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError:
            raise ValueError("O arquivo não é um banco SQLite")
        if ok != "ok":
            raise ValueError(f"O banco está corrompido ({ok})")
        faltam = [t for t in TABELAS if t not in tabelas]
        if faltam:
            raise ValueError(f"Não é um banco do MatheCafé (faltam as tabelas: {', '.join(faltam)})")
        contar = lambda sql: con.execute(sql).fetchone()[0]
        return {
            "clientes": contar("SELECT count(*) FROM usuarios WHERE perfil = 'cliente'"),
            "estacoes": contar("SELECT count(*) FROM estacoes"),
            "sessoes": contar("SELECT count(*) FROM sessoes"),
        }
    finally:
        con.close()


def _copiar_sqlite(origem: Path, destino: Path):
    """Copia consistente (API de backup do SQLite) para destino.tmp e renomeia."""
    temporario = destino.with_name(destino.name + ".tmp")
    fonte = sqlite3.connect(str(origem))
    try:
        copia = sqlite3.connect(str(temporario))
        try:
            fonte.backup(copia)
        finally:
            copia.close()
    finally:
        fonte.close()
    os.replace(temporario, destino)


def aplicar_restauracao_pendente(banco: Path, pedido: Path, pasta: Path, agora: datetime):
    """Chamado ao subir, antes de abrir o banco. Sem pedido: None. Com pedido:
    guarda o banco atual em pasta/antes-da-restauracao-AAAA-MM-DD-HHMMSS.db e
    poe o backup no lugar. Devolve o que fez (ou {"erro": ...}, sem mexer no banco)."""
    if not pedido.exists():
        return None
    try:
        dados = json.loads(pedido.read_text(encoding="utf-8"))
        arquivo = Path(dados["arquivo"])
        quem = dados.get("quem") or {}
    except (OSError, ValueError, KeyError, TypeError) as e:
        pedido.unlink(missing_ok=True)
        return {"erro": f"pedido de restauração ilegível ({e})"}
    pedido.unlink(missing_ok=True)  # um pedido so e tentado uma vez
    try:
        conferir_banco(arquivo)
    except ValueError as e:
        return {"erro": f"{arquivo.name}: {e}", "arquivo": arquivo.name, "quem": quem}
    pasta.mkdir(parents=True, exist_ok=True)
    antes = pasta / f"antes-da-restauracao-{agora:%Y-%m-%d-%H%M%S}.db"
    havia_banco = banco.exists()
    if havia_banco:
        _copiar_sqlite(banco, antes)
    for sobra in ("-wal", "-shm", "-journal"):  # do banco que saiu
        Path(str(banco) + sobra).unlink(missing_ok=True)
    temporario = banco.with_name(banco.name + ".restaurando")
    shutil.copyfile(arquivo, temporario)
    os.replace(temporario, banco)
    return {"arquivo": arquivo.name, "copia_antes": antes.name if havia_banco else None, "quem": quem}
