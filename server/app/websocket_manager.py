from fastapi import WebSocket
from typing import Dict
import json

class ConnectionManager:
    def __init__(self):
        self.paineis: list[WebSocket] = []
        self.usuario_do_painel: Dict[WebSocket, str] = {}  # ws -> id do usuario (pisos do grupo)
        self.estacoes: Dict[int, WebSocket] = {}

    # ── Painéis ──────────────────────────────────────────────────────────────
    async def conectar_painel(self, ws: WebSocket, usuario_id=None):
        await ws.accept()
        self.paineis.append(ws)
        if usuario_id:
            self.usuario_do_painel[ws] = usuario_id

    def desconectar_painel(self, ws: WebSocket):
        self.paineis.remove(ws) if ws in self.paineis else None
        self.usuario_do_painel.pop(ws, None)

    def _filtro_de_pisos(self, dados: dict):
        """Quais paineis recebem o evento: o operador de um grupo com pisos so
        recebe os das estacoes (e clientes da fila) desses pisos. Devolve uma
        funcao ws -> bool, ou None (todos recebem)."""
        if not self.usuario_do_painel:
            return None
        from app.database import SessionLocal
        from app.models import Estacao, Usuario
        from app.permissoes import pisos_do_usuario
        from app.pisos import piso_da_estacao, piso_do_cliente
        db = SessionLocal()
        try:
            pisos = {ws: pisos_do_usuario(db, uid) for ws, uid in self.usuario_do_painel.items()}
            if all(p is None for p in pisos.values()):
                return None
            piso = None
            if dados.get("estacao_id"):
                e = db.get(Estacao, dados["estacao_id"])
                piso = piso_da_estacao(e) if e else None
            elif isinstance(dados.get("cliente"), dict) and dados["cliente"].get("cliente_id"):
                c = db.get(Usuario, dados["cliente"]["cliente_id"])
                piso = piso_do_cliente(c) if c else None
            elif dados.get("cliente_id"):
                c = db.get(Usuario, dados["cliente_id"])
                piso = piso_do_cliente(c) if c else None
            if piso is None:
                return None
            piso_id = piso.id
        finally:
            db.close()
        return lambda ws: pisos.get(ws) is None or piso_id in pisos[ws]

    async def broadcast_paineis(self, evento: str, dados: dict):
        msg = json.dumps({"evento": evento, "dados": dados})
        try:
            recebe = self._filtro_de_pisos(dados)
        except Exception:
            recebe = None  # na duvida, como antes
        mortos = []
        for ws in list(self.paineis):
            if recebe is not None and not recebe(ws):
                continue
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
