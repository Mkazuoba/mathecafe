"""Importação do VSCyber do piso infantil (importar_infantil.py), num banco em memória."""
import os
import sys
import tempfile

if "app.database" not in sys.modules:  # rodando este arquivo sozinho: nunca o cybercafe.db
    _tmp = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/teste.db"
    os.environ["SECRET_KEY"] = "chave-so-dos-testes-" + "x" * 40

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Usuario
from importar_infantil import data_vscyber, importar_infantil, preencher_nascimento

HOJE = date(2026, 11, 5)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine)()
    yield sessao
    sessao.close()


def _cliente(db, login, nome, nasc=None, piso="adulto"):
    u = Usuario(login=login, nome=nome, senha_hash="x", perfil="cliente", piso=piso, data_nascimento=nasc)
    db.add(u)
    db.commit()
    return u


def _linha(login, nome, sobrenome="", nascimento=""):
    return {"login": login, "nome": nome, "sobrenome": sobrenome, "nascimento": nascimento}


def test_datas_nos_dois_formatos_do_vscyber():
    assert data_vscyber("05/09/1989 00:00") == date(1989, 9, 5)  # export do adulto
    assert data_vscyber("2018-04-09 00:00:00") == date(2018, 4, 9)  # export do infantil
    assert data_vscyber("") is None
    assert data_vscyber("lixo") is None


def test_preenche_nascimento_so_onde_esta_vazio(db):
    _cliente(db, "bn1", "Ana")
    _cliente(db, "bn2", "Bia", nasc=date(2000, 1, 1))
    n = preencher_nascimento(db, [_linha("bn1", "Ana", nascimento="05/09/1989 00:00"),
                                  _linha("bn2", "Bia", nascimento="02/02/2002 00:00"),
                                  _linha("bn9", "Fora", nascimento="03/03/2003 00:00")])
    assert n == 1
    assert db.query(Usuario).filter_by(login="bn1").one().data_nascimento == date(1989, 9, 5)
    assert db.query(Usuario).filter_by(login="bn2").one().data_nascimento == date(2000, 1, 1)
    assert db.query(Usuario).filter_by(login="bn9").first() is None  # nao cria ninguem


def test_cliente_novo_entra_no_infantil(db):
    r = importar_infantil(db, [_linha("bn10", "Caio", "Souza", "2018-04-09 00:00:00"),
                               _linha("bn11", "Davi", "", "2003-08-02 00:00:00")], HOJE, "hash")
    assert r["novos"] == 2
    caio = db.query(Usuario).filter_by(login="bn10").one()
    assert (caio.nome, caio.piso, caio.perfil, caio.data_nascimento) == ("Caio Souza", "infantil", "cliente",
                                                                         date(2018, 4, 9))
    # adulto hoje, mas cadastrado no infantil: entra no infantil (o piso nao depende da idade)
    assert db.query(Usuario).filter_by(login="bn11").one().piso == "infantil"


def test_mesma_pessoa_menor_de_18_passa_para_o_infantil(db):
    _cliente(db, "bn20", "Eva Lima", nasc=date(2012, 5, 1))
    r = importar_infantil(db, [_linha("bn20", "EVA", "Lima", "2012-05-01 00:00:00")], HOJE, "hash")
    assert r["para_infantil"] == 1 and r["novos"] == 0
    eva = db.query(Usuario).filter_by(login="bn20").one()
    assert eva.piso == "infantil"
    assert eva.piso_alterado_por and eva.piso_alterado_em
    assert db.query(Usuario).count() == 1  # nao duplica


def test_mesma_pessoa_maior_de_18_fica_no_adulto(db):
    _cliente(db, "bn21", "Fabio", nasc=date(2008, 11, 5))  # 18 anos hoje
    r = importar_infantil(db, [_linha("bn21", "Fabio", "", "2008-11-05 00:00:00")], HOJE, "hash")
    assert r["mantidos"] == 1
    assert db.query(Usuario).filter_by(login="bn21").one().piso == "adulto"


def test_login_igual_com_dados_diferentes_vai_para_conferir(db):
    _cliente(db, "bn30", "Gabriel", nasc=date(1990, 1, 1))
    _cliente(db, "bn31", "Helena")  # sem nascimento no MatheCafe: nao da para confirmar
    r = importar_infantil(db, [_linha("bn30", "Gabriel", "", "2015-01-01 00:00:00"),
                               _linha("bn31", "Helena", "", "2015-01-01 00:00:00")], HOJE, "hash")
    assert [c["login"] for c in r["conferir"]] == ["bn30", "bn31"]
    assert all(c["motivo"] for c in r["conferir"])
    assert db.query(Usuario).filter_by(login="bn30").one().piso == "adulto"  # nada muda
    assert db.query(Usuario).count() == 2


def test_rodar_de_novo_nao_duplica_nem_muda_o_piso(db):
    linhas = [_linha("bn40", "Ivo", "", "2003-08-02 00:00:00"), _linha("bn41", "Juca", "", "2018-01-01 00:00:00")]
    importar_infantil(db, linhas, HOJE, "hash")
    db.commit()
    r = importar_infantil(db, linhas, HOJE, "hash")
    assert r["novos"] == 0
    assert db.query(Usuario).count() == 2
    # Ivo tem 23 anos, mas ja estava no infantil: a segunda rodada nao o tira de la
    assert db.query(Usuario).filter_by(login="bn40").one().piso == "infantil"


def test_login_com_maiusculas_conta_como_o_mesmo(db):
    _cliente(db, "BN50", "Kika", nasc=date(2014, 3, 3))
    r = importar_infantil(db, [_linha("bn50", "Kika", "", "2014-03-03 00:00:00")], HOJE, "hash")
    assert r["para_infantil"] == 1 and r["novos"] == 0
