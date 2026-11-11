# Changelog

## 2026-11-11 — Área do Cliente, terceira versão (9.13)

- **Visual da imagem enviada pelo Matheus**, no agente (Tkinter):
  - **Menu mais limpo**: só a marca, Início, Meus Apps (com a quantidade) e **Configurações** no rodapé, que abre preferências da sessão (tema e tamanho do texto dos apps). O cliente saiu do menu.
  - **Card da sessão com o cliente**: avatar, nome, estação, login e Online no topo; embaixo o tempo restante, a hora de início, o limite e a barra.
  - **Avisos com tipo e horário**: Alerta (âmbar), Evento (violeta) ou Informativo (azul), com ícone e título na cor.
  - **Banner** mais alto, com selo, título, **descrição e créditos** do cartaz, botão "Abrir Inscrição / Programação" e setas para trocar de cartaz.
  - **Apps**: "Aplicativos da Estação" com a quantidade liberada, busca que acha também pela categoria, pílulas arredondadas, ícone da categoria no card e a situação **Pronto / Aberto**.
  - **Dock**: à esquerda o botão M e uma aba para cada app aberto; à direita notificações, relógio e tempo juntos, tema e Encerrar.
  - Fonte **Inter** quando estiver instalada no PC; senão continua a Segoe UI.
- **Painel** (Programação e avisos): tipo e horário em cada aviso; descrição e créditos em cada cartaz.
- O login do PC agora recebe o login do cliente (para o card da sessão).
- Sem Histórico no menu, por decisão do Matheus.

## 2026-11-11 — Trocar o piso pela manutenção (agente 1.22.0)

- Configurar conexão (Ctrl+Shift+M, modo manutenção) ganhou o campo **Piso**, com a lista do servidor e o piso atual do PC já escolhido. Trocar para outro piso pede confirmação e faz o PC entrar lá como computador novo (mesma regra do instalar.bat: ID novo); no mesmo piso, só grava o piso.

## 2026-11-11 — Corrigido: reinstalar em outro piso

- Reinstalado escolhendo o Infantil, o PC continuava no Adulto: o instalador mantém o ID do PC e o servidor reconhece pelo ID antes de olhar o piso.
- Agora o instalador pergunta ao servidor que estação aquele ID é (`GET /api/agente/estacao?id=`). Se o piso escolhido for outro, descarta o ID antigo: o PC entra no piso escolhido como computador novo. Mesmo piso: mantém o ID (continua a mesma estação). A estação antiga fica no mapa do outro piso para excluir.

## 2026-11-11 — Corrigido: Ctrl+Alt+Del liberado numa máquina nova

- Numa instalação nova o passo [6/6] falhava (o perfil do `cliente` ainda não existia) e o Ctrl+Alt+Del deixava **alterar a senha** e abrir o **Gerenciador de Tarefas**.
- O instalador agora cria a tarefa **MatheCafe-Politicas** (`registrar_politicas.ps1`), que roda como SYSTEM a cada logon do `cliente` e grava as políticas (sem Gerenciador de Tarefas, Bloquear e Alterar senha; downloads presos). Sair e Trocar usuário continuam (decisão do Matheus: Sair é a saída de emergência).
- O desinstalador remove essa tarefa. **PCs já instalados: rode o `instalar.bat` novo** (mantém o ID e a configuração) e entre como `cliente` de novo.

## 2026-11-11 — Tema claro creme e botão Novo cliente

- **Tema claro** em tom creme/off-white (paleta Stone, quente) no lugar do branco: fundo, cartões, bordas e textos um pouco mais escuros para ler melhor.
- **Novo cliente**: no Painel virou um botão principal (roxo, com ícone) ao lado da busca de clientes; em Clientes ganhou o ícone.

## 2026-11-11 — Desinstalador completo

- `agente/desinstalar.bat` agora deixa o PC como antes do `instalar.bat`: fecha o agente e a sessão do `cliente`, remove a tarefa e o autologin, desinstala o Python do agente (só o registrado em `C:\MatheCafe\python`), apaga o usuário `cliente` com o perfil (e as políticas dele) e a pasta `C:\MatheCafe`. Pede para digitar SIM; rodando de dentro de `C:\MatheCafe`, continua de uma cópia na pasta temporária.
- A estação continua no painel: para reinstalar com o mesmo nome, exclua no Mapa antes (ou Substitui a X).

## 2026-11-11 — Restaurar um backup pelo painel (10.2)

- Configurações → Servidor → Backup do banco: **Restaurar** em cada backup e **Restaurar de um arquivo...** (um banco guardado fora do servidor). O servidor confere o arquivo, reinicia e, ao subir, guarda o banco atual (`antes-da-restauracao-...db`) e põe o backup no lugar; o painel recarrega sozinho.
- **Desfazer**: os bancos de antes de cada restauração (e os enviados) ficam numa lista própria, com Restaurar e Baixar; não são apagados sozinhos.
- Com computadores em uso, o painel avisa e pede confirmação. Arquivo que não é banco do MatheCafé ou está corrompido é recusado. A restauração entra no registro de ações ("Restaurou um backup do banco").
- Testado com uma cópia supervisionada do servidor (porta 8020): restaurar, desfazer e restaurar de um arquivo, cada um reiniciando em ~2 s.

## 2026-11-11 — Programação e avisos fora de Configurações

- **Programação** e **Avisos** saíram de Configurações e viraram uma tela própria, **Programação e avisos**, no menu lateral logo abaixo do Mapa (com as duas abas; só admin).
- Avisos "não funcionavam" na biblioteca porque o servidor ainda não tinha sido reiniciado depois da 9.11 (`/api/avisos` respondia 404). Conferido no servidor de teste: publicar um aviso chega à lista dos PCs.

## 2026-11-11 — Seletor de piso só onde ele vale

- O seletor de piso do topo aparece só no **Painel**, em **Clientes** e no **Mapa**, as telas que mostram um piso por vez. Em Configurações e Históricos ele saiu.
- **Históricos → Por estação** ganhou o próprio filtro **Piso** (começa no último piso usado); **Por cliente** busca clientes de todos os pisos. **Uso** já tinha o filtro de piso.
- Corrigido: o histórico de um cliente juntava numa linha só estações de mesmo nome nos dois pisos (AD-01 do Adulto e do Infantil). Agora cada uma tem a sua linha, com o piso.

## 2026-11-11 — Acabamento da Área do Cliente (9.12; agente 1.21.0)

