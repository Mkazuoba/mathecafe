# Changelog

## 2026-10-30 — Agente não diminui na sessão (agente 1.6.6)

- Na sessão, o botão de maximizar/restaurar e a borda de redimensionar saem da janela junto com o minimizar (na 1.6.5 dava para restaurar e diminuir o agente). Se a janela sair de maximizada por outro caminho (arrastar a barra de título), volta sozinha. No modo manutenção, tudo volta ao normal.

## 2026-10-30 — SECRET_KEY segura e estação fechada desde a inicialização (agente 1.6.5)

- **SECRET_KEY**: o código trazia uma chave padrão pública (`TROQUE_ESTA_CHAVE_EM_PRODUCAO`); um servidor sem `.env` assinava os logins com ela e qualquer um podia forjar um login de admin. Agora, sem chave configurada, o servidor gera uma aleatória na primeira subida e guarda em `server/.secret_key` (fora do git), reaproveitando-a nas próximas. Chave de exemplo ou com menos de 32 caracteres: o servidor não sobe e diz o que fazer. O servidor da biblioteca já tem a própria chave no `.env` e continua igual (ninguém é deslogado).
- **Apps abertos antes do agente na inicialização do Windows**: a tarefa esperava 5s depois do logon e o agente só abria a janela depois de consultar a atualização (até 5s); o que o cliente abrisse nesse intervalo continuava rodando atrás da tela de login.
  - A tela do agente abre primeiro; a atualização é conferida e baixada em segundo plano (com sessão em andamento, fica para a próxima abertura).
  - Na tela de login o agente fecha, a cada segundo, qualquer janela de programa que não seja do Windows e terminais (`cmd`, PowerShell...). A primeira conferência é aos 0,5s, não mais aos 3s.
  - A tarefa agendada não espera mais 5s (`registrar_tarefa.ps1`): **vale só depois de rodar o `instalar.bat` de novo na estação**; o resto chega pela atualização automática.

## 2026-10-30 — Revisão: sessão presa depois de reiniciar o servidor (Ciclo 6, tarefa 6.3)

- **Sessões abertas ficavam presas quando o servidor reiniciava**: as estações viravam "desligada", mas a sessão continuava aberta até aquele PC reconectar; se ele não voltasse, o cliente ficava "em uso" e não podia ser liberado. Agora, ao subir, o servidor encerra essas sessões (motivo "Servidor desligado") e devolve ao cliente o tempo que sobrou.
- **Batimento**: a cada minuto o servidor grava em `configuracoes` (`servidor_vivo_em`) que está no ar. É esse horário que diz quando ele caiu — e ali a sessão terminou de fato, porque o agente volta ao login quando perde o servidor. Sem batimento gravado (só na primeira subida com esta versão), nada é cobrado.

## 2026-10-29 — Ampliar e salvar a tela da estação (Ciclo 6)

- **Ampliar**: na tela ao vivo, o botão "Ampliar" (ou clique duplo na imagem) abre a tela da estação ocupando a janela inteira; lá, "Tela cheia" usa o monitor todo de quem está vendo. Esc volta, sem fechar o painel da estação nem parar a transmissão. A Captura rápida abre no mesmo visor.
- **Salvar imagem**: na tela ao vivo e no visor, baixa a imagem do momento para o computador do operador, com o nome da estação e a hora (`AD-10 2026-10-29 14-30-05.jpg`).

## 2026-10-29 — Captura de tela e tela ao vivo voltam a funcionar (agente 1.6.4)

- **Captura rápida e "Ver ao vivo" chegavam em branco ao painel**: o agente manda a imagem dentro de `dados` (`{"evento": "tela_frame", "dados": {"imagem": ...}}`), mas o servidor a procurava no nível de cima da mensagem e repassava uma imagem vazia. Corrigido em `main.py`; o teste `test_captura_e_tela_ao_vivo_chegam_ao_painel` cobre os dois.
- **Agente 1.6.4**: a transmissão ao vivo não escreve mais no log da janela pela thread dela (o Tkinter só aceita a thread principal e podia travar; o log também enchia a cada 1,2s). Ela espera cada quadro ser enviado antes do próximo, para não acumular quadros numa rede lenta.
- O servidor não imprime mais uma linha por quadro no console.

