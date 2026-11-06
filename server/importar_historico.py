"""
Importa o historico de uso do VSCyber (tabela CON: cliente, estacao, inicio, fim)
como sessoes encerradas do MatheCafe (tarefa 8.5). Assim o historico de cada
cliente e o relatorio de uso (Historicos -> Uso) incluem o tempo de antes.

Rode dentro da pasta server/ com o venv ativo, na maquina do servidor, DEPOIS
de importar os clientes (importar_infantil.py):
  python importar_historico.py              simula: so mostra o que faria
  python importar_historico.py --aplicar    faz backup do banco e grava
  --desde AAAA-MM-DD                        a partir de quando (padrao 2022-01-01)

Le os CSV do exportar_fdb.py (Arquivos VSCyber/export e export_infantil:
tabelas/CON.csv, tabelas/ESTC.csv e clientes_importacao.csv).

Regras (decididas com o Matheus em 06/11/2026):
- so desde 2022; usos sem horario de fim ficam de fora;
- as estacoes ficam com o nome do VSCyber, como estacoes inativas
  ("BSP-87 (VS)" no adulto, "BSP-87 (VSI)" no infantil), num mapa inativo do
  piso de cada banco: nao aparecem no Mapa nem no Painel, so no historico;
- o cliente e achado pelo login; os logins que estao nos dois VSCyber com
  pessoas diferentes (os da planilha de conferencia) ficam de fora;
- rodar de novo nao duplica.
"""
import argparse
import csv
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import Estacao, GrupoEstacao, Piso, Sessao, Usuario
from app.tempo_diario import FUSO
from importar_infantil import _nome_completo, _primeiro_nome, data_vscyber, ler_csv

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA_VSCYBER = os.path.join(AQUI, "..", "Arquivos VSCyber")
from app.importados import MOTIVO  # "vscyber": escondidas por enquanto (app/importados.py)
USO_MAXIMO = timedelta(hours=16)  # mais que isso e registro quebrado (PC esquecido ligado)
BASES = [  # pasta do export, sufixo das estacoes, piso
    ("export", "VS", "Adulto"),
    ("export_infantil", "VSI", "Infantil"),
]