- **Cards dos apps no padrão novo**: capa em cima (escurecida), selo da categoria no canto, ícone sobre a capa e embaixo o nome, uma **descrição curta** e um só botão **Abrir** (azul). Com o mouse em cima, a borda puxa para a cor da categoria.
- **Descrição do app**: campo novo em Configurações → Apps permitidos → editar app ("Descrição curta", até 120 letras). Sem descrição, o card mostra o nome da categoria.
- **Cores das categorias** como no prompt: violeta, azul, **verde esmeralda**, âmbar e rosa (categorias novas; as já criadas mantêm a cor escolhida).
- **Banner** com 250 px de altura, degradê escuro da esquerda e o botão "Ver no navegador / Inscrição" em pílula azul.
- **Dock** em barra inteira na base da tela: sininho discreto com contador azul, relógio e tempo restante juntos, tema e **Encerrar sessão em rosa suave** (no lugar do vermelho vivo).
- Textos sem branco puro e rótulos pequenos em caixa alta, nos dois temas.

## 2026-11-11 — Mapas separados por piso, parte B: o instalador escolhe o piso (6.18; agente 1.20.0)

- **Instalador**: depois de testar o servidor, pergunta **em qual piso** fica o computador (a lista vem do servidor: Adulto, Infantil...) e grava `PISO=` no `agente.cfg`. Sem resposta do servidor, segue sem piso.
- **Agente 1.20.0**: conecta com o piso escolhido (`?piso=`).
- **Servidor**: o PC instalado com o nome de uma estação que já está no mapa daquele piso (e ainda sem computador) **entra direto nela**, aprovado. Nome que o piso não tem vai para **Novas estações**, já com o piso, e com o nome pedido mesmo que exista no outro piso. `GET /api/agente/pisos` (sem login) lista os pisos para o instalador.
- **Novas estações**: mostra o piso de cada PC; a zona sugerida é a do piso dele (as outras vêm depois, com o piso no nome) e "Substitui a X" mostra o piso de cada estação.
- Agentes até a 1.19 continuam como antes (pelo nome).

## 2026-11-11 — Área do Cliente no PC (9.11)

- **Tela da sessão redesenhada** (prompt enviado pelo Matheus, feito no agente em Tkinter): cores Zinc (escuro e claro) e três colunas sobre o dock.
  - **Menu à esquerda**, que recolhe: Início (banner da Programação + apps) e Meus Apps (só os apps). No rodapé, o cliente, a estação e se está online.
  - **No centro**: pesquisa, pílulas das categorias (cada uma na sua cor) e os cards dos apps com capa, logo, selo da categoria e um botão **Abrir**. Com o mouse em cima, o card sobe e brilha na cor da categoria.
  - **À direita**: o tempo restante com a barra do quanto já foi usado, e os **Avisos da biblioteca**.
  - Saiu a faixa de cima da sessão (nome, tempo e Encerrar): o tempo está no widget e no dock; o Encerrar, no dock.
- **Cor por categoria**: Configurações → Apps permitidos → Categorias tem a cor de cada uma. Categoria nova já nasce com uma cor.
- **Avisos da biblioteca**: Configurações → **Avisos** (novo). Publicar, editar, ligar/desligar, ordenar e apagar; os PCs atualizam na hora.
- **Link no cartaz**: em Configurações → Programação cada cartaz pode ter um link. O banner do PC mostra **Ver no navegador / Inscrição**, que abre no navegador (que precisa estar liberado na estação).
- Sem "pedir +30 min" e sem Histórico no menu, por decisão do Matheus.
- Vale a partir do agente com essas mudanças (ainda não liberado). O servidor e o painel já funcionam com os agentes atuais (eles ignoram a cor, o link e os avisos).

## 2026-11-11 — Mapas separados por piso, parte A: o mesmo nome no Adulto e no Infantil (6.18)

- O nome da estação passou a ser único **só dentro do piso**: dá para ter AD-01 no Adulto e AD-01 no Infantil, cada uma com o seu histórico. No mesmo piso continua proibido (criar, várias de uma vez, renomear, aprovar, mudar de zona ou mudar a zona de piso).
- As conexões dos agentes e os comandos do painel (mensagem, reiniciar, desligar, manutenção, liberar direto, captura, ao vivo, atualizar, ações em massa) passaram a usar o **id** da estação. Chamadas antigas só com o nome continuam valendo quando o nome é único; com dois iguais, respondem "informe qual".
- Históricos → Por estação usa o piso escolhido no topo.
- PC novo (agente 1.14+) com um nome que existe nos dois pisos espera em **Novas estações** (use "Substitui a X"). Se só um dos dois ainda não tem PC, ele assume esse.
- **Banco**: ao subir, o servidor refaz a tabela de estações sem o nome único (mesmos dados e ids). Antes disso grava uma cópia do banco ao lado dele (`cybercafe.antes-6.18.db`). Conferido numa cópia do banco real: 116 estações e as 283 mil sessões ligadas a elas.
- Os agentes atuais seguem funcionando. A parte B (agente 1.20 e instalador perguntando o piso) vem a seguir.

## 2026-11-11 — Histórico ao vivo; Mapa com seleção, duplicar e várias estações

- **Históricos → Por cliente**: o cliente aparece assim que loga, não só depois de sair: "Usando agora · AD-10" no topo e "agora" na linha da estação (o tempo da sessão entra no total quando ela acaba). A tela atualiza sozinha quando uma sessão abre ou fecha, e mostra a foto do cliente. Por estação também conta a sessão em andamento.
- **Configurações**: saíram "Relatórios" e "Histórico de uso", que repetiam Históricos. O CSV de todas as sessões continua no botão **Exportar CSV** da tela Clientes (baixa direto).
- **Mapa (Modo configuração)**: Ctrl+clique (ou Shift) seleciona várias zonas; arrastar uma selecionada move todas juntas (o grupo para inteiro na beirada) e puxar o canto deixa todas com o mesmo formato. Com a seleção: **Duplicar** e **Excluir** juntas. Cada zona ganhou o botão Duplicar.
- **Duplicar zona**: copia nome (com "(cópia)"), cor, tamanho e as estações nas mesmas posições, com os próximos números livres (AD-77 → AD-78...). A cópia vai para baixo de tudo, já selecionada.
- **Excluir zona**: leva as estações dela (quem tem histórico só sai do mapa); com alguém usando um PC da zona, não exclui nada.
- **Várias estações de uma vez**: no + da zona, "Várias de uma vez" (começo do nome, a partir do número, quantas, dígitos), com a prévia dos nomes e a sugestão a partir dos nomes da zona. Se algum nome já existe, não cria nenhuma.
- Registro de ações: "Cadastrou estações", "Duplicou zona do mapa", "Excluiu zona do mapa".

