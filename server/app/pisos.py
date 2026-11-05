"""Piso adulto / infantil (4.7).

O cliente tem o piso no cadastro; a estacao, o do grupo dela. Estacao sem
grupo, ou grupo sem piso, conta como adulto: so o que foi marcado infantil
recebe criancas, entao um erro de configuracao cai para o lado seguro.
"""
from typing import Literal, Optional

Piso = Literal["adulto", "infantil"]
PISO_PADRAO = "adulto"
NOMES = {"adulto": "Adulto", "infantil": "Infantil"}


def piso_da_estacao(estacao) -> str:
    grupo = estacao.grupo
    return (grupo.piso if grupo is not None else None) or PISO_PADRAO


def piso_do_cliente(cliente) -> str:
    return cliente.piso or PISO_PADRAO


def recusa_de_piso(cliente, estacao) -> Optional[str]:
    """Motivo para recusar o cliente nesta estacao, ou None se o piso bate."""
    do_cliente, da_estacao = piso_do_cliente(cliente), piso_da_estacao(estacao)
    if do_cliente == da_estacao:
        return None
    return (f"Este cadastro é do piso {NOMES[do_cliente]} e este computador é do piso "
            f"{NOMES[da_estacao]}. Procure o atendimento.")
