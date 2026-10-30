"""Imagens enviadas pelo painel (foto do cliente, cartazes da programação).

O painel reduz a imagem e manda em data URL; aqui ela é decodificada e o tipo
sai da assinatura do arquivo, não do que o navegador diz."""
import base64
import binascii
from typing import Optional

from fastapi import HTTPException

_ASSINATURAS = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


def tipo_da_imagem(dados: bytes) -> Optional[str]:
    for assinatura, tipo in _ASSINATURAS.items():
        if dados.startswith(assinatura):
            return tipo
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    return None


def ler_imagem(data_url: str, max_bytes: int) -> tuple[str, bytes]:
    """(tipo, bytes) da imagem, ou 400 com o motivo."""
    try:
        dados = base64.b64decode(data_url.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Imagem inválida")
    if len(dados) > max_bytes:
        raise HTTPException(status_code=400, detail=f"Imagem grande demais (máximo {max_bytes // 1_000_000} MB)")
    tipo = tipo_da_imagem(dados)
    if not tipo:
        raise HTTPException(status_code=400, detail="Envie uma imagem JPG, PNG ou WebP")
    return tipo, dados
