# Como rodar o MatheCafé

## Requisitos

- **Python 3.11 ou mais novo** (testado no 3.14)
- Windows nas estações (o agente usa Tkinter e controla processos do Windows)

## 1. Servidor

```bash
cd server
python -m venv venv
venv\Scripts\activate            # no Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

Configuração (opcional para testar localmente, obrigatória em produção):

```bash
copy .env.example .env           # e troque o SECRET_KEY
```

Crie o administrador (senha com no mínimo 10 caracteres):

```bash
python -m app.cli
```

Suba o servidor:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` é o que permite que as estações acessem o servidor pelo IP da rede. Sem ele, o servidor só atende a própria máquina.

- Painel: http://127.0.0.1:8000
- API interativa: http://127.0.0.1:8000/docs

> Na própria máquina, use `127.0.0.1` em vez de `localhost`. No Windows, `localhost` tenta primeiro o IPv6 e perde cerca de 2s a cada conexão.

## 2. Painel web (React)

O painel já vem compilado em `server/app/static/`: para só usar o sistema, não precisa de Node. Para **mexer no painel**, instale o [Node.js LTS](https://nodejs.org) e:

```bash
cd server/frontend
npm install
npm run dev          # painel em http://localhost:5173, com recarga automática
```

O `npm run dev` usa o servidor Python (porta 8000) para `/api` e `/ws`, então deixe o `uvicorn` rodando junto.

Terminou uma mudança? Gere o build e faça o commit dos arquivos de `server/app/static/` junto com o código:

```bash
npm run build        # compila para server/app/static
```

O painel HTML anterior continua em http://127.0.0.1:8000/antigo/ durante a transição.

## 3. Primeiro uso (pelo painel)

1. **Configurações → Operadores**: cadastre os operadores.
2. **Configurações → Apps permitidos**: cadastre os programas que os clientes podem abrir (processo `.exe`, caminho completo e, se quiser, uma imagem de capa).
3. **Mapa → Modo configuração**: cadastre as estações (o nome, ex. `PC-01`, é o mesmo usado no agente) e arraste-as para a posição da sala.
4. **Clientes**: cadastre os clientes.
5. **Painel**: clique em **Liberar** (ou arraste o cliente para uma estação). Ele entra na fila e pode fazer login no PC.

## 4. Agente (em cada estação)

Precisa do Python 3.11+ na estação ([python.org](https://www.python.org/downloads/), marcando "Add python.exe to PATH"). Copie a pasta `agente/` para o PC e:

1. Dois cliques em **`instalar.bat`** (uma vez só): cria o ambiente e instala as dependências.
2. Dois cliques em **`iniciar.bat`**: pergunta o endereço do servidor e o nome da estação e abre o agente como Administrador (o Windows pede confirmação).

Ou direto, sem perguntas: `iniciar.bat ws://IP_DO_SERVIDOR:8000 PC-01`

Num PC de testes (o seu, por exemplo), acrescente `teste` no fim: `iniciar.bat ws://IP_DO_SERVIDOR:8000 PC-TESTE teste`. Nesse modo o agente **não fecha nenhum programa**; só registra no `agente.log` o que fecharia (`[teste] fecharia ...`). A faixa "MODO TESTE" aparece no topo do agente.

- O nome da estação precisa ser exatamente o cadastrado no Mapa.
- Rode como **Administrador** (o `iniciar.bat` já faz isso), senão o bloqueio de programas não funciona.
- Antes, confira a rede: no navegador da estação, `http://IP_DO_SERVIDOR:8000` precisa abrir o painel. Se não abrir, libere o Python no Firewall do Windows **da máquina do servidor** (redes privadas).
- Servidor no Render: use `wss://` em vez de `ws://`.
- **Modo manutenção**: `Ctrl+Shift+M` na estação, depois login e senha de um operador ou admin (conferidos pelo servidor; o agente precisa estar online).

## 5. Testes automáticos

```bash
cd server
pip install -r requirements-dev.txt
python -m pytest -q
```

Cobrem o fluxo de sessão (liberar duas vezes, saldo, encerramento pelo operador, queda do PC), exclusões, reconexão e o modo manutenção, com um banco temporário. Rode antes de cada commit.

A espera de 8s até a estação aparecer como desligada só se testa com o servidor rodando: o cliente de teste interrompe o servidor assim que a conexão fecha.

## 6. Deploy

### Render

- Root directory: `server`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (o antigo `uvicorn main:app ...` continua funcionando, via `server/main.py`)
- Não precisa de Node no Render: o painel compilado já está em `server/app/static/`.
- Variáveis: `SECRET_KEY`, e `ADMIN_LOGIN` / `ADMIN_SENHA` para criar o primeiro admin (o Render gratuito não tem terminal para rodar o `app.cli`).

> O SQLite do Render é apagado a cada deploy. Para uso real, configure `DATABASE_URL` com um PostgreSQL (Supabase).

### Docker

```bash
cd server
docker build -t mathecafe .
docker run -d -p 8000:8000 -v mathecafe-data:/data --env-file .env mathecafe
docker exec -it <container> python -m app.cli
```
