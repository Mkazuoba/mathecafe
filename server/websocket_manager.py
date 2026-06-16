from fastapi import WebSocket
from typing import Dict
import json

class ConnectionManager:
    def __init__(self):
        self.paineis: list[WebSocket] = []
        self.estacoes: Dict[str, WebSocket] = {}

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
    async def conectar_estacao(self, nome: str, ws: WebSocket):
        await ws.accept()
        self.estacoes[nome] = ws

    def desconectar_estacao(self, nome: str):
        self.estacoes.pop(nome, None)

    async def enviar_estacao(self, nome: str, evento: str, dados: dict):
        ws = self.estacoes.get(nome)
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
        for nome, ws in self.estacoes.items():
            try:
                await ws.send_text(msg)
            except Exception:
                mortos.append(nome)
        for nome in mortos:
            self.desconectar_estacao(nome)

    def estacoes_online(self) -> list[str]:
        return list(self.estacoes.keys())

manager = ConnectionManager()
