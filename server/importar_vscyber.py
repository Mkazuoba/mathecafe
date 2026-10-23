"""
Importa clientes do VSCyber para o MatheCafe.
Rode dentro da pasta server/ com o venv ativo:
  python importar_vscyber.py
"""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.security import hash_senha
from app.models import Usuario

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "Arquivos VSCyber", "export", "clientes_importacao.csv")
SENHA_PADRAO = "1234"

def main():
    init_db()
    db = SessionLocal()
    try:
        existentes = set(r[0] for r in db.query(Usuario.login).all())
        print(f"Usuarios ja no banco: {len(existentes)}")

        # Hash calculado UMA vez para todos
        print("Calculando hash da senha padrao...")
        senha_hash = hash_senha(SENHA_PADRAO)
        print("Hash pronto. Iniciando importacao...")

        inseridos = 0
        ignorados = 0

        with open(CSV_PATH, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            lote = []
            for row in reader:
                login = (row.get("login") or "").strip()
                if not login or login in existentes:
                    ignorados += 1
                    continue

                nome = f"{(row.get('nome') or '').strip()} {(row.get('sobrenome') or '').strip()}".strip() or login

                lote.append(Usuario(
                    login=login,
                    nome=nome,
                    senha_hash=senha_hash,
                    perfil="cliente",
                    ativo=True,
                    saldo_segundos=0,
                ))
                existentes.add(login)
                inseridos += 1

                if len(lote) >= 1000:
                    db.bulk_save_objects(lote)
                    db.commit()
                    lote = []
                    print(f"  {inseridos} inseridos...", end="\r", flush=True)

            if lote:
                db.bulk_save_objects(lote)
                db.commit()

        print(f"\nConcluido!")
        print(f"  Inseridos : {inseridos}")
        print(f"  Ignorados : {ignorados}")

    except Exception as e:
        db.rollback()
        print(f"Erro: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