## 2026-10-29 — Ficha do cliente com foto (Ciclo 5)

- **Ficha do cliente** (`components/FichaCliente.tsx`) no lugar dos botões Histórico, Editar e Excluir: abre clicando na linha da aba Clientes, no botão "Ficha" ou na engrenagem do cliente no Painel. Três abas:
  - **Geral**: foto, nome, login, documento (CPF/RG), data de nascimento (com a idade), observações, tempo de hoje (com tempo extra) e data de cadastro.
  - **Histórico**: as últimas 50 sessões, com o motivo de encerramento em português (antes aparecia o código, como `tempo_esgotado`), e o atalho para a tela Históricos.
  - **Segurança**: trocar a senha (digitada duas vezes), ativar/desativar e excluir (admin).
- **Foto**: enviada por arquivo (JPG, PNG ou WebP). O painel reduz a imagem para 480px antes de enviar; o servidor confere que é imagem de verdade e guarda até 2 MB na tabela `fotos_clientes`, separada para a lista de clientes não carregar fotos. A foto sai junto quando o cliente é excluído.
- **Novo cliente** com documento e data de nascimento, igual na aba Clientes e no Painel (`components/ModalNovoCliente.tsx`); ao criar, a ficha já abre para pôr a foto.
- Novas colunas `usuarios.documento`, `data_nascimento` e `foto_em` (migração automática). API: `PUT`/`GET`/`DELETE /api/clientes/{id}/foto`.

## 2026-10-29 — Revisão: pausa não conta como uso (Ciclo 6, tarefa 6.2)

- **Encerrar uma sessão pausada cobrava a pausa**: a pausa só era descontada ao retomar. Exemplo: entra às 14:00, pausa às 14:30, o operador encerra às 15:30 — o cliente perdia 1h30 em vez de 30 min. Agora todo encerramento (operador, PC, queda de conexão) usa a mesma conta, `fechar_tempo_da_sessao` em `tempo_diario.py`, que desconta as pausas retomadas e a que está em andamento.
- O tempo consumido gravado não inclui mais as pausas (antes inflava o "uso de hoje" e os Históricos), e `tempo_total_segundos` passa a guardar o tempo concedido, sem a pausa somada.
- **A contagem do painel não para mais de descer durante a pausa**: `GET /api/sessoes/ativas` informa `pausada_em` e a contagem (Painel e Mapa) fica parada nesse momento.
- O agente não muda: continua somando a pausa ao total ao retomar.

## 2026-10-29 — Históricos por cliente e por estação (Ciclo 5)

- **Nova tela Históricos** (menu lateral, admin e operador), com duas abas:
  - **Por cliente**: quais estações ele já usou — quantas vezes, tempo total, primeira e última vez.
  - **Por estação**: quais clientes já passaram por ela, com os mesmos números e quantos clientes diferentes.
- Período (De/Até, em dias de Brasília), ordenação por coluna e exportação em CSV (ponto e vírgula, abre direto no Excel). Clicar numa linha abre o outro lado: do cliente para a estação e vice-versa. O endereço guarda a escolha, então dá para mandar o link.
- Atalhos: "Ver quais estações ele já usou" no histórico do cliente (aba Clientes) e "Ver quais clientes já passaram por aqui" no histórico da estação (Painel).
- API: `GET /api/relatorios/cliente/{id}` e `GET /api/relatorios/estacao/{nome}`, com `de` e `ate`.

## 2026-10-29 — Revisão: filtro de cliente do Relatório CSV (Ciclo 6, tarefa 6.1)

- **O filtro de cliente do Relatório CSV estava sempre vazio**: usava a lista de clientes do contexto, que não é mais carregada. Agora é uma busca (`components/SeletorCliente.tsx`): digita, escolhe, e o "x" tira o filtro.
- A lista `clientes` saiu do `lib/dados.tsx`, para nenhuma tela voltar a usá-la; `tests/test_painel.py` confere isso no código-fonte.

