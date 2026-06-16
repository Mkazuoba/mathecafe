# MatheCafé

Sistema de gerenciamento de Cyber Café — substituto do VSCyber.

## Como rodar localmente

```bash
cd server
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Acesse: http://localhost:8000
Login: admin / admin123

## Rodar o agente na estação

```bash
cd agente
pip install -r requirements.txt
python agente.py --servidor ws://IP_DO_SERVIDOR:8000 --estacao PC-01
```

## Deploy no Render

- Root Directory: `server`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Estrutura

```
mathecafe/
├── server/          ← FastAPI (servidor)
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── auth.py
│   ├── config.py
│   ├── websocket_manager.py
│   ├── requirements.txt
│   └── routes/
│       ├── auth.py
│       ├── clientes.py
│       ├── estacoes.py
│       ├── sessoes.py
│       └── apps.py
├── frontend/
│   └── index.html   ← Painel web
└── agente/
    ├── agente.py    ← App das estações Windows
    └── requirements.txt
```
