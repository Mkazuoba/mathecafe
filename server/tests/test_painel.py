"""Regras do painel React conferidas no codigo-fonte (o painel nao tem testes
proprios). Clientes sao ~43k: nenhuma tela carrega a lista inteira."""
import os
import re

SRC = os.path.join(os.path.dirname(__file__), "..", "frontend", "src")


def _arquivos():
    for raiz, _, nomes in os.walk(SRC):
        for n in nomes:
            if n.endswith((".ts", ".tsx")):
                caminho = os.path.join(raiz, n)
                with open(caminho, encoding="utf-8") as f:
                    yield os.path.relpath(caminho, SRC), f.read()


def test_nenhuma_tela_usa_lista_de_clientes_do_contexto():
    # A lista "clientes" do dados.tsx ficou sempre vazia quando a busca foi
    # para o servidor: a aba Clientes e o filtro do Relatorio CSV quebraram.
    usam = [nome for nome, src in _arquivos()
            if re.search(r"\{[^}]*\bclientes\b[^}]*\}\s*=\s*useDados\(\)", src)]
    assert usam == [], f"use useBuscaClientes em vez da lista do contexto: {usam}"
    dados = dict(_arquivos())[os.path.join("lib", "dados.tsx")]
    assert not re.search(r"^\s*clientes: Cliente\[\]", dados, re.M)


def test_historico_por_estacao_nao_repete_o_interrogacao():
    # Por estação o caminho já vem com ?piso_id=N; o hook dos históricos
    # acrescentava "?de=...", e a API recebia piso_id="1?" (erro 422 na tela).
    hist = dict(_arquivos())[os.path.join("pages", "Historicos.tsx")]
    assert "`${caminho}?${" not in hist
    assert "?piso_id=" in hist  # o caso que pede o "&"