## 2026-11-10 — Visual novo do painel (estilo shadcn/ui)

- **Menu lateral** de 260px que recolhe para só os ícones, com o bloco MatheCafé · SP Leituras no topo, os grupos Operação e Gestão e quem está logado (com Sair) embaixo. Históricos e Configurações abrem **subitens** (abas e seções), recuados, com linha vertical e seta que gira; com o menu aberto, a lista própria de Configurações some.
- **Cabeçalho** com o botão do menu, o caminho (MatheCafé › tela), a escolha de piso e a busca.
- **Busca global (Ctrl+K)**: telas, estações e clientes do piso; a estação abre a janela dela no Painel e o cliente, a ficha.
- **Cores Zinc** (escuro e claro), colunas do Painel em cartões arredondados e **selos de status** em pílula: Livre verde, Ocupada âmbar, Desligada cinza; Manutenção passou a azul.
- **Tipografia**: Geist em tudo e Geist Mono nos horários, com antialiased; títulos de grupo e cabeçalhos de tabela em 11px caixa alta; sem negrito e sem branco ou preto puro no texto.
- As fontes vêm do Google Fonts; sem internet, o painel cai para Inter/Segoe UI.

## 2026-11-10 — Nome trocado no PC pede aprovação (agente 1.18.0)

- Corrigido: trocar o nome da estação no próprio PC (Ctrl+Shift+M → Configurar conexão) não fazia nada e não dava erro (o servidor reconhece o PC pelo identificador e devolvia o nome antigo).
- Agora vira um pedido em **Mapa → Novas estações**: "AD-01 quer se chamar AD-05", com **Aceitar** (renomeia e avisa o PC na hora) e **Recusar**. Até aceitar, a estação segue com o nome atual. O botão Novas estações conta os pedidos junto com os PCs novos.
- PC ainda não aprovado: trocar o nome no PC só muda o nome com que ele aparece para aprovar.
- Agente 1.18.0: ao salvar um nome novo em Configurar conexão, avisa que ele vai para aprovação no painel.
- Registro de ações: aceitar entra como "Renomeou estação" (pedido do PC); recusar, "Recusou o nome pedido pelo PC".

## 2026-11-10 — Log do PC vai para o painel; nome do PC grande no login (9.10; agente 1.19.0)

- **O log de comunicação saiu da tela do cliente.** Agora fica no servidor: no painel, clique na estação → aba **Log** (últimas 300 linhas, chegando ao vivo; botão Atualizar). As linhas de quando o PC estava sem conexão chegam ao reconectar, com a hora em que aconteceram. O log fica só na memória do servidor: reiniciar o servidor apaga.
- **Sem a barra de cima no PC.** O nome do computador fica bem grande acima do formulário de login, com um computador **verde** (online), **vermelho** (offline) ou laranja (conectando). O botão de tema e a versão foram para o canto de baixo.
- O nome grande e o fim da barra valem a partir do agente 1.19.0. Os agentes anteriores já mandam o log, então a aba Log funciona com eles assim que o servidor for atualizado; só a hora é a do servidor.

## 2026-11-10 — Instalador instala o Python e as dependências sozinho

- Máquina nova não precisa de nada antes, só de internet: o `instalar.bat` baixa o Python 3.13.17 do python.org e instala um **Python só do agente** em `C:\MatheCafe\python` (com Tkinter; sem atalho, sem PATH e sem mexer em outro Python da máquina). Depois instala as dependências do `requirements.txt` (websockets, psutil, Pillow) pelo pip.
- O download e o pip usam o **proxy do Windows** (o mesmo do navegador); antes o pip ignorava o proxy.
- Numa reinstalação o Python do agente é reaproveitado. Se a mesma versão já existia na máquina, ela é copiada para `C:\MatheCafe\python`.
- Saiu a exigência de Python instalado antes (e a recusa do Python da Microsoft Store, que não é mais usado).

## 2026-11-10 — Instalador sugere e testa o endereço do servidor

- O `instalar.bat` sugere o endereço do servidor (Enter = a 1ª linha de `agente/servidor.txt`, hoje `10.26.31.77:8000`) e **testa a conexão na hora**. Se o servidor não responde, avisa e pede o endereço de novo, ou continua com **C**. Antes, um endereço errado terminava em "Instalação concluída" e o PC só nunca aparecia no painel.
- Corrigido: o exemplo do instalador apontava para 10.26.31.99 (o servidor é o .77).
- Aceita o endereço com `http://`, `https://`, `ws://` e barra no fim.

## 2026-11-10 — Reiniciar o servidor pelo Windows, sem administrador

- **`server\reiniciar_servidor.bat`**: clique duplo no computador do servidor reinicia o MatheCafé (aplica atualizações do código) sem reiniciar o computador, sem PowerShell de administrador e sem entrar no painel. Ele deixa um pedido (`reiniciar.pedido`) que o servidor da tarefa atende em até 2 s; o `iniciar_servidor.bat` sobe de novo e o `.bat` avisa quando voltou.
- Só é atendido por um servidor de 10/11 em diante: na primeira vez, reinicie pelo botão do painel (Configurações → Servidor → Reiniciar servidor).

## 2026-11-10 — Login do PC em duas metades, com os cartazes (9.9; agente 1.17.0)

- **Tela de login do cliente redesenhada** (modelo enviado pelo Matheus): formulário à esquerda ("Entre na sua conta", Login, Senha com o **olho** para mostrar/esconder, Entrar) e, à direita, os **cartazes da Programação** inteiros sobre eles mesmos desfocados, com o título digitando letra a letra entre aspas. Os cartazes passam sozinhos (fade).
- Sem cartaz, a metade direita fica num degradê da cor do piso com "Bem-vindo(a) à biblioteca! Faça login para começar."
- No lugar de "criar conta"/Google: "Não tem cadastro? Fale com um funcionário da biblioteca."
- Os cartazes agora são carregados ao conectar e sempre que mudam no painel (antes só durante a sessão).
- Corrigido: a roda do mouse parava de rolar a grade a partir da segunda sessão.

