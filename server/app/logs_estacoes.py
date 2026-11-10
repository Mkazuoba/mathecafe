"""Log de comunicacao de cada estacao (o que o agente escrevia na tela do PC).

Fica so na memoria do servidor: as ultimas LIMITE linhas por estacao, pelo id
(sobrevive a renomear no painel). Reiniciar o servidor apaga; serve para
diagnosticar uma estacao agora, nao como historico.
"""
from collections import deque
from datetime import datetime

LIMITE = 300
TAMANHO_MAXIMO = 500

_logs: dict[int, deque] = {}


def registrar(estacao_id: int, msg, ts=None) -> dict:
    """Guarda uma linha. ts e a hora do PC (HH:MM:SS); agente antigo nao manda."""
    ts = str(ts)[:8] if ts else datetime.now().strftime("%H:%M:%S")
    linha = {"ts": ts, "msg": str(msg or "")[:TAMANHO_MAXIMO]}
    _logs.setdefault(estacao_id, deque(maxlen=LIMITE)).append(linha)
    return linha


def linhas(estacao_id: int) -> list[dict]:
    return list(_logs.get(estacao_id, ()))


def apagar(estacao_id: int) -> None:
    _logs.pop(estacao_id, None)
