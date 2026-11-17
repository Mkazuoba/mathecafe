"""Estilos da tela do cliente (17/11): escolhidos por estacao no painel.

O agente tem a paleta e a fonte de cada um (ESTILOS em agente.py, mesmas
chaves daqui); o servidor so guarda qual vale para cada PC e avisa o agente
(evento estilo_estacao). "padrao" e o visual de sempre.
"""
ESTILOS = {
    "padrao": "Padrão",
    "biblioteca": "Biblioteca (teste)",
}


def estilo_de(estacao) -> str:
    return estacao.estilo if estacao.estilo in ESTILOS else "padrao"
