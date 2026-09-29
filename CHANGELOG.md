# Changelog

## 2026-09-29 — Bugs confirmados (Ciclo 1)

- O servidor não subia num console Windows comum: emoji nas mensagens de inicialização. Removido.
- Depois de o operador encerrar uma sessão pelo painel, o PC usava o tempo padrão em vez do saldo devolvido. A conexão do PC agora relê o banco a cada mensagem.
- Excluir cliente ou operador com histórico dava erro 500: agora a resposta pede para desativar. Estação com histórico é desativada em vez de excluída.
- Uma conexão antiga do PC podia derrubar a nova numa reconexão.
- A estação aparecia como desligada durante a espera de 8s; agora a lista usa o status do banco, e o servidor zera os status ao iniciar.
- Quando o PC cai no meio de uma sessão, o servidor encerra a sessão (`conexao_perdida`) e devolve o tempo não usado. Antes a estação ficava presa como ocupada.
- Modo manutenção do agente: fim da senha fixa `admin123`; agora pede login de operador/admin, conferido pelo servidor.

## 2026-09-29 — Reorganização (Ciclo 0)

- Servidor reorganizado no pacote `server/app/` (rotas em `app/routers/`), no molde do sistema de Banners. Painel movido de `frontend/` para `server/app/static/`.
- Comando de início: `uvicorn app.main:app` (**o start command do Render precisa ser trocado**).
- Admin padrão `admin/admin123` não é mais criado: `python -m app.cli` ou `ADMIN_LOGIN`/`ADMIN_SENHA` no `.env`. Bancos existentes mantêm seus usuários.
- Dependências atualizadas (FastAPI 0.141, SQLAlchemy 2.1, bcrypt 5); roda em Python 3.11 a 3.14.
- `.gitignore`, `.env.example`, `Dockerfile`, testes automáticos (`python -m pytest -q`) e documentação (README, COMO_RODAR, ARQUITETURA).

## 2026-06-17 e antes

Histórico no git: launcher em grid com imagens, modo manutenção, bloqueio de programas, mapa, configurações, relatórios.
