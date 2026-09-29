# Arquitetura do MatheCafé

> Como o sistema funciona **hoje**. O que ainda falta está no [roadmap](https://claude.ai/artifact/DzDETNJFr5jxzD6FCdKCEC).
> Última revisão: 2026-09-29.

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
| `websocket_manager.py` | guarda quem está conectado (painéis e estações) e envia mensagens |
| `cli.py` | `python -m app.cli` cria um administrador |
| `routers/` | `auth`, `clientes`, `estacoes` (+ grupos, posição no mapa, fila), `sessoes`, `apps`, `operadores`, `config`, `relatorios` |
| `static/index.html` | painel em HTML puro: Painel, Clientes, Mapa, Configurações |

## Tabelas

| Tabela | Guarda |
|---|---|
| `usuarios` | admin, operadores e clientes (`perfil`), saldo de tempo dos clientes, `ativo` |
| `grupos_estacao` | grupos de PCs (abas do Mapa), com tempo padrão de sessão |
| `estacoes` | PCs cadastrados, status (livre / ocupada / desligada / manutencao), `pos_x`/`pos_y` no mapa, `ativa` |
| `autorizacoes` | fila de espera: um registro por cliente, `usado=false` = está na fila |
| `sessoes` | histórico de uso: início, fim, tempo total e consumido, motivo |
| `apps_permitidos` | programas que podem rodar (processo, caminho, imagem de capa), por grupo ou para todos |
| `configuracoes` | chave/valor: `tempo_padrao_segundos`, `reiniciar_ao_encerrar` |

## Fluxo de uma sessão

1. Operador clica em **Liberar** (ou arrasta o cliente para uma estação) → a `autorizacao` do cliente é criada ou reativada → evento `fila_atualizada`.
2. Cliente digita login e senha no agente → `login_cliente` pelo WebSocket.
3. Servidor confere: senha certa? está na fila? estação livre? Se não, responde o motivo.
4. Se sim: tempo = saldo do cliente, ou o tempo padrão das configurações. Cria a `sessao`, marca a autorização como usada, estação vira `ocupada`, manda tempo, apps permitidos e `reiniciar_ao_encerrar` ao agente, avisa os painéis (`sessao_iniciada`).
5. O agente mostra o launcher em tela cheia e conta o tempo; o painel conta junto.
6. Fim da sessão, de quatro jeitos:
   - cliente encerra ou o tempo acaba → agente manda `sessao_encerrada`;
   - operador encerra pelo painel → servidor manda `encerrar_sessao` ao agente;
   - conexão do PC cai → servidor encerra como `conexao_perdida` (ver abaixo);
   - admin entra em manutenção no PC → agente encerra com motivo `manutencao`.
7. Servidor grava o tempo que sobrou em `usuarios.saldo_segundos` (zero se o tempo acabou) e libera a estação.

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

## Decisões não óbvias

- **Sessão do banco por conexão**: o handler `/ws/estacao/{nome}` usa uma sessão do SQLAlchemy durante toda a conexão. Por isso ele chama `db.expire_all()` a cada mensagem do agente; sem isso, o que o painel altera por outras rotas (encerrar sessão, liberar, saldo) fica invisível para ele.
- **Uma autorização por cliente** (`cliente_id` é único): ao liberar de novo, o registro existente é reaproveitado (`usado=False`), nunca recriado.
- **Queda de conexão do PC**: a estação só é marcada `desligada` 8s depois (`SEGUNDOS_ATE_OFFLINE` em `main.py`), para não piscar no painel. O agente volta à tela de login assim que perde a conexão; por isso o servidor encerra a sessão que ficou aberta (`conexao_perdida`), contando o tempo até a queda e devolvendo o resto como saldo — quando o PC reconecta ou quando os 8s passam.
- **Reconexão**: uma conexão antiga que cai depois de o agente já ter reconectado não derruba a nova (`desconectar_estacao(nome, ws)`).
- **Status vem do banco**: `GET /api/estacoes/` devolve o `status` gravado (e `online` separado). Ao subir, o servidor marca todas as estações como `desligada`, exceto as em manutenção.
- **Modo manutenção sem senha fixa**: o agente pede login e senha de admin/operador e o servidor confere (`validar_manutencao`). Sem conexão com o servidor, não há como entrar em manutenção.
- **Exclusões preservam o histórico**: cliente com sessões e operador que já liberou alguém não podem ser excluídos (409, "desative"); o painel tem o botão "Ativo" para isso. Estação com sessões é desativada em vez de excluída (some do painel); cadastrar de novo o mesmo nome a reativa.
- **Admin sem senha fixa**: criado por `python -m app.cli` ou pelas variáveis `ADMIN_LOGIN`/`ADMIN_SENHA`.
- **Mensagens no console só com caracteres latinos**: emoji em `print` derruba o servidor num console Windows (cp1252).
