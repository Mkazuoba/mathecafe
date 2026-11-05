"""
Importa os clientes do VSCyber do piso infantil (tarefa 4.7c) e completa o
nascimento dos clientes do adulto ja importados.

Rode dentro da pasta server/ com o venv ativo, na maquina do servidor:
  python importar_infantil.py              simula: so mostra o que faria
  python importar_infantil.py --aplicar    faz backup do banco e grava

Os CSV vem do exportar_fdb.py (Arquivos VSCyber/export e export_infantil).

Regras (decididas com o Matheus em 05/11/2026):
- nascimento do adulto: preenche so onde esta vazio;
- login novo: entra no piso infantil, com o nascimento e a senha padrao 1234;
- login que ja existe e e a mesma pessoa (mesmo primeiro nome e mesmo
  nascimento): um cadastro so; menor de 18 hoje passa para o infantil, os
  outros ficam onde estao (ninguem sai do infantil, entao rodar de novo nao muda nada);
- login que ja existe com nome ou nascimento diferente: nao importa; vai para
  uma planilha para o atendimento conferir.
"""
import argparse
import csv
import os
import sys
import unicodedata
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import Usuario

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA_VSCYBER = os.path.join(AQUI, "..", "Arquivos VSCyber")
CSV_ADULTO = os.path.join(PASTA_VSCYBER, "export", "clientes_importacao.csv")
CSV_INFANTIL = os.path.join(PASTA_VSCYBER, "export_infantil", "clientes_importacao.csv")
CSV_CONFERIR = os.path.join(PASTA_VSCYBER, "export_infantil", "conferir_logins_repetidos.csv")
SENHA_PADRAO = "1234"
MAIORIDADE = 18
QUEM_TROCOU = "Importação do VSCyber infantil"


def ler_csv(caminho):
    with open(caminho, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def data_vscyber(texto):
    """O export do adulto tem 05/09/1989 00:00; o do infantil, 2018-04-09 00:00:00."""
    texto = (texto or "").strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    return None


def idade(nascimento: date, hoje: date) -> int:
    return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def _primeiro_nome(texto):
    partes = _normalizar(texto).split()
    return partes[0] if partes else ""


def _nome_completo(linha):
    login = (linha.get("login") or "").strip()
    return f"{(linha.get('nome') or '').strip()} {(linha.get('sobrenome') or '').strip()}".strip() or login


def _clientes_por_login(db):
    return {u.login.strip().lower(): u for u in db.query(Usuario).filter(Usuario.perfil == "cliente")}


def preencher_nascimento(db, linhas) -> int:
    """Nascimento vindo do VSCyber nos clientes que ainda nao tem. Devolve quantos."""
    clientes = _clientes_por_login(db)
    preenchidos = 0
    for linha in linhas:
        cliente = clientes.get((linha.get("login") or "").strip().lower())
        nascimento = data_vscyber(linha.get("nascimento"))
        if cliente is not None and cliente.data_nascimento is None and nascimento:
            cliente.data_nascimento = nascimento
            preenchidos += 1
    db.flush()
    return preenchidos


def importar_infantil(db, linhas, hoje: date, senha_hash: str) -> dict:
    """Aplica as regras do topo na sessao (quem chama faz o commit)."""
    clientes = _clientes_por_login(db)
    resultado = {"novos": 0, "para_infantil": 0, "mantidos": 0, "conferir": []}
    agora = datetime.utcnow()
    for linha in linhas:
        login = (linha.get("login") or "").strip()
        if not login:
            continue
        nascimento = data_vscyber(linha.get("nascimento"))
        existente = clientes.get(login.lower())
        if existente is None:
            novo = Usuario(login=login, nome=_nome_completo(linha), senha_hash=senha_hash, perfil="cliente",
                           ativo=True, saldo_segundos=0, piso="infantil", data_nascimento=nascimento)
            db.add(novo)
            clientes[login.lower()] = novo
            resultado["novos"] += 1
            continue

        mesmo_nome = _primeiro_nome(existente.nome) == _primeiro_nome(_nome_completo(linha))
        mesmo_nascimento = nascimento is not None and existente.data_nascimento == nascimento
        if not (mesmo_nome and mesmo_nascimento):
            motivos = []
            if not mesmo_nome:
                motivos.append("nome diferente")
            if not mesmo_nascimento:
                motivos.append("nascimento diferente" if existente.data_nascimento else
                               "sem nascimento no MatheCafé")
            resultado["conferir"].append({
                "login": login,
                "nome_no_matheCafe": existente.nome,
                "nascimento_no_matheCafe": existente.data_nascimento.isoformat() if existente.data_nascimento else "",
                "nome_no_vscyber_infantil": _nome_completo(linha),
                "nascimento_no_vscyber_infantil": nascimento.isoformat() if nascimento else "",
                "motivo": " e ".join(motivos),
            })
            continue

        if existente.piso != "infantil" and idade(nascimento, hoje) < MAIORIDADE:
            existente.piso = "infantil"
            existente.piso_alterado_por = QUEM_TROCOU
            existente.piso_alterado_em = agora
            resultado["para_infantil"] += 1
        else:
            resultado["mantidos"] += 1
    db.flush()
    return resultado


def gravar_conferir(caminho, itens):
    colunas = ["login", "motivo", "nome_no_matheCafe", "nascimento_no_matheCafe",
               "nome_no_vscyber_infantil", "nascimento_no_vscyber_infantil"]
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=colunas, delimiter=";")
        w.writeheader()
        w.writerows(itens)