## 2026-11-09 — Substituir computador, atualizar pelo painel e correções (agente 1.16.0)

- **Computador formatado ou trocado**: em Mapa → Novas estações, **É o computador de → Substitui a AD-3** (sugerido quando o nome bate). O PC novo vira a AD-3 com o mesmo nome, zona, lugar no mapa e histórico; recusado se a AD-3 ainda está ligada.
- **Atualizar o agente pelo painel**: botão **Atualizar agora** na linha Agente do painel da estação e **Atualizar agente** nas ações em massa. Só sem cliente usando; vale a partir do agente 1.16 (as estações em 1.15 ou antes atualizam uma vez pela manutenção).
- Corrigido: digitar a data à mão nos relatórios. Cada dígito do ano (0002, 0020...) virava uma consulta de séculos e travava a tela; agora o campo só consulta com a data completa.
- Corrigido: relatórios aceitavam data no futuro (o campo vai até hoje) e o cadastro aceitava nascimento no futuro (o servidor também recusa, e antes de 1900).
- Corrigido: RG/documento aceitava qualquer caractere. Agora só números e X (pontos e traços saem; x vira X). Documentos antigos com pontuação só mudam quando editados.
- Corrigido: dava para excluir no Mapa uma estação em uso (o botão some e o servidor recusa) e a exclusão não aparecia em Ações dos operadores (agora aparecem excluir, substituir e atualizar agente).
- Corrigido: mensagem longa do operador era cortada. A janela no PC cresce com o texto (rola se passar de 60% da tela) e, durante a sessão, clicar na notificação abre a mensagem inteira.

## 2026-11-09 — Estação nova aparece sozinha no painel (6.4; agente 1.14.0)

- **Instalar o agente já liga o PC ao servidor**: o `instalar.bat` só pergunta o nome da estação (Enter = o nome do Windows), o endereço do servidor e a senha do `cliente`. Saíram o login de admin e o cadastro pela API (que não funcionava: o login era mandado no formato errado).
- O PC aparece no painel em **Mapa → Novas estações** (botão laranja com a contagem, só para admin): confirme ou troque o nome, escolha a zona e **Aprovar**; ou **Recusar** (o PC fica bloqueado). Até aprovar, ninguém faz login nele e a tela de login avisa que ele aguarda aprovação.
- **Renomear estação pelo Mapa** (lápis no cartão da estação): o agente 1.14 recebe o nome novo na hora, sem reconectar, e grava no `agente.cfg`.
- O agente gera um identificador na primeira vez (`ID=` no `agente.cfg`), e é por ele que o servidor reconhece o PC: renomear não perde a conexão, e um segundo PC instalado com o mesmo nome vira outra estação (`-2`). Reinstalar mantém o identificador.
- Estações já cadastradas continuam como estão: ao receberem a 1.14, adotam o identificador do agente.
- Registro de ações: aprovar, recusar e renomear estação.


## 2026-11-09 — Tela de apps do agente em estilo loja, com categorias (9.8; agente 1.15.0)

- **Banner largo da Programação** no topo da tela de apps (antes era uma coluna estreita à direita): o cartaz aparece inteiro à direita sobre ele mesmo ampliado e desfocado, com o título grande à esquerda; troca com fade e bolinhas para escolher o cartaz.
- **Pesquisa** pelo nome do app (sem diferenciar acento nem maiúscula) e **categorias** à esquerda: Todos, as categorias cadastradas e Outros (apps sem categoria). A grade de capas fica embaixo, com o número de apps.
- **Categorias cadastráveis**: Configurações → Apps permitidos → botão **Categorias** (criar, renomear, mudar a ordem, excluir); cada app escolhe a sua na edição. A tela de apps também filtra por categoria e o cartão mostra a dela.
- Servidor: tabela `categorias_apps`, `apps_permitidos.categoria_id`, rotas `/api/categorias/`; a whitelist mandada ao agente leva `categoria` e `categoria_ordem`.

## 2026-11-09 — Apps por piso e capa do app no dock (agente 1.13.0)

- **Cada piso tem os seus apps**: a tela Apps permitidos segue o piso do topo (abas "Apps do Adulto" / "Apps do Infantil") e o interruptor do cartão liga o app **só naquele piso**. O cartão mostra em que outros pisos o app também está ligado; "N de M apps ligados no piso X". Ações em massa: ligar/desligar no piso, excluir. App novo entra ligado no piso escolhido.
- O vínculo por mapa saiu: a estação recebe os apps ligados no piso dela (login no PC e liberar direto). Tabela `apps_pisos`; `PUT /api/apps/{id}/pisos/{piso_id}`.
- Conversão automática (uma vez, ao subir): app de todos os mapas → ligado em todos os pisos; de um mapa → no piso desse mapa; desligado → em nenhum.
- **Dock do agente com a capa do app**: o ícone de cada app aberto é a imagem cadastrada (o quadrado do centro, de cantos arredondados); sem imagem, a letra, como antes.

## 2026-11-09 — Apps permitidos em grade de cartões

- **Configurações → Apps permitidos** virou uma grade de cartões em pé: a capa cobre o cartão, o nome embaixo e o mapa em cima. O **interruptor** no canto liga e desliga o app na hora; desligado, o cartão fica apagado.
- O primeiro cartão é **Adicionar app**; clicar num cartão abre a edição (com prévia do cartão e Excluir).
- Filtros: busca pelo nome, Todos/Ligados/Desligados, fichas por mapa (e "Valem em todos"), Limpar e ordem (nome ou mais novos). Paginação com 23 por página.
- **Ações em massa**: o interruptor deixa marcar vários cartões e ligar, desligar, mudar de mapa ou excluir de uma vez.
- Corrigido: mudar o mapa na edição de um app não era salvo (o servidor ignorava o campo).

## 2026-11-09 — Reiniciar o servidor pelo painel

- **Configurações → Servidor → Reiniciar servidor** (admin): reinicia sem precisar de PowerShell de administrador do Windows (o servidor da biblioteca roda como SYSTEM e só um administrador elevado mexe na tarefa). O painel mostra "Reiniciando..." e avisa quando o servidor voltou.
- `iniciar_servidor.bat` agora sobe o servidor de novo sempre que ele termina (3 s depois) e marca `MATHECAFE_SUPERVISIONADO=1`; o botão só aparece quando o servidor foi aberto por ele. `LOG` muda o arquivo de log (para testar outra cópia).
- **Vale depois de um reinício do computador** (o `.bat` em execução é o antigo).