def _hora_vscyber(texto):
    """'2024-03-10 14:00:00.000000' em Brasilia -> UTC sem fuso (como o MatheCafe guarda)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            local = datetime.strptime(texto, formato)
            return local.replace(tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    return None


def logins_duvidosos(adulto, infantil):
    """Logins que estao nos dois VSCyber com pessoas diferentes (primeiro nome ou
    nascimento diferente): os mesmos que a importacao dos clientes mandou conferir."""
    por_login = {(r.get("login") or "").strip().lower(): r for r in adulto}
    duvidosos = set()
    for r in infantil:
        login = (r.get("login") or "").strip().lower()
        a = por_login.get(login)
        if a is None:
            continue
        mesmo_nome = _primeiro_nome(_nome_completo(a)) == _primeiro_nome(_nome_completo(r))
        mesmo_nascimento = data_vscyber(a.get("nascimento")) == data_vscyber(r.get("nascimento")) is not None
        if not (mesmo_nome and mesmo_nascimento):
            duvidosos.add(login)
    return duvidosos


def _grupo_historico(db, piso_nome):
    """Mapa inativo onde ficam as estacoes antigas daquele piso."""
    piso = db.query(Piso).filter(Piso.nome == piso_nome).first()
    nome = f"VSCyber {piso_nome} (histórico)"
    grupo = db.query(GrupoEstacao).filter(GrupoEstacao.nome == nome).first()
    if grupo is None:
        grupo = GrupoEstacao(nome=nome, ativo=False, piso_id=piso.id if piso else None, cor="#64748b")
        db.add(grupo)
        db.flush()
    return grupo


def _nome_estacao(nome_vs, sufixo):
    fim = f" ({sufixo})"
    return (nome_vs or "?").strip()[: 20 - len(fim)] + fim


def importar_conexoes(db, conexoes, nomes_estacao, login_por_id, sufixo, piso_nome, desde: date,
                      ignorar_logins=frozenset()):
    """Cria as sessoes (quem chama faz o commit). Devolve as contagens."""
    grupo = _grupo_historico(db, piso_nome)
    clientes = {u.login.strip().lower(): u.id for u in db.query(Usuario).filter(Usuario.perfil == "cliente")}
    estacoes = {e.nome: e for e in db.query(Estacao).filter(Estacao.nome.like(f"% ({sufixo})"))}
    ja = {(s.cliente_id, s.estacao_id, s.iniciada_em) for s in
          db.query(Sessao.cliente_id, Sessao.estacao_id, Sessao.iniciada_em).filter(Sessao.motivo_encerramento == MOTIVO)}
    limite = datetime.combine(desde, datetime.min.time()).replace(tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)
    r = {"importadas": 0, "antes_da_data": 0, "sem_fim": 0, "sem_cliente": 0, "invalidas": 0,
         "ja_importadas": 0, "duvidosas": 0}
    novas = []
    for c in conexoes:
        inicio = _hora_vscyber(c.get("DHINI"))
        if inicio is None:
            r["invalidas"] += 1
            continue
        if inicio < limite:
            r["antes_da_data"] += 1
            continue
        fim = _hora_vscyber(c.get("DHFIM"))
        if fim is None:
            r["sem_fim"] += 1
            continue
        if not (inicio < fim <= inicio + USO_MAXIMO):
            r["invalidas"] += 1
            continue
        login = (login_por_id.get((c.get("IDCLI") or "").strip()) or "").strip().lower()
        if login in ignorar_logins:
            r["duvidosas"] += 1
            continue
        cliente_id = clientes.get(login)
        if not cliente_id:
            r["sem_cliente"] += 1
            continue
        nome = _nome_estacao(nomes_estacao.get((c.get("IDESTC") or "").strip()), sufixo)
        estacao = estacoes.get(nome)
        if estacao is None:
            estacao = Estacao(nome=nome, grupo_id=grupo.id, ativa=False, status="desligada")
            db.add(estacao)
            db.flush()
            estacoes[nome] = estacao
        chave = (cliente_id, estacao.id, inicio)
        if chave in ja:
            r["ja_importadas"] += 1
            continue
        ja.add(chave)
        uso = int((fim - inicio).total_seconds())
        novas.append({"cliente_id": cliente_id, "estacao_id": estacao.id, "iniciada_em": inicio,
                      "encerrada_em": fim, "tempo_total_segundos": uso, "tempo_consumido_segundos": uso,
                      "motivo_encerramento": MOTIVO, "pausada": False, "tempo_pausado_segundos": 0})
        r["importadas"] += 1
        if len(novas) >= 5000:
            db.bulk_insert_mappings(Sessao, novas)
            novas = []
    if novas:
        db.bulk_insert_mappings(Sessao, novas)
    db.flush()
    return r


def main(argv=None):
    p = argparse.ArgumentParser(description="Importa o historico de uso do VSCyber")
    p.add_argument("--aplicar", action="store_true", help="grava no banco (sem isso, so simula)")
    p.add_argument("--desde", default="2022-01-01", help="AAAA-MM-DD (padrao 2022-01-01)")
    p.add_argument("--pasta", default=PASTA_VSCYBER, help="pasta Arquivos VSCyber")
    args = p.parse_args(argv)
    desde = date.fromisoformat(args.desde)

    from app.database import SessionLocal, init_db
    from importar_infantil import _backup_antes

    bases = []
    for pasta, sufixo, piso in BASES:
        raiz = os.path.join(args.pasta, pasta)
        if not os.path.exists(os.path.join(raiz, "tabelas", "CON.csv")):
            print(f"{pasta}: sem tabelas/CON.csv, pulando")
            continue
        clientes = ler_csv(os.path.join(raiz, "clientes_importacao.csv"))
        bases.append((pasta, sufixo, piso, raiz, clientes))
    if not bases:
        raise SystemExit("Nenhum export do VSCyber encontrado (rode o exportar_fdb.py)")
    adulto = next((b[4] for b in bases if b[0] == "export"), [])
    infantil = next((b[4] for b in bases if b[0] == "export_infantil"), [])
    duvidosos = logins_duvidosos(adulto, infantil)

    init_db()
    if args.aplicar:
        _backup_antes()
    db = SessionLocal()
    try:
        for pasta, sufixo, piso, raiz, clientes in bases:
            nomes = {r["IDESTC"].strip(): r["NOME"] for r in ler_csv(os.path.join(raiz, "tabelas", "ESTC.csv"))}
            login_por_id = {r["id_vscyber"].strip(): r["login"] for r in clientes}
            conexoes = ler_csv(os.path.join(raiz, "tabelas", "CON.csv"))
            print(f"\n{pasta} (piso {piso}): {len(conexoes)} usos no VSCyber")
            r = importar_conexoes(db, conexoes, nomes, login_por_id, sufixo, piso, desde,
                                  ignorar_logins=duvidosos if pasta == "export_infantil" else frozenset())
            print(f"  importados:                      {r['importadas']}")
            print(f"  antes de {desde.strftime('%d/%m/%Y')}:              {r['antes_da_data']}")
            print(f"  sem horario de fim:              {r['sem_fim']}")
            print(f"  cliente nao existe no MatheCafe: {r['sem_cliente']}")
            print(f"  login para conferir (fora):      {r['duvidosas']}")
            print(f"  registro quebrado:               {r['invalidas']}")
            print(f"  ja importados antes:             {r['ja_importadas']}")
        if args.aplicar:
            db.commit()
            print("\nGravado.")
        else:
            db.rollback()
            print("\nSimulacao: nada foi gravado. Para gravar: python importar_historico.py --aplicar")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
