"""Importação do histórico de uso do VSCyber (importar_historico.py), num banco em memória."""
import os
import sys
import tempfile

if "app.database" not in sys.modules:  # rodando este arquivo sozinho: nunca o cybercafe.db
    _tmp = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/teste.db"
    os.environ["SECRET_KEY"] = "chave-so-dos-testes-" + "x" * 40

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Estacao, GrupoEstacao, Piso, Sessao, Usuario
from importar_historico import importar_conexoes, logins_duvidosos

DESDE = date(2022, 1, 1)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine)()
    sessao.add_all([Piso(nome="Adulto", cor="#6366f1", padrao=True), Piso(nome="Infantil", cor="#ec4899")])
    for login, nome in (("bn1", "Ana Lima"), ("bn2", "Bruno"), ("bn3", "Caio")):
        sessao.add(Usuario(login=login, nome=nome, senha_hash="x", perfil="cliente"))
    sessao.commit()
    yield sessao
    sessao.close()


def _con(idcli, idestc, ini, fim):
    return {"IDCLI": idcli, "IDESTC": idestc, "DHINI": ini, "DHFIM": fim}


ESTACOES = {"7": "BSP-87", "8": "BSP-90"}
CLIENTES = {"101": "bn1", "102": "bn2", "103": "bn9"}  # bn9 nao existe no MatheCafe


def test_importa_sessoes_desde_a_data_em_estacoes_antigas(db):
    conexoes = [
        _con("101", "7", "2024-03-10 14:00:00.000000", "2024-03-10 15:30:00.000000"),  # entra (90 min)
        _con("102", "8", "2023-01-05 10:00:00", "2023-01-05 10:20:00"),                 # entra (20 min)
        _con("101", "7", "2019-06-01 10:00:00", "2019-06-01 11:00:00"),                 # antes de 2022
        _con("101", "7", "2024-03-11 14:00:00", ""),                                   # sem fim
        _con("103", "7", "2024-03-12 14:00:00", "2024-03-12 15:00:00"),                 # cliente nao existe
        _con("101", "7", "2024-03-13 14:00:00", "2024-03-13 13:00:00"),                 # fim antes do inicio
    ]
    r = importar_conexoes(db, conexoes, ESTACOES, CLIENTES, sufixo="VS", piso_nome="Adulto", desde=DESDE)
    db.commit()
    assert r == {"importadas": 2, "antes_da_data": 1, "sem_fim": 1, "sem_cliente": 1, "invalidas": 1,
                 "ja_importadas": 0, "duvidosas": 0}
    s = db.query(Sessao).join(Estacao).filter(Estacao.nome == "BSP-87 (VS)").one()
    # 14:00 em Brasilia = 17:00 UTC; uso pelo relogio do VSCyber
    assert s.iniciada_em == datetime(2024, 3, 10, 17, 0) and s.tempo_consumido_segundos == 5400
    assert s.motivo_encerramento == "vscyber" and s.cliente.login == "bn1"
    est = s.estacao
    assert est.ativa is False and est.grupo.ativo is False and est.grupo.piso.nome == "Adulto"


def test_rodar_de_novo_nao_duplica(db):
    conexoes = [_con("101", "7", "2024-03-10 14:00:00", "2024-03-10 15:00:00")]
    importar_conexoes(db, conexoes, ESTACOES, CLIENTES, sufixo="VS", piso_nome="Adulto", desde=DESDE)
    db.commit()
    r = importar_conexoes(db, conexoes, ESTACOES, CLIENTES, sufixo="VS", piso_nome="Adulto", desde=DESDE)
    db.commit()
    assert r["importadas"] == 0 and r["ja_importadas"] == 1
    assert db.query(Sessao).count() == 1
    assert db.query(Estacao).count() == 1 and db.query(GrupoEstacao).count() == 1


def test_infantil_vai_para_estacoes_e_mapa_do_infantil(db):
    conexoes = [_con("101", "7", "2025-02-02 09:00:00", "2025-02-02 09:45:00")]
    importar_conexoes(db, conexoes, ESTACOES, CLIENTES, sufixo="VSI", piso_nome="Infantil", desde=DESDE)
    db.commit()
    est = db.query(Estacao).one()
    assert est.nome == "BSP-87 (VSI)" and est.grupo.piso.nome == "Infantil"


def test_logins_duvidosos_ficam_de_fora(db):
    adulto = [{"login": "bn1", "nome": "Ana", "sobrenome": "Lima", "nascimento": "05/09/1989 00:00"},
              {"login": "bn2", "nome": "Bruno", "sobrenome": "", "nascimento": "01/01/2000 00:00"}]
    infantil = [{"login": "bn1", "nome": "Ana", "sobrenome": "Lima", "nascimento": "1989-09-05 00:00:00"},  # mesma
                {"login": "bn2", "nome": "Beatriz", "sobrenome": "", "nascimento": "2015-01-01 00:00:00"},  # outra
                {"login": "bn7", "nome": "Davi", "sobrenome": "", "nascimento": "2016-01-01 00:00:00"}]     # so infantil
    duvidosos = logins_duvidosos(adulto, infantil)
    assert duvidosos == {"bn2"}
    conexoes = [_con("102", "7", "2025-02-02 09:00:00", "2025-02-02 09:45:00")]
    r = importar_conexoes(db, conexoes, ESTACOES, CLIENTES, sufixo="VSI", piso_nome="Infantil", desde=DESDE,
                          ignorar_logins=duvidosos)
    assert r["duvidosas"] == 1 and r["importadas"] == 0