## 2026-11-09 — Meus arquivos no Explorador de verdade e notificações com movimento (9.5, 9.4; agente 1.12.0)

- O leque de arquivos saiu (não funcionou bem). O ícone de pasta do dock abre o **Explorador do Windows** na pasta Downloads do cliente.
- O cliente não sai da pasta: se tentar ir para C:, Este Computador ou outra pasta (pela barra de endereço, painel lateral ou "voltar"), a janela volta sozinha para Downloads em até meio segundo. Feito com um PowerShell escondido que o próprio agente sobe na sessão (COM do Windows, nada a instalar) e que termina com ela.
- Programas baixados continuam sendo fechados pela lista de apps permitidos; a pasta continua sendo esvaziada entre clientes.
- **Notificações com movimento**: a pilha aparece com fade (e um leve deslize vindo da direita) e some com fade deslizando para a direita; uma notificação nova entra deslizando da direita e a fechada (×) sai deslizando para a direita antes de sumir.

## 2026-11-09 — Agente só se atualiza pela manutenção (6.13; agente 1.11.0)

- **O agente não se atualiza mais sozinho** (antes reiniciava ao abrir, até com cliente esperando na tela de login). Ele só confere se há versão nova; na faixa do modo manutenção o botão mostra **Atualizar para a versão X** (ou "Agente em dia" / "Verificar atualização"), e o operador confirma a hora.
- **Painel mostra a versão do agente** de cada estação: linha **Agente** no painel da estação e um ícone de aviso na lista do Controle de sessões para as desatualizadas.
- Servidor guarda a versão informada no evento `estado` (`estacoes.versao_agente`); a versão distribuída é relida só quando o arquivo muda.

## 2026-11-06 — Meus arquivos no próprio ícone do dock, em leque animado (tarefa 9.5; agente 1.10.2)

- O **ícone do dock virou a pasta** (na 1.10.1 abria uma pasta grande separada em cima dele). Com o mouse em cima, os arquivos saem dela em **leque animado** logo acima do dock (até 5 cartões, fotos com miniatura, +N para os próximos); tirar o mouse guarda os cartões.
- Mouse num cartão o levanta e mostra o ×; clicar abre direto no programa liberado; × exclui com confirmação. Avisos (tipo que não abre, programa não liberado) chegam como notificação.
- Animação a ~60 quadros/s sem pisca: cada quadro troca uma imagem só, com os cartões prontos em cache.

## 2026-11-06 — Meus arquivos como pasta e downloads presos (tarefa 9.5; agente 1.10.1)

- **Visual de pasta**: os arquivos baixados saem de uma pasta em cartões inclinados (fotos com miniatura; documentos com tipo e tamanho), aberta em cima do ícone do dock. Mouse em cima levanta o cartão; clicar abre; × exclui com confirmação; ⋯ mostra os próximos 4. **Clicar fora ou Esc fecha** (antes a janela ficava por cima de tudo).
- **Abre direto no programa liberado**, sem o aviso de segurança do Windows que aparecia antes.
- **Downloads presos na pasta Downloads** (`politicas_cliente.ps1`): Chrome e Edge do `cliente` não perguntam mais onde salvar e bloqueiam downloads perigosos. Nas estações já instaladas, rodar o script novo como administrador (ou o `instalar.bat`).

## 2026-11-06 — Meus arquivos: downloads da sessão (Ciclo 9, tarefa 9.5; agente 1.10.0)

- **Ícone "Meus arquivos" no dock** (ao lado do Início): lista o que o cliente baixou na pasta Downloads, com tamanho e hora, e se atualiza quando um download termina. O Explorador de Arquivos continua bloqueado.
- **Abrir** só documentos e imagens (PDF, Word, Excel, PowerPoint, txt, fotos) e só se o programa que abre o tipo estiver na whitelist; senão avisa para pedir ajuda ao atendimento. Imprimir é pelo próprio programa. Executáveis e scripts só aparecem para **Excluir** (com confirmação).
- **Downloads esvaziada** no fim de cada sessão (depois de fechar os apps) e no início da próxima (caso o PC tenha reiniciado no meio), para o próximo cliente não ver o que o anterior baixou.

## 2026-11-06 — Dock sem pisca e sininho junto da hora (tarefa 9.4; agente 1.9.2)

- **Dock parou de piscar**: o efeito de crescer redesenhava o dock inteiro (e recolocava o bloco da hora) a cada 16 ms com o mouse em cima. Agora não há animação: o mouse só contorna o ícone e mostra o nome, e o dock é redesenhado apenas quando abre/fecha um app, muda o foco ou o tema.
- **Sininho pequeno ao lado da hora**, fora do dock, com o número das não lidas. O dock ficou com o Início e os apps abertos.

## 2026-11-06 — Dock menor e notificações em pilha (tarefa 9.4; agente 1.9.1)

- **Dock na faixa da barra do Windows** (48 px): mostra só o Início, **os apps abertos** (aparecem ao abrir, somem ao fechar; ponto no app em uso) e o sininho. Na 1.9.0 ele era alto, mostrava todos os apps liberados e cobria parte do navegador.
- **Notificações em pilha**, como no modelo enviado: a mais nova na frente e até duas espiando atrás; com o mouse em cima a pilha abre em lista (e marca como lidas), ao sair volta. Cabeçalho com "N novas" e Limpar tudo; cartão com ícone colorido, origem, tempo, ponto de não lida, título e mensagem numa linha; × dispensa. A nova aparece por 7 s e fica no sininho.

## 2026-11-06 — Visual do agente: dock, notificações e cor do piso (Ciclo 9, tarefa 9.4; agente 1.9.0)

- **Dock** no lugar da barra de tarefas própria: centralizado embaixo, com fundo arredondado, Início, um ícone por app liberado (cada um com sua cor e a inicial) e o sininho. Os ícones crescem com o mouse por perto (os vizinhos menos), o nome aparece em cima e os apps abertos têm uma bolinha; clicar traz o app aberto para a frente ou o abre. Fora do desenho a janela é transparente e o clique passa.
- **Bloco separado no canto** com relógio (hora atual), tempo restante, tema e Encerrar sessão.
- **Notificações** no canto inferior direito: a mensagem do operador (antes uma janela no meio da tela), os avisos de fechamento da biblioteca, o tempo acabando (antes uma caixa do Windows) e a conexão perdida/de volta. A nova aparece sozinha por alguns segundos (com o mouse em cima não some) e fica no **sininho do dock**, com o número das não lidas; o sininho abre a lista (× dispensa, Limpar tudo). Ao fim da sessão a lista é apagada.
- **Cor do piso**: o servidor manda o piso da estação ao agente (`piso_estacao`) e a cor dele (Infantil rosa, Adulto roxo, ou a cadastrada em Pisos) vira o destaque da tela, também no tema claro.

