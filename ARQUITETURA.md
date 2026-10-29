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
| `routers/` | `auth`, `clientes`, `estacoes` (+ grupos, posição no mapa, fila), `sessoes`, `apps`, `operadores`, `config`, `relatorios` (CSV e históricos por cliente/estação), `agente` (auto-update) |
| `agente_dist/agente.py` | arquivo distribuído para auto-update; versão lida da constante `VERSAO` no topo |
| `static/` | **build** do painel React (gerado por `npm run build`; não editar à mão) |
| `static_antigo/index.html` | painel HTML anterior, em `/antigo` durante a transição |

`server/main.py` só reexporta `app.main:app`, para o start command antigo do Render continuar valendo.

## Painel (`server/frontend/`)

React 19 + Vite + Tailwind 4, no mesmo molde do `central/frontend` do sistema de Banners.

| Arquivo | Papel |
|---|---|
| `src/App.tsx` | rotas: `/login`, `/` (Painel), `/clientes`, `/mapa`, `/historicos`, `/configuracoes` (só admin) |
| `src/lib/api.ts` | chamadas à API com o token; 401 leva de volta ao login |
| `src/lib/dados.tsx` | dados compartilhados entre as telas (estações, fila, sessões, grupos), WebSocket `/ws/painel` com reconexão e o relógio das contagens |
| `src/lib/buscaClientes.ts` | busca de clientes no servidor (`useBuscaClientes`) e os filtros, os mesmos no Painel e na aba Clientes |
| `src/lib/acoes.ts` | liberar, tirar da fila, encerrar sessão |
| `src/lib/tempo.ts` | formato HH:MM:SS e cálculo do tempo restante |
| `src/components/` | `Layout` (menu lateral e cabeçalho), `ModalSaldo`, `FiltrosBusca`, `ColunasAjustaveis` (colunas do Painel com largura e ordem do operador) e `ui/` (botão, campos, modal, selos de status) |
| `src/pages/` | uma tela por arquivo |

O FastAPI serve os arquivos de `app/static/` e devolve o `index.html` para qualquer outra rota que não seja `/api` ou `/ws`; assim, recarregar a página em `/clientes` funciona.

## Tabelas

| Tabela | Guarda |
|---|---|
| `usuarios` | admin, operadores e clientes (`perfil`), tempo que o cliente ainda tem hoje (`saldo_segundos` + `saldo_dia`), `ativo` |
| `grupos_estacao` | grupos de PCs (abas do Mapa), com cor (o `tempo_padrao_segundos` do grupo não é mais usado) |
| `estacoes` | PCs cadastrados, status (livre / ocupada / desligada / manutencao), `pos_x`/`pos_y` no mapa, `ativa` |
| `autorizacoes` | fila de espera: um registro por cliente, `usado=false` = está na fila |
| `sessoes` | histórico de uso: início, fim, tempo total e consumido, motivo |
| `apps_permitidos` | programas que podem rodar (processo, caminho, imagem de capa), por grupo ou para todos |
| `configuracoes` | chave/valor: `tempo_padrao_segundos` (tempo de uso por dia), `reiniciar_ao_encerrar` |

## Fluxo de uma sessão

1. Operador clica em **Liberar** (ou arrasta o cliente para uma estação) → a `autorizacao` do cliente é criada ou reativada → evento `fila_atualizada`.
2. Cliente digita login e senha no agente → `login_cliente` pelo WebSocket.
3. Servidor confere: senha certa? está na fila? estação livre? Se não, responde o motivo.
4. Se sim: tempo = o que o cliente ainda tem hoje (`reservar_tempo`); se acabou, recusa até amanhã. Cria a `sessao`, marca a autorização como usada, estação vira `ocupada`, manda tempo, apps permitidos e `reiniciar_ao_encerrar` ao agente, avisa os painéis (`sessao_iniciada`).
5. O agente mostra o launcher em tela cheia e conta o tempo; o painel conta junto.
6. Fim da sessão, de quatro jeitos:
   - cliente encerra ou o tempo acaba → agente manda `sessao_encerrada`;
   - operador encerra pelo painel → servidor manda `encerrar_sessao` ao agente;
   - conexão do PC cai → servidor encerra como `conexao_perdida` (ver abaixo);
   - admin entra em manutenção no PC → agente encerra com motivo `manutencao`.