## 2026-10-29 — Tempo de uso por dia (Ciclo 5)

- **Não havia limite diário de verdade**: quando o tempo acabava, o saldo 0 significava "dar o tempo padrão de novo", e o cliente podia ser liberado outra vez no mesmo dia. O painel até mostrava "Limite diário atingido", mas o servidor ignorava. O "reset" que existia usava a data em UTC (o dia virava às 21h) e só valia no login pelo PC.
- **Regra nova** (`app/tempo_diario.py`): cada cliente tem por dia o tempo de Configurações → Comportamento, somando todas as sessões. Quando acaba, a fila, o login no PC e o "Iniciar direto" recusam até amanhã; o operador dá tempo extra editando o saldo. O que sobra não passa para o dia seguinte. Zera à meia-noite de Brasília.
- Nova coluna `usuarios.saldo_dia` (migração automática): saldo de outro dia vale o tempo cheio, sem tarefa agendada. **Na primeira subida, todos os clientes começam com o tempo cheio.**
- **Configurações → Comportamento → Zerar agora** (admin): faz na hora o que a meia-noite faria — útil para testar.
- Sair para manutenção devolve o tempo que sobrou (antes zerava, o que agora bloquearia o cliente o dia todo).
- O tempo padrão por grupo deixou de ser usado (a cota é a global) e saiu da tela Grupos.
- Painel: "Tempo de hoje esgotado" no cartão do cliente; a aba Clientes chama a coluna de "Tempo de hoje".

## 2026-10-29 — Aba Clientes de volta, busca refinada e colunas ajustáveis (Ciclo 5)

- **A aba Clientes sempre dizia "Nenhum cliente encontrado"**: ela filtrava a lista que o painel deixou de carregar quando a busca passou para o servidor (são ~43k clientes). Agora busca no servidor, lista até 200 pela ordem escolhida e avisa quando é preciso refinar.
- **Busca refinada, igual no Painel e na aba Clientes** (`lib/buscaClientes.ts`, `components/FiltrosBusca.tsx`): buscar em nome e login, só nome ou só login; "contém as palavras", "começa com" ou "exatamente igual"; com ou sem saldo. Na aba Clientes também status e ordenação, inclusive clicando no cabeçalho da tabela. Os filtros ficam guardados no navegador.
- **Palavras em qualquer ordem e sem acento**: "jose silva" acha "Maria José da Silva" (antes não achava nada). No SQLite a comparação usa a função `sem_acento`, registrada em `database.py`.
- `GET /api/clientes/` aceita `campo`, `modo`, `status`, `saldo`, `ordem`, `desc` e `tudo` (lista sem termo de busca).
- **Colunas do Painel ajustáveis** (`components/ColunasAjustaveis.tsx`): arrastar a divisa muda a largura (clique duplo volta ao padrão), as setas no cabeçalho trocam as colunas de lugar e "Restaurar layout" desfaz tudo. Guardado no navegador.
- As buscas de clientes abertas se atualizam sozinhas quando um cliente é editado ou uma sessão termina (`versaoClientes` em `lib/dados.tsx`).

## 2026-10-29 — Controle de sessões no Painel (Ciclo 5)

- A coluna de estações do Painel virou a tabela **Controle de sessões**, como no VSCyber: Status, Estação, Login (login - nome) e Tempo restante, com ordenação ao clicar no cabeçalho (clique de novo inverte), filtro por grupo e contagem por status no rodapé. Ordem natural nos nomes (AD-2 antes de AD-10).
- O grupo e a ordenação escolhidos ficam guardados no navegador.
- Clicar na linha abre a estação; arrastar um cliente para uma linha livre continua liberando.

## 2026-10-29 — Agente não minimiza na sessão (agente 1.6.3)

- O botão de minimizar some da barra de título na sessão; se a janela for minimizada de outro jeito (clique no ícone da barra de tarefas), volta sozinha. No modo manutenção minimiza normalmente.

## 2026-10-29 — Bloqueios continuam na sessão (agente 1.6.2)