## 2026-11-06 — Mapa: zonas em qualquer lugar, colunas e zoom

- **Zonas vão para qualquer lugar**: no modo configuração o quadro tem folga à direita e embaixo, a tela rola sozinha quando o arrasto chega na beirada e a zona se move pegando em qualquer ponto vazio dela (não só no cabeçalho). Antes ela ficava presa à área visível.
- **Colunas × linhas**: ao criar ou editar a zona, escolher o tamanho em estações (ex.: 1 coluna × 6 para uma fileira junto à parede, 2 ou 3 colunas para uma bancada). A zona pode ter uma coluna só; ao estreitá-la, as estações que ficariam de fora vão para a primeira vaga livre. A zona nova entra embaixo das outras, já com o tamanho escolhido.
- **Zoom** no topo do Mapa (−, +, Ajustar para ver o mapa inteiro), lembrado em cada navegador.

## 2026-11-06 — Mapa novo: zonas, cores de estado e iniciar sessão no mapa (Ciclo 7, tarefa 7.3)

- **Todas as zonas (salas) do piso lado a lado numa tela só**, cada uma um retângulo na cor dela, com o nome e quantas estão ocupadas. Estações em quadrados numerados **na cor do estado** (livre verde, ocupada laranja com o tempo restante, desligada apagada, manutenção amarela; ícone de sem conexão). Legenda com a contagem no topo.
- **Cartão da estação** ao clicar: cliente, tempo restante e total, Encerrar sessão, Mensagem, Reiniciar, Desligar (ou Ligar, se desligada). Na estação livre: **busca de cliente e Iniciar**, que começa a sessão no PC sem o cliente digitar a senha.
- **Modo configuração** (admin): **+ Zona** (no piso do topo), mover a zona pelo cabeçalho e mudar o tamanho pelo canto, editar nome e cor, **+** estação na zona, excluir estação e arrastar estações, também para outra zona.
- **Quadrantes**: cada zona é uma grade com uma estação por quadrante (as vagas aparecem tracejadas no modo configuração). Soltar em cima de outra estação troca as duas de lugar; posições antigas são encaixadas no quadrante mais próximo, sem nunca ficar uma em cima da outra. Ao soltar, a zona inteira é gravada.
- API: `zona` (x, y, largura, altura) nos grupos (`PUT /api/estacoes/grupos/{id}`).

## 2026-11-06 — Histórico do VSCyber guardado, mas escondido

- A importação do histórico ainda vai ser ajustada: as sessões importadas (motivo `vscyber`) ficam no banco, mas saem de todos os históricos e relatórios (ficha do cliente, painel da estação, Históricos por cliente/estação/uso e o CSV) até a chave `historico_vscyber_visivel` ser ligada. Regra num lugar só: `app/importados.py`.

## 2026-11-06 — Histórico de uso do VSCyber (Ciclo 8, tarefa 8.5)

- **`server/importar_historico.py`**: traz os usos do VSCyber desde 2022 (adulto e infantil) como sessões encerradas, que aparecem no histórico de cada cliente e em Históricos → Uso. Sem `--aplicar` só simula; com `--aplicar` faz backup e grava; rodar de novo não duplica.
- As estações antigas entram com o nome do VSCyber como estações inativas ("BSP-87 (VS)", "BSP-87 (VSI)"), num mapa inativo do piso de cada banco. Ficam de fora usos sem fim, com mais de 16 h, de clientes inexistentes e dos logins para conferir.
- Relatório de uso mais rápido com muito histórico (lê só os campos usados): 5 anos em menos de 3 segundos.

## 2026-11-06 — Relatório de uso na tela (Ciclo 8, tarefa 8.2)

- **Históricos → Uso** (só admin), por período (7 dias, 30 dias, este mês ou datas à escolha; padrão: últimos 30 dias) e piso:
  - números do período: sessões, tempo de uso, clientes diferentes e média por sessão;
  - **horas de uso por dia** (barras; passando o mouse, as sessões e os clientes do dia; ou **Ver tabela**);
  - **horários de pico**: dia da semana × hora, mais escuro onde houve mais uso;
  - **estações mais usadas**, em ranking.
- Só sessões já encerradas. O uso de cada sessão é distribuído pelas horas em que aconteceu.
- API `GET /api/relatorios/uso?de=&ate=&piso_id=`.

## 2026-11-06 — Registro das ações dos operadores (Ciclo 8, tarefa 8.1)

- **Históricos → Ações dos operadores** (só admin): quem fez o quê, quando, com qual cliente e em qual estação, do mais recente para o mais antigo. Filtros por operador, ação, cliente (nome ou login), estação e período; **Exportar CSV** com os mesmos filtros. Os filtros ficam no endereço.
- Registradas: cadastrar/editar/excluir/ativar/desativar cliente, trocar a senha e o piso, mudar o tempo de hoje (tempo extra), liberar, tirar da fila, liberar direto, encerrar/pausar/retomar a sessão e dar mais tempo nela, mensagem, reiniciar, desligar, ligar e manutenção (cada estação de uma ação em massa), zerar o tempo do dia, horário de funcionamento, configurações e operadores.
- Tabela `acoes_operadores`; API `GET /api/relatorios/acoes`, `/acoes/tipos` e `/acoes.csv`.

## 2026-11-06 — Horário de funcionamento (Ciclo 8, tarefa 8.4)

- **Configurações → Horário**: liga/desliga e, para cada dia da semana, se funciona e o horário de abrir e fechar (Brasília). Vários dias de uma vez: atalhos Seg a sex / Fim de semana / Todos e "Nos marcados: das ... às ... Aplicar" ou "Fechado". Começa desligado.
- **Ligado**: 10 e 5 minutos antes de fechar os clientes recebem um aviso na tela ("A biblioteca fecha às 20:00. Sua sessão termina em 10 minutos..."); no horário as sessões são encerradas (motivo `horario`) e o tempo que sobrou volta para cada cliente; fora do horário o login no PC e o liberar direto são recusados ("A biblioteca está fechada agora."). A fila continua funcionando.
- Não precisa de agente novo: o aviso usa a mensagem na tela que já existe.

