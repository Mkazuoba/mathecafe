# MatheCafé — contexto para o Claude Code

Sistema de gerenciamento de computadores públicos da **SP Leituras** (bibliotecas públicas de São Paulo), substituto do **VSCyber** (descontinuado). Operador libera o cliente no painel → cliente loga no PC → sessão cronometrada → saldo salvo.

- Desenvolvedor: Matheus. **Conversas em português.**
- Abordagem: **ciclos curtos e testáveis, uma funcionalidade por vez**.
- Tarefas e status: [roadmap](https://claude.ai/artifact/DzDETNJFr5jxzD6FCdKCEC) (artifact com banco `ciclos`/`tarefas`). Atualize o status lá ao começar/terminar uma tarefa e leia as anotações antes de começar.
- Projeto irmão usado como molde de organização: `../Banners SPLEITURAS` (central + unidades, FastAPI, React + Vite + Tailwind no painel).
- **Antes de analisar o código, compare com o GitHub** (`git fetch` e `git status -sb`). Matheus às vezes envia arquivos pelo site do GitHub, e esta pasta já ficou para trás.

## Documentos — leia antes de mexer

- [ARQUITETURA.md](ARQUITETURA.md) — como funciona **hoje** (arquivos, tabelas, fluxo, eventos WS, decisões). Mantenha atualizado quando mudar comportamento.
- [COMO_RODAR.md](COMO_RODAR.md) — instalação, primeiro uso, testes, deploy.
- [CHANGELOG.md](CHANGELOG.md) — registre cada ciclo concluído.

## Estrutura

```
server/            FastAPI — rodar de dentro desta pasta
  app/main.py      app + WebSockets (/ws/painel, /ws/estacao/{nome}) + serve static/
  app/routers/     auth, clientes, estacoes (+grupos, fila), sessoes, apps, operadores, config, relatorios
  app/static/      BUILD do painel React — gerado por `npm run build`, commitado (Render não tem Node)
  app/static_antigo/  painel HTML anterior, em /antigo durante a transição
  tests/           pytest
  frontend/        painel React + Vite + Tailwind (molde do Banners)
  main.py          só reexporta app.main:app (start command antigo do Render)
agente/agente.py   app Windows (Tkinter) em cada estação
```

## Comandos

```bash
cd server
venv\Scripts\activate
python -m app.cli                                   # cria admin
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
python -m pytest -q                                 # testes (requirements-dev.txt)
```

Rode os testes antes de dar um ciclo por concluído e acrescente um teste para cada bug corrigido (escreva o teste antes da correção e veja-o falhar). O TestClient cancela o handler WS quando a conexão fecha, então a espera de 8s até offline só se testa com o servidor rodando — use `127.0.0.1`, não `localhost` (no Windows o IPv6 atrasa ~2s).

## Regras e armadilhas

- **Sem passlib** — bcrypt direto (`app/security.py`).
- **`db.expire_all()`** a cada mensagem no handler da estação (`main.py`): a sessão do SQLAlchemy vive a conexão WS inteira e ficaria com cache velho. Não remover.
- **`autorizacoes.cliente_id` é único** — reaproveitar o registro ao reliberar (resetar `usado=False`), nunca criar outro.
- **Queda do PC encerra a sessão** (`conexao_perdida`): o agente volta ao login quando perde a conexão, então o servidor não pode deixar a sessão aberta.
- **Nada de emoji em `print`** no servidor — derruba a inicialização num console Windows (cp1252). No agente, emoji só dentro da interface Tkinter.
- **Saldo sempre em HH:MM:SS** em todo o painel.
- **Agente precisa rodar como Administrador** para o psutil encerrar processos.
- **SQLite no Render zera a cada deploy** — produção vai para PostgreSQL (Supabase). A migração leve de colunas em `database.py` só funciona no SQLite.
- **Node.js é portátil nesta máquina**, em `%LOCALAPPDATA%\Programs\nodejs` (fora do PATH). No bash: `export PATH="$LOCALAPPDATA/Programs/nodejs:$PATH"` antes de `npm`.
- **Mexeu no painel? Rode `npm run build`** em `server/frontend` e commite `server/app/static/` junto — é o que o servidor serve.
- Painel React: dados compartilhados em `src/lib/dados.tsx` (não buscar a mesma lista em cada tela); textos sempre via JSX, nunca `dangerouslySetInnerHTML`.