def _backup_antes():
    from app.backup import fazer_backup
    from app.config import get_settings, pasta_de_backup
    from app.database import ARQUIVO_SQLITE
    from app.tempo_diario import FUSO
    if ARQUIVO_SQLITE is None:
        print("Banco nao e SQLite: faca o backup pelo provedor antes de continuar.")
        return
    s = get_settings()
    destino = fazer_backup(ARQUIVO_SQLITE, pasta_de_backup(s.BACKUP_PASTA), datetime.now(FUSO), s.BACKUP_DIAS)
    print(f"Backup feito: {destino}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Importa o VSCyber do piso infantil")
    p.add_argument("--aplicar", action="store_true", help="grava no banco (sem isso, so simula)")
    p.add_argument("--adulto", default=CSV_ADULTO)
    p.add_argument("--infantil", default=CSV_INFANTIL)
    p.add_argument("--conferir", default=CSV_CONFERIR)
    args = p.parse_args(argv)

    from app.database import SessionLocal, init_db
    from app.security import hash_senha
    from app.tempo_diario import hoje_br

    adulto, infantil = ler_csv(args.adulto), ler_csv(args.infantil)
    print(f"CSV do adulto: {len(adulto)} | CSV do infantil: {len(infantil)}")
    init_db()
    if args.aplicar:
        _backup_antes()
    db = SessionLocal()
    try:
        antes = db.query(Usuario).filter(Usuario.perfil == "cliente").count()
        preenchidos = preencher_nascimento(db, adulto)
        print("Calculando o hash da senha padrao...")
        r = importar_infantil(db, infantil, hoje_br(), hash_senha(SENHA_PADRAO))
        print(f"Clientes no MatheCafe antes: {antes}")
        print(f"  nascimento preenchido (adulto): {preenchidos}")
        print(f"  novos no piso infantil:          {r['novos']}")
        print(f"  ja existiam, passaram ao infantil (menores de 18): {r['para_infantil']}")
        print(f"  ja existiam, ficaram como estavam: {r['mantidos']}")
        print(f"  logins repetidos para conferir (nao importados): {len(r['conferir'])}")
        gravar_conferir(args.conferir, r["conferir"])
        print(f"  planilha para conferir: {os.path.abspath(args.conferir)}")
        if args.aplicar:
            db.commit()
            print("Gravado.")
        else:
            db.rollback()
            print("Simulacao: nada foi gravado. Para gravar: python importar_infantil.py --aplicar")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