## 2026-11-06 — Cadastro do cliente: e-mail e foto no cadastro novo (Ciclo 8, tarefa 8.3)

- **Cadastro novo no mesmo formato da ficha**: foto à esquerda (Enviar/Trocar/Remover, com prévia) e os dados à direita. A foto vai junto ao criar; antes só dava para pôr depois, na ficha.
- **E-mail** no cadastro novo e na ficha (opcional; guardado em minúsculas, formato conferido, vazio apaga).
- **Ajustar a foto**: ao escolher (ou em **Ajustar**, numa foto já salva) abre um quadro para arrastar a foto e aproximar; ela sai quadrada, 480x480.
- **Miniatura da foto no avatar** dos clientes na coluna Clientes do Painel (sem foto, as iniciais). Cada foto é baixada uma vez e reaproveitada (`lib/fotos.ts`).
- O cadastro novo não tem mais o campo "Tempo de hoje": o tempo do dia vem de Configurações → Comportamento (e o tempo extra continua na ficha).

## 2026-11-06 — Desligar pelo painel e ações em massa (Ciclo 7, tarefas 7.1 e 7.2; agente 1.8.1)

- **Desligar o PC pelo painel**: no painel da estação, **Desligar** ao lado de Reiniciar. O servidor encerra a sessão (o tempo que sobrou volta para o cliente) e o agente desliga em 10s (`shutdown /s`). **Reiniciar** passou a encerrar a sessão do mesmo jeito.
- **Ações em massa**: o Controle de sessões ganhou caixinhas (uma por estação e uma para todas as do grupo/piso na tela). Com estações marcadas aparece a barra **Mensagem**, **Encerrar sessões**, **Ligar**, **Reiniciar** e **Desligar**; as que pedem confirmação dizem quantas estações. O aviso conta quantas deram certo e diz as que não foram e por quê (ex.: "AC-02 (Estação offline)").
- API: `POST /api/estacoes/{nome}/desligar` e `POST /api/estacoes/acoes`.
- Agente 1.8.1 (auto-update): entende `desligar_pc`. Agente antigo ignora o comando (a sessão é encerrada mesmo assim).

## 2026-11-06 — Cliente não cai junto com o servidor (agente 1.8.0) e total de clientes por piso

- **Queda do servidor ou da rede não derruba mais o cliente**: antes o agente voltava ao login e o servidor, ao subir, encerrava todas as sessões. Agora o cliente segue usando até o tempo acabar, o agente reconecta sozinho e o servidor retoma a mesma sessão (o tempo continua contado pelo relógio do servidor). A estação aparece ocupada, com o ícone de sem conexão.
- Se o cliente sair (ou o tempo acabar) enquanto o servidor está fora, o agente guarda e avisa ao reconectar, e o servidor desconta só até a hora em que terminou.
- Só encerra como "conexão perdida" se o PC reiniciar (volta ao login) ou nunca mais voltar — aí quando o tempo dele acabaria —, cobrando até a queda e devolvendo o resto.
- Se o operador encerrar a sessão enquanto o PC estava sem conexão, o PC volta ao login ao reconectar.
- **Total de clientes em cada aba de piso** da tela Clientes (ex.: "Clientes do Infantil 8.349"), para conferir a importação.
- Agente 1.8.0 (auto-update). Agentes antigos continuam funcionando como antes (caem junto com o servidor).

## 2026-11-05 — Pisos cadastráveis, mapas por piso e painel separado por piso (Ciclo 4, tarefa 4.7b)

- **Pisos cadastrados no sistema** (Configurações → **Pisos**, só admin): nome e cor de cada piso, um deles o padrão. Adulto (padrão) e Infantil são criados sozinhos; criar outro (ex.: Juvenil) é pela tela. Piso com clientes ou mapas, ou o padrão, não se exclui.
- **Todo mapa pertence a um piso** (Configurações → **Mapas**, antes "Grupos"): obrigatório ao criar. Mapas antigos sem piso aparecem em vermelho com um aviso até alguém escolher (o mapa "Infantil" criado antes ficava no Adulto sem ninguém perceber).
- **Seletor de piso no cabeçalho**, com os pisos cadastrados, lembrado em cada navegador. Estações, mapas, fila, sessões e a busca de clientes mostram só o piso escolhido; o cabeçalho, o Controle de sessões e as colunas de clientes e fila ficam na cor do piso.
- **Tela Clientes com uma aba por piso** ("Clientes do Adulto", "Clientes do Infantil"...), a mesma escolha do cabeçalho, e a tabela na cor do piso; coluna **Idade**. A busca do Painel mostra a idade.
- **Cadastro novo** nasce no piso escolhido. **Ficha do cliente**: etiqueta do piso e troca por uma lista, com confirmação (com a idade) e "trocado por ... em ...".
- **Servidor**: tabela `pisos`, `usuarios.piso_id` e `grupos_estacao.piso_id`; API `/api/pisos/`; `GET /api/clientes/?piso_id=`. Os pisos que o 4.7a gravou como texto (inclusive os da importação do infantil já feita no servidor) viram `piso_id` sozinhos ao subir.
- `importar_infantil.py --piso NOME` escolhe o piso de destino (padrão: Infantil).

## 2026-11-05 — Importação do VSCyber do piso infantil (Ciclo 4, tarefa 4.7c)

- **`server/importar_infantil.py`**: importa os 8.660 clientes do VSCyber do infantil e completa o nascimento dos 42 mil do adulto. Sem `--aplicar` só simula; com `--aplicar` faz um backup antes e grava.
- Regras decididas com o Matheus: todos entram no piso Infantil; o mesmo login nos dois VSCyber, com o mesmo primeiro nome e nascimento, vira um cadastro só (menor de 18 passa para o Infantil); os logins repetidos com nome ou nascimento diferente não entram e vão para uma planilha de conferência. Rodar de novo não duplica.
- `exportar_fdb.py` aceita outro arquivo e outra pasta de saída (`python exportar_fdb.py ARQUIVO.FDB export_infantil`).
- Numa cópia do banco: 8.349 novos no Infantil, 3 que já existiam passaram ao Infantil, 211 ficaram como estavam, 97 para conferir, 42.253 nascimentos preenchidos.

## 2026-11-05 — Piso adulto / infantil no servidor (Ciclo 4, tarefa 4.7a)

