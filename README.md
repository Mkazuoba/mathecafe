# MatheCafé

Sistema de gerenciamento de computadores de uso público da **SP Leituras**, feito para substituir o VSCyber (descontinuado). O operador libera o cliente pelo painel, o cliente faz login no PC e usa o computador pelo tempo disponível; o painel acompanha tudo em tempo real.

## Peças

| Pasta | O que é | Onde roda |
|---|---|---|
| `server/` | API FastAPI + WebSocket + painel web | um servidor (ou o Render) |
| `server/app/static/` | painel atual (HTML puro): Painel, Clientes, Mapa, Configurações | servido pelo próprio servidor |
| `agente/` | app Windows (Tkinter) que controla cada PC: launcher, bloqueio de programas, modo manutenção | em cada estação |

## Começo rápido

```bash
cd server
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m app.cli          # cria o administrador
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Painel em http://127.0.0.1:8000 · API interativa em http://127.0.0.1:8000/docs

O passo a passo completo, incluindo o agente, os testes e o deploy, está em [COMO_RODAR.md](COMO_RODAR.md).

## Documentos

- [COMO_RODAR.md](COMO_RODAR.md) — instalação do zero, primeiro uso, testes, deploy
- [ARQUITETURA.md](ARQUITETURA.md) — como o sistema funciona hoje
- [CHANGELOG.md](CHANGELOG.md) — o que mudou e quando
- [Roadmap](https://claude.ai/artifact/DzDETNJFr5jxzD6FCdKCEC) — tarefas por ciclo, com status
