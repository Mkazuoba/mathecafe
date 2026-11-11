from fastapi import WebSocket
from typing import Dict
import json

class ConnectionManager:
    def __init__(self):
        self.paineis: list[WebSocket] = []
        self.estacoes: Dict[int, WebSocket] = {}

    # ── Painéis ──────────────────────────────────────────────────────────────
    async def conectar_painel(self, ws: WebSocket):
        await ws.accept()
        self.paineis.append(ws)

    def desconectar_painel(self, ws: WebSocket):
        self.paineis.remove(ws) if ws in self.paineis else None

    async def broadcast_paineis(self, evento: str, dados: dict):
        msg = json.dumps({"evento": evento, "dados": dados})
        mortos = []
        for ws in self.paineis:
            try:
                await ws.send_text(msg)
            except Exception:
                mortos.append(ws)
        for ws in mortos:
            self.desconectar_painel(ws)

    # ── Estações ──────────────────────────────────────────────────────────────
    # Pelo id da estacao (6.18): o nome se repete entre os pisos (AD-01 no Adulto
    # e no Infantil) e muda quando o admin renomeia.
    async def conectar_estacao(self, estacao_id: int, ws: WebSocket):
        await ws.accept()
        self.estacoes[estacao_id] = ws

    def desconectar_estacao(self, estacao_id: int, ws: WebSocket = None):
        # Com ws informado, só remove se ainda for a mesma conexão: se o agente
        # já reconectou, a conexão antiga não pode derrubar a nova.
        if ws is None or self.estacoes.get(estacao_id) is ws:
            self.estacoes.pop(estacao_id, None)

    def estacao_conectada(self, estacao_id: int) -> bool:
        return estacao_id in self.estacoes

    async def enviar_estacao(self, estacao_id: int, evento: str, dados: dict):
        ws = self.estacoes.get(estacao_id)
        if ws:
            try:
                await ws.send_text(json.dumps({"evento": evento, "dados": dados}))
            except Exception:
                # NÃO remove a estação aqui — o handler ws_estacao detecta
                # a desconexão real via WebSocketDisconnect e limpa corretamente.
                pass

    async def broadcast_estacoes(self, evento: str, dados: dict):
        msg = json.dumps({"evento": evento, "dados": dados})
        mortos = []
        for estacao_id, ws in self.estacoes.items():
            try:
                await ws.send_text(msg)
            except Exception:
                mortos.append(estacao_id)
        for estacao_id in mortos:
            self.desconectar_estacao(estacao_id)

    def estacoes_online(self) -> list[int]:
        return list(self.estacoes.keys())

manager = ConnectionManager()
