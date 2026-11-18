"""Estilos da tela do cliente (17/11): escolhidos por estacao no painel.

O agente tem a paleta e a fonte de cada um (ESTILOS em agente.py, mesmas
chaves daqui); o servidor so guarda qual vale para cada PC e avisa o agente
(evento estilo_estacao). "padrao" e o visual de sempre.
"""
ESTILOS = {
    "padrao": "Padrão",
    "biblioteca": "Biblioteca (teste)",
    "caderno": "Caderno (teste)",
}


# a partir de qual versao do agente cada estilo aparece no PC (o resto: 1.28.0)
DESDE = {"caderno": "1.29.0"}


def estilo_de(estacao) -> str:
    return estacao.estilo if estacao.estilo in ESTILOS else "padrao"
