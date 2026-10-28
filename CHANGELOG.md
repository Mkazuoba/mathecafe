# Changelog

## 2026-10-28 — Agente abre sozinho no logon (Ciclo 3, tarefa 3.3)

- **Causa**: a tarefa agendada rodava como SYSTEM (sessão 0, sem área de trabalho), então a janela do agente nunca aparecia. Além disso, o `instalar.bat` deixou de criar o `venv` (o agente morria sem `websockets`/`psutil`) e usava o Python e a pasta do perfil do admin, que o `cliente` não lê.
- **`instalar.bat`**: copia o agente para `C:\MatheCafe`, cria o `venv` lá, dá ao `cliente` escrita na pasta (cfg e auto-update) e recusa Python instalado só para um usuário. Senha do `cliente` não expira.
- **`registrar_tarefa.ps1`** (novo): tarefa `MatheCafe-Agente` no logon do `cliente`, `LogonType Interactive`, `pythonw`, sem o limite padrão de 3 dias e reabrindo se cair. Remove a tarefa antiga `MatheCafe_Agente` (SYSTEM no boot), que abria um segundo agente invisível.
- **`desinstalar.bat`** (novo) substitui `instalar_autostart.bat`/`desinstalar_autostart.bat`, removidos.
- `.gitattributes`: `.bat` e `.ps1` sempre com CRLF (o `cmd` se perde em `goto`/rótulos com LF, como num zip baixado do GitHub).

## 2026-10-23 — Cor e renomeação de grupos (Ciclo 5)

- **Cor por grupo**: nova coluna `cor` (hex, padrão `#6366f1`) em `GrupoEstacao`. Persistida no banco via migração automática do SQLite.
- **API de grupos atualizada**: `GET /api/estacoes/grupos` retorna `cor`; `POST` e `PUT` aceitam e persistem a cor. `serial_estacao` expõe `grupo_cor` para o Mapa.
- **Mapa — abas coloridas**: a aba do grupo ativo usa a cor de fundo; nas abas inativas aparece um ponto colorido ao lado do nome.
- **Mapa — Pino colorido**: quando a estação está livre, a borda inferior do card usa a cor do grupo (via `borderBottomColor` inline); outros status mantêm as cores semânticas.
- **Configurações > Grupos**: edição inline de nome, cor (color picker nativo) e tempo padrão — botão "Salvar" aparece apenas quando há alteração.

## 2026-10-23 — Auto-update do agente + melhorias no painel (Ciclo 3)

- **Auto-update do agente**: ao iniciar, o agente consulta `GET /api/agente/versao`; se a versão do servidor for maior, baixa `GET /api/agente/download`, substitui o próprio arquivo (`os.replace`) e reinicia o processo (`os.execv`). A partir da v1.2.0 as atualizações são automáticas — só a primeira instalação é manual.
- **Versão visível**: barra de título da janela mostra `MatheCafe v1.2.0 - <estação>` e o header exibe o número de versão em cinza ao lado do nome.
- **Diálogo de atualização**: antes de baixar, aparece uma caixa informando a versão atual e a nova — facilita diagnóstico e dá visibilidade ao operador.
- **Novo router `/api/agente/`** (`server/app/routers/agente.py`): dois endpoints sem autenticação — `/versao` lê a constante `VERSAO` do arquivo distribuído; `/download` serve o arquivo. Para publicar uma nova versão: incremente `VERSAO` em `agente/agente.py`, copie para `server/agente_dist/agente.py` e commite ambos.
- **Painel — aviso de saldo removido**: o texto "Sem saldo: receberá o tempo padrão" não aparece mais nos cards de cliente.
- **Painel — botão de editar saldo removido**: operadores não podem mais alterar o saldo diretamente pelo card; a edição vai ser centralizada numa tela de Clientes futura.
- **Histórico de uso — filtros**: novo filtro por cliente (select com nomes), por estação (select com nomes) e por intervalo de datas (De / Até), com botão "Limpar filtros". Limite de registros aumentado de 200 para 500.
- `.gitignore`: pasta `Arquivos VSCyber/` adicionada para evitar commits acidentais de dados legados.
- **Correção — `/api/agente/versao` retornava `0.0.0`**: o router procurava `server/app/agente_dist` em vez de `server/agente_dist`.
- **Correção — loop de auto-update**: o `agente.py` tinha duas declarações de `VERSAO`; agora há só a do topo, e um teste garante isso.

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