- **Depois do login os atalhos voltavam**: o hook de teclado liberava tudo na sessão. Agora Win (Iniciar, Win+R, Win+E, Win+D...), Ctrl+Esc e Ctrl+Shift+Esc ficam bloqueados também na sessão; só Alt+Tab e Alt+F4 continuam, para alternar e fechar os apps liberados. O Esc sozinho segue funcionando dentro dos apps.
- **Configurações, Calculadora e apps da Loja escapavam da whitelist**: abrem dentro do `ApplicationFrameHost.exe`, que é processo seguro. A janela (`ApplicationFrameWindow`) agora é fechada, como já acontecia com o Explorador.

## 2026-10-28 — Painel sem estações e whitelist furada (agente 1.6.1)

- **Nenhuma estação aparecia no painel**: `GET /api/estacoes/` dava 500 com o `cybercafe.db` existente, porque a coluna `grupos_estacao.cor` (Ciclo 5) nunca ganhou migração — o changelog do Ciclo 5 dizia que sim. A migração do SQLite agora é genérica: adiciona qualquer coluna do `models.py` que falte no banco, com o valor padrão. **Reinicie o servidor** para aplicar.
- **Apps fora da whitelist abriam na sessão**: processos que já rodavam antes do login (Edge em segundo plano, por exemplo) nunca eram conferidos, e o Explorador de Arquivos é o `explorer.exe`, que não pode ser encerrado. Agora o agente também confere o dono de cada janela visível: fecha o programa se estiver fora da whitelist e fecha só a janela do Explorador. Terminais e afins (`cmd`, `regedit`...) caem mesmo se já existiam. A conferência passa de 3s para 1s.

## 2026-10-28 — Agente 1.6.0: conexão na rede da biblioteca e bloqueios (Ciclo 3, tarefas 3.3 e 3.4)

- **Estação não aparecia no painel**: rodando como `cliente`, o agente pegava o proxy da rede e não chegava ao servidor interno. Volta a correção de 29/09 (perdida quando o `agente.py` foi reescrito em 02/10): conexão direta para IP privado ou nome sem ponto, agora também no auto-update e nas imagens.
- Voltam também: nome de estação com espaço/acento, aviso de "estação não cadastrada" na tela de login, só fica online depois do `pong` e erros fatais em `agente_erro.log`.
- **Esc e fechar a janela** só no modo manutenção.
- **Atalhos do Windows**: hook de teclado (`BloqueioTeclado`) engole Win, Ctrl+Esc, Alt+Tab, Alt+Esc e Alt+F4 na tela de login e Ctrl+Shift+Esc sempre (fora da manutenção). O `taskmgr.exe` é fechado também na tela de login.
- **`politicas_cliente.ps1`** (novo, etapa 6 do instalador): desliga Gerenciador de Tarefas, Bloquear e Alterar senha no perfil do `cliente`, criando o perfil se preciso.
- Removido o aviso "rodando sem privilégios de admin" (agora é o esperado).
- `tests/test_agente.py`: 5 testes que conferem essas regras no código-fonte do agente e que o `agente_dist` é igual ao `agente.py`.

## 2026-10-28 — Agente abre sozinho no logon (Ciclo 3, tarefa 3.3)

- **Causa**: a tarefa agendada rodava como SYSTEM (sessão 0, sem área de trabalho), então a janela do agente nunca aparecia. Além disso, o `instalar.bat` deixou de criar o `venv` (o agente morria sem `websockets`/`psutil`) e usava o Python e a pasta do perfil do admin, que o `cliente` não lê.
- **`instalar.bat`**: copia o agente para `C:\MatheCafe`, cria o `venv` lá e dá ao `cliente` escrita na pasta (cfg e auto-update). Python instalado só para o admin (o padrão do python.org, inclusive o novo install manager `pythoncore-3.14`) é copiado para `C:\MatheCafe\python`; o da Microsoft Store é recusado. Numa reinstalação, fecha o agente que estiver rodando da pasta. Senha do `cliente` não expira.
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