7. Servidor grava o tempo que sobrou em `usuarios.saldo_segundos` (zero se o tempo acabou) e libera a estação. O que sobra vale só até a meia-noite.

## Eventos WebSocket

| Direção | Eventos |
|---|---|
| Servidor → painel | `estacao_online`, `estacao_offline`, `sessao_iniciada`, `sessao_encerrada`, `fila_atualizada` |
| Servidor → agente | `login_resultado`, `encerrar_sessao`, `manutencao_resultado`, `pong` |
| Agente → servidor | `login_cliente`, `sessao_encerrada`, `status_estacao` (manutencao/livre), `validar_manutencao`, `ping` |

## Perfis

| Perfil | Pode |
|---|---|
| `admin` | tudo: configurações, operadores, apps, relatórios, mapa, excluir |
| `operador` | liberar fila, encerrar sessões, criar e editar clientes, entrar em manutenção num PC |
| `cliente` | só entra pelo agente; o login do painel recusa |

## Auto-update do agente

O agente (`agente/agente.py`) verifica atualizações **antes de abrir a janela Tkinter**, na função `verificar_update(servidor_http)`:

1. `GET /api/agente/versao` → retorna `{"versao": "x.y.z"}` (lido de `agente_dist/agente.py`)
2. Se `versao_servidor > VERSAO` local: mostra diálogo informativo, baixa `GET /api/agente/download`
3. Salva sobre si mesmo com `os.replace()` e reinicia com `os.execv()`

**Para publicar uma nova versão:**
1. Incremente `VERSAO` em `agente/agente.py`
2. Copie o arquivo para `server/agente_dist/agente.py`
3. Commit e push dos dois arquivos
4. Reinicie o servidor (para o endpoint ler o novo arquivo)

A primeira instalação em cada PC é manual; a partir da v1.2.0 todas as atualizações são automáticas.

Os endpoints `/api/agente/versao` e `/api/agente/download` não exigem autenticação — o agente ainda não tem token quando checa a versão.

## Decisões não óbvias

