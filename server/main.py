"""Compatibilidade com o start command antigo do Render (`uvicorn main:app`).

O app fica em app/main.py; prefira `uvicorn app.main:app`.
"""
from app.main import app  # noqa: F401
