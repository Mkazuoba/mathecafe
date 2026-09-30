# Changelog

## 2026-09-30 — Launcher como fundo e modo teste (Ciclo 3)

- Launcher não minimiza mais ao abrir um app: fica em tela cheia atrás, cobrindo a área de trabalho (como VSCyber/Senet). Ao fechar o app, o cliente volta ao launcher.
- Faixa "Em uso" no launcher com os apps abertos; clicar traz o app para a frente.
- `--teste` no agente (`iniciar.bat ... teste`): não fecha nenhum programa nem reinicia o PC, só registra no log. Para testar no PC do desenvolvedor sem perder os outros programas.

## 2026-09-29 — Painel em React (Ciclo 2)

- Painel reescrito em React + Vite + Tailwind (`server/frontend`), com as mesmas 4 telas e o mesmo visual. O build fica em `server/app/static`, então o deploy não precisa de Node.
- Endereços próprios por tela (`/clientes`, `/mapa`, `/configuracoes?secao=apps`...), que funcionam ao recarregar a página.
- Mapa: aba "Sem grupo" (antes essas estações não apareciam), troca de grupo no painel lateral, arrastar com o mouse ou o dedo.
- Painel: cliente em sessão aparece como "Em uso no PC-X" e não pode ser liberado de novo; lista só clientes ativos.
- Saldo editado sempre em HH:MM:SS, com validação do formato.
- Segurança: o WebSocket do painel passou a exigir login; nomes e textos não são mais inseridos como HTML.
- Painel antigo disponível em `/antigo` durante a transição.
- `server/main.py` mantém o start command antigo do Render funcionando.

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