- **Piso do cliente**: o cadastro ganhou o piso (Adulto ou Infantil). Quem já está no banco ficou no Adulto. A troca do piso registra quem trocou e quando (`piso_alterado_por`, `piso_alterado_em`); a confirmação fica no painel (4.7b).
- **Piso da estação**: vem do grupo (`grupos_estacao.piso`). Estação sem grupo ou grupo sem piso conta como Adulto, então só um PC marcado como Infantil recebe criança.
- **Recusa sempre**: cliente de um piso não faz login num PC do outro ("Este cadastro é do piso Infantil e este computador é do piso Adulto. Procure o atendimento.") e não pode ser arrastado para ele (iniciar direto). A liberação continua valendo para um PC do piso certo.
- A API devolve o piso em clientes, estações, grupos e fila (`cliente_piso`). Regra em `app/pisos.py`.
- Até marcar o grupo da sala infantil como Infantil (painel, 4.7b), nada muda no uso.

## 2026-11-05 — Painel antigo aposentado (Ciclo 2, tarefa 2.7)

- **`/antigo` removido**: o painel HTML anterior (`server/app/static_antigo`) saiu; o React é o único painel.
- **`server/main.py` voltou a só reexportar `app.main:app`**: um envio pelo GitHub (09/10) tinha posto lá uma cópia velha do servidor inteiro, e quem subisse com `uvicorn main:app` (start command antigo do Render) rodaria o código de outubro. Teste novo impede que volte.

## 2026-11-05 — Servidor sobe sozinho e backup diário do banco (Ciclo 4, tarefas 4.5 e 4.6)

- **Backup diário**: o servidor copia o `cybercafe.db` todo dia logo depois da meia-noite (ou ao subir, se o do dia ainda não foi feito) para `server/backups` e guarda os últimos 14 dias. A cópia usa o backup do próprio SQLite, então fica íntegra mesmo com o servidor em uso. A pasta e os dias se trocam no `.env` (`BACKUP_PASTA`, `BACKUP_DIAS`), por exemplo para outro disco.
- **Painel → Configurações → Servidor → Backup do banco**: lista os backups, **Fazer backup agora** e **Baixar** (para guardar uma cópia fora do servidor). Só o admin.
- **Servidor subindo sozinho**: `server/registrar_servidor.ps1` (como Administrador) cria a tarefa `MatheCafe-Servidor`, que sobe o servidor quando o Windows liga, sem ninguém fazer login, e reabre se ele cair; também libera a porta no firewall. A saída vai para `server/logs/servidor.log`. `iniciar_servidor.bat` sobe o servidor do mesmo jeito à mão.

## 2026-11-05 — Trocar servidor e banco sem reinstalar; estação presa em manutenção (agente 1.7.1)

- **Estação presa em "manutenção"**: o status ficava gravado no banco e não saía quando o agente reabria na tela de login (fechado ou reiniciado na manutenção). O painel mostrava Manutenção e o servidor recusava o login do cliente ("Estação não está disponível"). Agora toda conexão nova volta a estação para livre; se o agente só caiu e voltou ainda na manutenção, ele avisa o servidor logo em seguida.
- **Configurar conexão no agente**: no modo manutenção, o botão **Configurar conexão** troca o endereço do servidor e o nome da estação, com **Testar** (conecta como a estação e diz se o servidor a reconhece) e **Salvar e reiniciar** (grava o `agente.cfg` e reabre o agente). Não precisa mais do `instalar.bat` para isso.
- **Manutenção sem conexão**: agente apontando para o servidor errado fica offline e não conseguia entrar na manutenção. Agora vale, sem conexão, o login de um operador que já entrou na manutenção daquela estação com o servidor no ar (os últimos 5, guardados só como hash PBKDF2 no `agente.cfg`; se o servidor recusar a senha, o operador é esquecido).
- **Banco do servidor pelo painel**: Configurações → **Servidor** mostra o banco em uso (sem a senha) e troca por outro (PostgreSQL/Supabase ou SQLite): **Testar conexão** diz se conectou e se o banco já tem dados do MatheCafé; **Salvar** grava `DATABASE_URL` no `server/.env`, que vale ao reiniciar o servidor. Se a URL vem da variável de ambiente (Render), o painel avisa que a troca é por lá.
- **Driver do PostgreSQL**: `psycopg[binary]` não estava no `requirements.txt`, então o servidor não conectaria no Supabase. URLs `postgres://` e `postgresql://` passam a usar o psycopg 3.

## 2026-10-30 — Barra própria, tema claro e programação da biblioteca (agente 1.7.0)

- **Barra de tarefas do MatheCafé** (agente, `BarraSessao`): na sessão a barra do Windows some e a nossa fica exatamente no lugar dela, sempre visível, com **Início** (volta ao launcher), um botão por app liberado aberto (clicar traz para a frente), o tema, o tempo restante e **Encerrar sessão**. O espaço reservado pela barra do Windows continua reservado, então um app maximizado não cobre a nossa. Ela some na pausa, na manutenção e no fim da sessão, e a barra do Windows volta ao sair da sessão ou se o agente fechar.
- **Sessão em tela cheia sem barra de título**: na 1.6.6 ainda dava para arrastar a janela e a barra do Windows sumia; agora não há o que arrastar nem diminuir, e os apps abrem na frente. Sem barra do Windows, o Iniciar também não abre pelo mouse (6.6).
- **Tema claro**:
  - No painel: botão de sol/lua no cabeçalho, guardado no navegador de cada operador (`lib/tema.ts`, cores em `index.css`).
  - No agente: o próprio cliente troca no botão "Tema claro" da tela de login ou da barra; fica guardado no `agente.cfg` da estação (`PALETAS`, `trocar_cores`).
- **Programação da biblioteca**: Configurações → **Programação** recebe os cartazes (vários de uma vez, reduzidos para 1280px), com título, ordem, ativo e segundos por cartaz. O agente mostra os ativos em carrossel numa coluna ao lado dos apps durante a sessão e recarrega sozinho quando algo muda no painel (evento `programacao_atualizada`). Igual em todas as estações.
- API: `/api/programacao/` (admin cadastra; operador consulta) e `/api/programacao/agente` + `/api/programacao/{id}/imagem`, abertos para o agente (cartazes públicos, como a atualização do agente). Validação de imagem num módulo só (`app/imagens.py`), usado também pela foto do cliente.

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
