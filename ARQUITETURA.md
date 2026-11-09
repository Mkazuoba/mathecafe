# Arquitetura do MatheCafé

> Como o sistema funciona **hoje**. O que ainda falta está no [roadmap](https://claude.ai/artifact/DzDETNJFr5jxzD6FCdKCEC).
> Última revisão: 2026-10-23.

## Visão geral

```
  Operador                                   Cliente
     │                                          │
     ▼                                          ▼
┌──────────────┐   HTTP + WS    ┌──────────┐   WS    ┌──────────────────┐
│ Painel web   │ ◀────────────▶ │ Servidor │ ◀─────▶ │ Agente (cada PC) │
│ (navegador)  │  /api  /ws/    │ FastAPI  │ /ws/    │ agente.py        │
└──────────────┘    painel      └────┬─────┘ estacao └──────────────────┘
                                     │
                                ┌────▼─────┐
                                │  Banco   │  SQLite (dev) / PostgreSQL (prod)
                                └──────────┘
```

O painel e o agente **nunca se falam diretamente**. Tudo passa pelo servidor, que grava no banco e avisa o outro lado pelo WebSocket.

O WebSocket (e não um heartbeat HTTP, como no sistema de Banners) é necessário porque o servidor precisa **mandar ordens** para o PC, como "encerrar sessão agora".

## Servidor (`server/app/`)

| Arquivo | Papel |
|---|---|
| `main.py` | cria o app, registra as rotas, WebSockets do painel e das estações, serve o painel |
| `models.py` | tabelas (SQLAlchemy) |
| `database.py` | conexão, criação das tabelas, migração leve de colunas (só SQLite), dados iniciais |
| `config.py` | configurações lidas do `.env` |
| `security.py` | senhas (bcrypt) e tokens JWT; `requer_perfil(...)` protege as rotas |
| `tempo_diario.py` | tempo de uso por dia de cada cliente: cota, reset à meia-noite de Brasília, reservar o tempo da sessão |
| `websocket_manager.py` | guarda quem está conectado (painéis e estações) e envia mensagens |
| `cli.py` | `python -m app.cli` cria um administrador |
| `routers/` | `auth`, `clientes`, `estacoes` (+ grupos, posição no mapa, fila), `sessoes`, `apps`, `operadores`, `config`, `pisos`, `relatorios` (CSV e históricos por cliente/estação), `programacao` (cartazes do agente), `agente` (auto-update) |
| `imagens.py` | lê as imagens enviadas pelo painel (data URL), confere a assinatura do arquivo e o tamanho |
| `pisos.py` | pisos cadastrados (tabela `pisos`): o do cliente (cadastro) e o da estação (o do mapa; sem mapa ou mapa antigo sem piso = o piso padrão); `recusa_de_piso` dá o motivo da recusa; `garantir_pisos` cria Adulto (padrão) e Infantil na primeira subida e converte os pisos que eram texto (4.7a) |
| `importados.py` | sessões importadas do VSCyber (motivo `vscyber`): guardadas, mas fora de todos os históricos e relatórios enquanto `configuracoes.historico_vscyber_visivel` não for `true` (`so_visiveis`) |
| `registro.py` | `registrar(db, quem, acao, cliente, estacao, detalhe)`, chamado pelas rotas que mudam algo (liberar, tempo extra, encerrar, desligar, trocar piso...); `ROTULOS` dá o nome de cada ação no painel e no CSV |
| `horario.py` | horário de funcionamento (chave `horario_funcionamento` em `configuracoes`, um dia por linha, 0 = segunda): `decidir` diz, a cada batimento, se avisa (10 e 5 min antes de fechar) ou encerra as sessões (motivo `horario`, devolvendo o tempo); `esta_fechada` recusa o login no PC e o liberar direto |
| `backup.py` | backup diário do SQLite (`sqlite3.backup`, cópia consistente com o servidor gravando), um arquivo por dia em `BACKUP_PASTA`, guarda `BACKUP_DIAS` dias |
| `agente_dist/agente.py` | arquivo distribuído para auto-update; versão lida da constante `VERSAO` no topo |
| `static/` | **build** do painel React (gerado por `npm run build`; não editar à mão) |

`server/main.py` só reexporta `app.main:app`, para o start command antigo do Render continuar valendo.

## Painel (`server/frontend/`)

React 19 + Vite + Tailwind 4, no mesmo molde do `central/frontend` do sistema de Banners.

| Arquivo | Papel |
|---|---|
| `src/App.tsx` | rotas: `/login`, `/` (Painel), `/clientes`, `/mapa`, `/historicos`, `/configuracoes` (só admin) |
| `src/lib/api.ts` | chamadas à API com o token; 401 leva de volta ao login |
| `src/lib/dados.tsx` | dados compartilhados entre as telas (estações, fila, sessões, grupos), WebSocket `/ws/painel` com reconexão e o relógio das contagens. Carrega os **pisos** e guarda o escolhido (cabeçalho ou abas da tela Clientes, lembrado no navegador); entrega estações, mapas, fila e sessões só desse piso. `todosGrupos` é para configurar mapas e mover estações |
| `src/lib/piso.tsx` | piso escolhido no navegador, cor do piso (`--color-piso` no `:root`; `index.css` deriva `piso-fundo` e `piso-borda`), idade pela data de nascimento, `AbasPiso` e `EtiquetaPiso` |
| `src/lib/buscaClientes.ts` | busca de clientes no servidor (`useBuscaClientes`, só do piso escolhido) e os filtros, os mesmos no Painel e na aba Clientes |
| `src/lib/acoes.ts` | liberar, tirar da fila, encerrar sessão |
| `src/lib/tempo.ts` | formato HH:MM:SS e cálculo do tempo restante |
| `src/components/` | `Layout` (menu lateral e cabeçalho), `FichaCliente` (dados, foto, histórico e segurança do cliente), `ModalNovoCliente` (mesmo formato da ficha, com a foto), `QuadroFoto` (foto, botões e o ajuste de enquadramento, usados pelos dois), `AvatarCliente` (miniatura nas listas; fotos em cache em `lib/fotos.ts`), `ModalSaldo`, `SeletorCliente`, `FiltrosBusca`, `ColunasAjustaveis` (colunas do Painel com largura e ordem do operador) e `ui/` (botão, campos, modal, selos de status) |
| `src/pages/` | uma tela por arquivo |

O FastAPI serve os arquivos de `app/static/` e devolve o `index.html` para qualquer outra rota que não seja `/api` ou `/ws`; assim, recarregar a página em `/clientes` funciona.

## Tabelas

| Tabela | Guarda |
|---|---|
| `usuarios` | admin, operadores e clientes (`perfil`), tempo que o cliente ainda tem hoje (`saldo_segundos` + `saldo_dia`), `ativo`, documento, e-mail, data de nascimento, `foto_em` (quando a foto mudou), `piso_id` com `piso_alterado_por` / `piso_alterado_em` (quem trocou por último) |
| `fotos_clientes` | foto de cada cliente (bytes + tipo), à parte para a lista de clientes não carregar imagens |
| `programacao` | cartazes da programação da biblioteca (imagem, título, ordem, ativo); o tempo de cada um fica em `configuracoes.programacao_segundos` |
| `acoes_operadores` | registro do que cada operador fez (`app/registro.py`): quando, operador, ação, cliente, estação e detalhe, com nomes guardados no momento |
| `pisos` | pisos da biblioteca (nome, cor, `padrao`), cadastrados em Configurações → Pisos |
| `grupos_estacao` | mapas/zonas do Mapa, com cor, `piso_id` e `zona_x`/`zona_y`/`zona_largura`/`zona_altura` (posição e tamanho da zona no quadro do piso; vazio = o Mapa arruma sozinho) (obrigatório ao criar; vazio só em mapas antigos, que o painel aponta e contam como o padrão). O `tempo_padrao_segundos` do grupo não é mais usado |
| `estacoes` | PCs cadastrados, status (livre / ocupada / desligada / manutencao), `pos_x`/`pos_y` no mapa, `ativa` |
| `autorizacoes` | fila de espera: um registro por cliente, `usado=false` = está na fila |
| `sessoes` | histórico de uso: início, fim, tempo total e consumido, motivo (`vscyber` = importada do VSCyber por `importar_historico.py`, em estações inativas "... (VS)"/"(VSI)") |
| `apps_permitidos` | programas que podem rodar (processo, caminho, imagem de capa), por grupo ou para todos |
| `configuracoes` | chave/valor: `tempo_padrao_segundos` (tempo de uso por dia), `reiniciar_ao_encerrar` |

## Fluxo de uma sessão

1. Operador clica em **Liberar** (ou arrasta o cliente para uma estação) → a `autorizacao` do cliente é criada ou reativada → evento `fila_atualizada`.
2. Cliente digita login e senha no agente → `login_cliente` pelo WebSocket.
3. Servidor confere: senha certa? está na fila? estação livre? o piso do cliente é o da estação? Se não, responde o motivo. Recusado pelo piso, o cliente continua na fila e pode entrar num PC do piso dele. O **iniciar direto** (arrastar para a estação) faz a mesma checagem do piso.
4. Se sim: tempo = o que o cliente ainda tem hoje (`reservar_tempo`); se acabou, recusa até amanhã. Cria a `sessao`, marca a autorização como usada, estação vira `ocupada`, manda tempo, apps permitidos e `reiniciar_ao_encerrar` ao agente, avisa os painéis (`sessao_iniciada`).
5. O agente mostra o launcher em tela cheia e conta o tempo; o painel conta junto.
6. Fim da sessão, de quatro jeitos:
   - cliente encerra ou o tempo acaba → agente manda `sessao_encerrada`;
   - operador encerra pelo painel → servidor manda `encerrar_sessao` ao agente;
   - o PC reinicia (volta ao login) ou nunca mais reconecta → servidor encerra como `conexao_perdida`, contando até a queda (ver abaixo). Queda do servidor ou da rede **não** encerra: o cliente segue usando;
   - admin entra em manutenção no PC → agente encerra com motivo `manutencao`.
7. Servidor grava o tempo que sobrou em `usuarios.saldo_segundos` (zero se o tempo acabou) e libera a estação. O que sobra vale só até a meia-noite.

## Eventos WebSocket

| Direção | Eventos |
|---|---|
| Servidor → painel | `captura_tela`, `tela_frame`, `estacao_online`, `estacao_offline`, `sessao_iniciada`, `sessao_encerrada`, `fila_atualizada` |
| Servidor → agente | `piso_estacao` (nome e cor do piso, logo depois da resposta ao `estado`; também vai em `login_resultado` e `iniciar_sessao_direta` como `piso`: o agente usa a cor como destaque), `login_resultado`, `encerrar_sessao`, `manutencao_resultado`, `pong`, `programacao_atualizada` (recarregar os cartazes), `mensagem_tela` (com `origem: "horario"` nos avisos de fechamento; na sessão vira notificação no agente), `reiniciar_pc` e `desligar_pc` (o servidor já encerrou a sessão e devolveu o tempo; o agente sai dela e roda `shutdown /r` ou `/s` em 10s), `ativar_manutencao`/`desativar_manutencao`, `capturar_tela` |
| Agente → servidor | `estado` (primeira mensagem ao conectar: a sessão em andamento ou nenhuma), `teste_conexao`, `login_cliente`, `sessao_encerrada` (com `segundos_atras` quando terminou sem conexão), `status_estacao` (manutencao/livre), `validar_manutencao`, `ping`, `captura_tela_resultado` e `tela_frame` (imagem em `dados.imagem`) |

**Comandos em massa**: `POST /api/estacoes/acoes` `{acao, estacoes, texto}` com `acao` = `mensagem`, `encerrar`, `reiniciar`, `desligar` ou `ligar` (Wake-on-LAN) aplica o mesmo comando a cada estação e devolve `resultados` (`"ok"` ou o motivo: offline, sem sessão...), sem parar no primeiro erro. No Painel: as caixinhas do Controle de sessões e a barra `components/AcoesEmMassa.tsx`.

## Perfis

| Perfil | Pode |
|---|---|
| `admin` | tudo: configurações, operadores, apps, relatórios, mapa, excluir |
| `operador` | liberar fila, encerrar sessões, criar e editar clientes, entrar em manutenção num PC |
| `cliente` | só entra pelo agente; o login do painel recusa |

## Atualização do agente (só pela manutenção)

Desde o agente 1.11.0 (6.13) o agente **nunca se atualiza sozinho**. Ao abrir (depois da janela no ar) e ao entrar na manutenção, `checar_atualizacao` só pergunta a versão (`GET /api/agente/versao`, lida de `agente_dist/agente.py`). Havendo versão nova, o botão da faixa da manutenção vira **Atualizar para a versão X**; o operador confirma, o agente baixa `GET /api/agente/download`, troca o próprio arquivo (`os.replace`) e reinicia (`os.execv`) — `_aplicar_atualizacao` recusa fora da manutenção. Agentes até 1.10.x ainda se atualizam sozinhos ao abrir (é assim que chegam à 1.11).

O agente informa a versão no evento `estado`; o servidor guarda em `estacoes.versao_agente` e o painel marca as desatualizadas (ícone na lista do Controle de sessões e a linha **Agente** no painel da estação).

**Para publicar uma nova versão:**
1. Incremente `VERSAO` em `agente/agente.py`
2. Copie o arquivo para `server/agente_dist/agente.py`
3. Commit e push dos dois arquivos
4. No servidor: `git pull` (a versão é lida do arquivo; não precisa reiniciar para isso)
5. Em cada PC: modo manutenção → **Atualizar para a versão X**

Atenção: o servidor de produção lê `agente_dist` direto da pasta do projeto; copiar uma versão para lá já a oferece às estações.

Os endpoints `/api/agente/versao` e `/api/agente/download` não exigem autenticação — o agente ainda não tem token quando checa a versão.

## Decisões não óbvias

- **Sessão do banco por conexão**: o handler `/ws/estacao/{nome}` usa uma sessão do SQLAlchemy durante toda a conexão. Por isso ele chama `db.expire_all()` a cada mensagem do agente; sem isso, o que o painel altera por outras rotas (encerrar sessão, liberar, saldo) fica invisível para ele.
- **Tempo por dia sem tarefa agendada**: `saldo_dia` diz de que dia (Brasília) é o `saldo_segundos`; saldo de outro dia vale a cota cheia (`saldo_do_dia`). A busca filtra e ordena pelo mesmo cálculo em SQL (`saldo_do_dia_sql`). Editar o saldo grava `saldo_dia = hoje`: é assim que o operador dá tempo extra a quem esgotou. Durante a sessão o saldo fica 0 (reservado). "Zerar agora" só limpa `saldo_dia`.
- **Pausa**: retomar soma a pausa ao `tempo_total_segundos` (o agente conta pelo relógio de parede) e acumula `tempo_pausado_segundos`. Ao encerrar, `fechar_tempo_da_sessao` desconta as pausas (inclusive a que estiver em andamento) e grava o tempo concedido e o consumido de verdade. O painel para a contagem em `pausada_em`.
- **Uma autorização por cliente** (`cliente_id` é único): ao liberar de novo, o registro existente é reaproveitado (`usado=False`), nunca recriado.
- **Queda de conexão (servidor, rede ou PC)**: a sessão **não** é encerrada (agente 1.8). O agente segue a sessão até o tempo acabar e reconecta a cada 3s; o servidor marca `sessoes.sem_conexao_desde` e mantém a estação `ocupada` (ícone de sem conexão no Painel). Ao reconectar, a primeira mensagem do agente é `estado` com a `sessao_id` em andamento (ou nenhuma), e o servidor (`_resolver_estado` em `main.py`): retoma a mesma sessão; encerra como `conexao_perdida`, contando até a queda, a sessão aberta de um PC que voltou sem ela (reiniciou); ou responde `encerrar_sessao` se o operador encerrou enquanto o PC estava sem conexão. Fim de sessão sem conexão (cliente saiu, tempo acabou) fica guardado no agente e vai antes do `estado`, com `segundos_atras`; o servidor conta o uso só até lá. PC que nunca volta: o batimento encerra a sessão quando o tempo dela acabaria (`encerrar_sessoes_vencidas`), cobrando até a queda. Agente antigo (sem `estado`, abre com `ping`) e o `teste_conexao` da tela Configurar conexão: o primeiro encerra a sessão órfã como antes, o segundo não mexe em nada. Sem sessão, a estação vira `desligada` 8s depois da queda (`SEGUNDOS_ATE_OFFLINE`), para não piscar no painel.
- **Servidor reiniciado**: a cada minuto o servidor grava `servidor_vivo_em` em `configuracoes`. Ao subir, `marcar_sessoes_sem_conexao` deixa as sessões abertas marcadas sem conexão desde o último batimento (sem batimento, desde o início: PC que nunca voltar não paga nada); as estações com sessão ficam `ocupada` e as outras `desligada`, até os agentes reconectarem. (`servidor_desligado` era o motivo usado até o 4.7, quando reiniciar o servidor derrubava os clientes.)
- **Reconexão**: uma conexão antiga que cai depois de o agente já ter reconectado não derruba a nova (`desconectar_estacao(nome, ws)`).
- **Status vem do banco**: `GET /api/estacoes/` devolve o `status` gravado (e `online` separado). Ao subir, o servidor marca todas as estações como `desligada`, exceto as em manutenção; quando o agente conecta, ela vira `livre`.
- **Modo manutenção sem senha fixa**: o agente pede login e senha de admin/operador e o servidor confere (`validar_manutencao`). Quem o servidor aceitou fica lembrado no `agente.cfg` (`OPERADORES`, últimos 5, hash PBKDF2 com sal) e pode entrar sem conexão, para corrigir um servidor errado em **Configurar conexão** (1.7.1); uma recusa do servidor esquece o operador.
- **Status "manutencao" não sobrevive a uma conexão nova**: o agente sempre abre na tela de login, então o servidor marca `livre` a cada conexão; o agente que reconecta ainda na manutenção manda `status_estacao` logo em seguida. Desconectado, a estação continua aparecendo em manutenção.
- **Banco trocado pelo painel** (`/api/config/banco`, admin): testa a URL (`SELECT 1` e se existe a tabela `usuarios`) e grava `DATABASE_URL` no `server/.env`; vale ao reiniciar. Recusa (409) quando a URL vem do ambiente, que tem prioridade sobre o `.env`. `normalizar_url_banco` (`config.py`) leva `postgres://`/`postgresql://` para o psycopg 3.
- **Agente roda como `cliente`, sem admin**: tarefa agendada no logon, `LogonType Interactive` (SYSTEM ou senha gravada rodam sem área de trabalho). Atalhos do Windows são engolidos por um hook `WH_KEYBOARD_LL` numa thread própria (`BloqueioTeclado`): Win, Ctrl+Esc e Ctrl+Shift+Esc sempre (fora da manutenção), Alt+Tab/Alt+Esc/Alt+F4 só na tela de login; o que ele não alcança (Ctrl+Alt+Del) é desligado por políticas no perfil do `cliente`, que só o admin grava (`politicas_cliente.ps1`).
- **Agente sem proxy na rede interna**: o websockets e o urllib usam o proxy do usuário, que na rede da biblioteca desvia até IPs internos. Servidor em IP privado ou nome sem ponto → conexão direta (`servidor_na_rede_local`).
- **Whitelist por processo e por janela**: a cada 1s o agente encerra processos novos fora da whitelist e também o dono de qualquer janela visível fora dela (processos de antes do login abrem janelas sem criar processo novo). Janelas do Explorador (`CabinetWClass`) e dos apps da Loja/Configurações (`ApplicationFrameWindow`, do `ApplicationFrameHost.exe`) são fechadas sem encerrar o processo (`JANELAS_DE_PROCESSOS_SEGUROS`). Janelas camufladas pelo DWM (UWP suspenso, Iniciar, Widgets) são ignoradas.
- **Migração do SQLite é genérica** (`_migrar_colunas_faltantes`): toda coluna do `models.py` que falte no banco é adicionada com o padrão. Uma coluna sem migração já derrubou `GET /api/estacoes/` (500) e o painel ficou sem estações.
- **`agente.py` já foi reescrito a partir de uma cópia antiga** e perdeu correções (proxy, nome com espaço, estação não cadastrada). `tests/test_agente.py` confere essas regras no código-fonte.
- **Exclusões preservam o histórico**: cliente com sessões e operador que já liberou alguém não podem ser excluídos (409, "desative"); o painel tem o botão "Ativo" para isso. Estação com sessões é desativada em vez de excluída (some do painel); cadastrar de novo o mesmo nome a reativa.
- **Clientes nunca são carregados em massa** (~43k): toda tela busca no servidor (`GET /api/clientes/?busca=...`, até 200). A lista `clientes` do `dados.tsx` fica vazia; `recarregarClientes` só incrementa `versaoClientes`, e as buscas abertas refazem a consulta. A busca divide o termo em palavras e ignora acentos (função `sem_acento` registrada no SQLite em `database.py`).
- **Foto do cliente**: o painel reduz a imagem (480px, JPEG) antes de enviar em data URL; o servidor confere a assinatura do arquivo (não o tipo que o navegador diz) e limita a 2 MB. Como `<img src>` não manda o token, o painel busca a foto com `fetch` e mostra um blob local; `foto_em` vai na URL para não usar a foto antiga.
- **Preferências do operador ficam no navegador** (`localStorage`: `painel.layout`, `painel.ordem`, `painel.grupo`, `painel.busca`, `clientes.busca`), sempre com `try/catch`; sem storage, valem até recarregar.
- **WebSocket do painel exige login**: `/ws/painel?token=...` só aceita admin ou operador (os eventos trazem nomes de clientes).
- **Mapa mostra estações sem grupo** numa aba "Sem grupo"; no painel lateral o admin troca o grupo da estação.
- **SECRET_KEY nunca fixa no código** (`config.resolver_secret_key`): vale a do ambiente/`.env` se tiver 32+ caracteres e não for de exemplo (senão o servidor não sobe); sem ela, usa `server/.secret_key`, gerada na primeira subida. Trocar a chave desloga todo mundo. Guarde o arquivo junto com o backup do banco.
- **Barra própria na sessão** (agente 1.7.0): a janela do agente é tela cheia sem "sempre por cima" (apps abrem na frente) e a `BarraSessao` (Toplevel sempre por cima) ocupa o retângulo da barra do Windows, que é escondida com `ShowWindow`. O espaço que o Windows reserva para a barra dele continua reservado, então apps maximizados param acima da nossa. A barra do Windows volta no fim da sessão, na manutenção e por `atexit`. Na pausa, a nossa some. Desde o agente 1.9.1 ela é um dock (Início e só os apps abertos) com o bloco de sininho, relógio, tempo, tema e Encerrar à direita; o dock não tem animação e só é redesenhado quando algo muda (redesenhar a cada quadro fazia piscar); fora do desenho a janela é transparente (`-transparentcolor`). As notificações (`Notificacoes`) ficam numa pilha acima do canto direito, que abre em lista com o mouse em cima.
- **Meus arquivos** (agente 9.5): o ícone de pasta do dock (`icone_pasta`, Pillow) é a própria pasta: com o mouse em cima, os arquivos de Downloads do `cliente` saem dela em **leque**, animados, numa janela transparente logo acima do dock (`MeusArquivos`; até 5 cartões, fotos com miniatura, botão +N para os próximos). Cada quadro (~60/s) gira e junta os cartões prontos em cache numa imagem só, trocada com `itemconfig` — nada é apagado e recriado, então não pisca. Tirar o mouse (do ícone e do leque, com 0,2 s de folga) guarda os cartões. Mouse num cartão o levanta; **clicar abre** só documentos e imagens (`EXTENSOES_DOCUMENTOS`), direto no programa associado (`FindExecutableW` + `Popen`, sem o aviso de segurança do `startfile`) e só se ele estiver na whitelist (senão, notificação); o **×** exclui com um segundo clique. O Explorador continua bloqueado. A pasta é esvaziada (`limpar_pasta`, que recusa a pasta do usuário e a raiz) 1,5 s depois de fechar os apps no fim da sessão e no início de cada sessão nova. O `politicas_cliente.ps1` grava no perfil do `cliente` as políticas do Chrome e do Edge `DownloadDirectory` (`${user_home}\Downloads`), `PromptForDownloadLocation=0` e `DownloadRestrictions=1` (bloqueia downloads perigosos): sem elas o cliente salvava em qualquer pasta.
- **Tema do agente sem reconstruir a tela**: `trocar_cores` percorre os widgets e troca cada cor da paleta antiga pela da nova (`PALETAS`, sem cores repetidas dentro de uma paleta). Cores de status (verde, vermelho, laranja) são as mesmas nos dois temas.
- **Agente abre a janela antes de tudo**: a atualização é conferida numa thread depois de a janela estar no ar, e na tela de login o agente fecha qualquer janela que não seja do Windows (o que o cliente abriu na inicialização antes do agente).
- **Admin sem senha fixa**: criado por `python -m app.cli` ou pelas variáveis `ADMIN_LOGIN`/`ADMIN_SENHA`.
- **Mensagens no console só com caracteres latinos**: emoji em `print` derruba o servidor num console Windows (cp1252).
- **Backup no batimento** (`main.py`): a cada minuto, se o backup do dia (data de Brasília) ainda não existe, ele é feito numa thread. Assim o primeiro sai logo depois da meia-noite ou quando o servidor sobe. Nome `cybercafe-AAAA-MM-DD-HHMM.db`: o "Fazer backup agora" do painel não sobrescreve o da madrugada. Gravado como `.tmp` e renomeado, para nunca existir um backup pela metade. Só SQLite; no PostgreSQL, o provedor cuida.
- **Servidor de produção como tarefa do Windows** (`registrar_servidor.ps1`): `MatheCafe-Servidor`, na inicialização, como SYSTEM (servidor não precisa de área de trabalho, ao contrário do agente), reabrindo se cair; libera a porta no firewall. `iniciar_servidor.bat` grava a saída em `server/logs/servidor.log` (sem buffer, sem log de cada requisição).