- **Sessão do banco por conexão**: o handler `/ws/estacao/{nome}` usa uma sessão do SQLAlchemy durante toda a conexão. Por isso ele chama `db.expire_all()` a cada mensagem do agente; sem isso, o que o painel altera por outras rotas (encerrar sessão, liberar, saldo) fica invisível para ele.
- **Tempo por dia sem tarefa agendada**: `saldo_dia` diz de que dia (Brasília) é o `saldo_segundos`; saldo de outro dia vale a cota cheia (`saldo_do_dia`). A busca filtra e ordena pelo mesmo cálculo em SQL (`saldo_do_dia_sql`). Editar o saldo grava `saldo_dia = hoje`: é assim que o operador dá tempo extra a quem esgotou. Durante a sessão o saldo fica 0 (reservado). "Zerar agora" só limpa `saldo_dia`.
- **Uma autorização por cliente** (`cliente_id` é único): ao liberar de novo, o registro existente é reaproveitado (`usado=False`), nunca recriado.
- **Queda de conexão do PC**: a estação só é marcada `desligada` 8s depois (`SEGUNDOS_ATE_OFFLINE` em `main.py`), para não piscar no painel. O agente volta à tela de login assim que perde a conexão; por isso o servidor encerra a sessão que ficou aberta (`conexao_perdida`), contando o tempo até a queda e devolvendo o resto como saldo — quando o PC reconecta ou quando os 8s passam.
- **Reconexão**: uma conexão antiga que cai depois de o agente já ter reconectado não derruba a nova (`desconectar_estacao(nome, ws)`).
- **Status vem do banco**: `GET /api/estacoes/` devolve o `status` gravado (e `online` separado). Ao subir, o servidor marca todas as estações como `desligada`, exceto as em manutenção.
- **Modo manutenção sem senha fixa**: o agente pede login e senha de admin/operador e o servidor confere (`validar_manutencao`). Sem conexão com o servidor, não há como entrar em manutenção.
- **Agente roda como `cliente`, sem admin**: tarefa agendada no logon, `LogonType Interactive` (SYSTEM ou senha gravada rodam sem área de trabalho). Atalhos do Windows são engolidos por um hook `WH_KEYBOARD_LL` numa thread própria (`BloqueioTeclado`): Win, Ctrl+Esc e Ctrl+Shift+Esc sempre (fora da manutenção), Alt+Tab/Alt+Esc/Alt+F4 só na tela de login; o que ele não alcança (Ctrl+Alt+Del) é desligado por políticas no perfil do `cliente`, que só o admin grava (`politicas_cliente.ps1`).
- **Agente sem proxy na rede interna**: o websockets e o urllib usam o proxy do usuário, que na rede da biblioteca desvia até IPs internos. Servidor em IP privado ou nome sem ponto → conexão direta (`servidor_na_rede_local`).
- **Whitelist por processo e por janela**: a cada 1s o agente encerra processos novos fora da whitelist e também o dono de qualquer janela visível fora dela (processos de antes do login abrem janelas sem criar processo novo). Janelas do Explorador (`CabinetWClass`) e dos apps da Loja/Configurações (`ApplicationFrameWindow`, do `ApplicationFrameHost.exe`) são fechadas sem encerrar o processo (`JANELAS_DE_PROCESSOS_SEGUROS`). Janelas camufladas pelo DWM (UWP suspenso, Iniciar, Widgets) são ignoradas.
- **Migração do SQLite é genérica** (`_migrar_colunas_faltantes`): toda coluna do `models.py` que falte no banco é adicionada com o padrão. Uma coluna sem migração já derrubou `GET /api/estacoes/` (500) e o painel ficou sem estações.
- **`agente.py` já foi reescrito a partir de uma cópia antiga** e perdeu correções (proxy, nome com espaço, estação não cadastrada). `tests/test_agente.py` confere essas regras no código-fonte.
- **Exclusões preservam o histórico**: cliente com sessões e operador que já liberou alguém não podem ser excluídos (409, "desative"); o painel tem o botão "Ativo" para isso. Estação com sessões é desativada em vez de excluída (some do painel); cadastrar de novo o mesmo nome a reativa.
- **Clientes nunca são carregados em massa** (~43k): toda tela busca no servidor (`GET /api/clientes/?busca=...`, até 200). A lista `clientes` do `dados.tsx` fica vazia; `recarregarClientes` só incrementa `versaoClientes`, e as buscas abertas refazem a consulta. A busca divide o termo em palavras e ignora acentos (função `sem_acento` registrada no SQLite em `database.py`).
- **Preferências do operador ficam no navegador** (`localStorage`: `painel.layout`, `painel.ordem`, `painel.grupo`, `painel.busca`, `clientes.busca`), sempre com `try/catch`; sem storage, valem até recarregar.
- **WebSocket do painel exige login**: `/ws/painel?token=...` só aceita admin ou operador (os eventos trazem nomes de clientes).
- **Mapa mostra estações sem grupo** numa aba "Sem grupo"; no painel lateral o admin troca o grupo da estação.
- **Admin sem senha fixa**: criado por `python -m app.cli` ou pelas variáveis `ADMIN_LOGIN`/`ADMIN_SENHA`.
- **Mensagens no console só com caracteres latinos**: emoji em `print` derruba o servidor num console Windows (cp1252).
