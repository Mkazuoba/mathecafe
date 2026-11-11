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
copy .env.example .env           # SECRET_KEY pode ficar vazia: o servidor gera uma
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

### Servidor de produção (máquina da biblioteca)

Para o servidor subir sozinho quando a máquina liga, sem terminal aberto: abra o PowerShell **como Administrador** na pasta `server` e rode

```bash
powershell -ExecutionPolicy Bypass -File registrar_servidor.ps1
```

Ele cria a tarefa `MatheCafe-Servidor` (na inicialização do Windows, como SYSTEM, reabrindo se cair), libera a porta 8000 no firewall e já sobe o servidor. Feche antes o servidor que estiver rodando num terminal (os dois não usam a mesma porta).

- Log: `server\logs\servidor.log`.
- **Reiniciar** (depois de atualizar o código ou trocar o banco), sem reiniciar o computador e sem administrador do Windows, de um destes jeitos:
  - no computador do servidor, clique duas vezes em **`server\reiniciar_servidor.bat`**: ele pede o reinício e espera o servidor voltar (uns 10 s);
  - no painel, Configurações → Servidor → **Reiniciar servidor** (admin do MatheCafé).

  Os dois só funcionam com o servidor aberto pela tarefa `MatheCafe-Servidor` (desde 10/11 o `reiniciar_servidor.bat` só é atendido por servidor de 10/11 em diante: na primeira vez, use o botão do painel). O servidor termina e o `iniciar_servidor.bat` o sobe de novo em 3 s; as estações com agente 1.8+ seguem a sessão. Pela linha de comando, num PowerShell **como administrador** ("Executar como administrador"): `schtasks /end /tn MatheCafe-Servidor` e `schtasks /run /tn MatheCafe-Servidor`.
- Outra porta: `registrar_servidor.ps1 -Porta 8080`. Desfazer: `registrar_servidor.ps1 -Remover`.
- Para subir à mão do mesmo jeito (sem `--reload`): `iniciar_servidor.bat`.

### Backup do banco

O servidor faz sozinho um backup do `cybercafe.db` por dia, logo depois da meia-noite (ou quando sobe, se o do dia ainda não foi feito), em `server\backups`, guardando 14 dias. No painel: Configurações → Servidor → **Backup do banco** (fazer agora, baixar). No `.env`: `BACKUP_PASTA` (outro disco ou pasta de rede, ex.: `D:/BackupMatheCafe`) e `BACKUP_DIAS`.

Guarde junto, uma vez, o `server\.secret_key` (ou a `SECRET_KEY` do `.env`): sem ele o banco restaurado funciona, mas todos precisam entrar no painel de novo.

**Restaurar** (pelo painel): Configurações → Servidor → Backup do banco → **Restaurar** no backup escolhido, ou **Restaurar de um arquivo...** para um backup guardado fora do servidor (pendrive, outro PC). O servidor confere o arquivo (banco do MatheCafé, sem corrupção), reinicia e, ao subir, guarda o banco atual como `antes-da-restauracao-AAAA-MM-DD-HHMMSS.db` na pasta dos backups e põe o backup no lugar; o painel recarrega sozinho. Para **desfazer**, restaure esse "Banco de antes da restauração" (lista *Para desfazer uma restauração*). Com computadores em uso, o painel avisa: as sessões voltam ao estado do backup. A restauração entra no registro de ações. Sem a tarefa (servidor aberto à mão), ela vale no próximo início.

À mão (se o painel não abrir): pare o servidor (`schtasks /end /tn MatheCafe-Servidor`), guarde o `cybercafe.db` atual com outro nome, copie o backup escolhido para `server\cybercafe.db` e suba de novo (`schtasks /run /tn MatheCafe-Servidor`).

## 2. Painel web (React)

O painel já vem compilado em `server/app/static/`: para só usar o sistema, não precisa de Node. Para **mexer no painel**, instale o [Node.js LTS](https://nodejs.org) e:

```bash
cd server/frontend
npm install
npm run dev          # painel em http://localhost:5173, com recarga automática
```

O `npm run dev` usa o servidor Python (porta 8000) para `/api` e `/ws`, então deixe o `uvicorn` rodando junto. Para apontar para outro servidor (o de teste, por exemplo), defina `MATHECAFE_API=http://127.0.0.1:8010` antes do `npm run dev`.

Terminou uma mudança? Gere o build e faça o commit dos arquivos de `server/app/static/` junto com o código:

```bash
npm run build        # compila para server/app/static
```

## 3. Primeiro uso (pelo painel)

1. **Configurações → Operadores**: cadastre os operadores.
2. **Configurações → Apps permitidos**: cadastre os programas que os clientes podem abrir (processo `.exe`, caminho completo e, se quiser, uma imagem de capa).
3. **Mapa → Modo configuração**: crie as zonas da sala. As estações aparecem sozinhas depois de instalar o agente (ver 4): aprove-as em **Mapa → Novas estações** e arraste-as para a posição na sala. Cadastrar a estação à mão só é preciso para agentes antigos (até a 1.13), com o mesmo nome usado neles.
4. **Clientes**: cadastre os clientes.
5. **Programação e avisos** (menu lateral, abaixo do Mapa; opcional): suba os cartazes da programação da biblioteca; eles aparecem ao lado dos apps durante a sessão.
6. **Painel**: clique em **Liberar** (ou arraste o cliente para uma estação). Ele entra na fila e pode fazer login no PC.

## 4. Agente (em cada estação)

**Não precisa instalar nada antes**, só ter **internet** na estação. O instalador baixa o Python (versão em `PY_VERSAO`, no começo do `instalar.bat`) do python.org e instala um Python **só do agente** em `C:\MatheCafe\python`, com Tkinter, sem atalho e sem mexer em outro Python da máquina. Depois instala as dependências do `requirements.txt` pelo pip. O download e o pip usam o proxy do Windows (o mesmo do navegador). Numa reinstalação, se o Python do agente já estiver lá, ele é reaproveitado. Se a mesma versão do Python já existia em outro lugar da máquina, o instalador do python.org não instala de novo: ela é copiada para `C:\MatheCafe\python`.

Copie a pasta `agente/` para o PC, clique com o botão direito em **`instalar.bat`** → Executar como administrador e responda as perguntas: o **nome da estação** (Enter usa o nome do Windows), o **endereço do servidor** (Enter usa o de `agente/servidor.txt`, hoje `10.26.31.77:8000`; se o servidor mudar de IP, troque esse arquivo), o **piso** (a lista vem do servidor: Adulto, Infantil...) e a senha do usuário `cliente`. Não pede login do painel. Ele testa na hora se o servidor responde: se não, avisa e pede o endereço de novo (ou continua com **C**). Ele:

1. cria o usuário Windows `cliente` (sem admin, senha que não expira) e liga o autologin;
2. fecha o agente, se já estiver rodando de `C:\MatheCafe`; copia o agente para lá; baixa e instala o Python do agente em `C:\MatheCafe\python` (se ainda não estiver); cria o `venv` e instala as dependências;
3. grava `agente.cfg` (numa reinstalação, mantém o `ID=` que já estava lá) e dá ao `cliente` permissão de escrita na pasta (para o `agente.cfg` e a atualização);
4. registra a tarefa `MatheCafe-Agente` (`registrar_tarefa.ps1`): abre o `pythonw agente.py` no logon do `cliente`, **dentro da sessão dele**, sem limite de tempo e reabrindo se cair;
5. desliga, no perfil do `cliente`, o Gerenciador de Tarefas, o Bloquear e o Alterar senha, que aparecem no Ctrl+Alt+Del, e prende os downloads do Chrome e do Edge na pasta Downloads, bloqueando os perigosos (`politicas_cliente.ps1`). Se o `cliente` nunca entrou no Windows, o perfil dele é criado na hora;

Quando o agente abre pela primeira vez, ele gera um identificador (`ID=` no `agente.cfg`) e conecta com o piso escolhido (`PISO=`, agente 1.20). **Se o mapa daquele piso já tem uma estação com esse nome** (criada no Modo configuração, ainda sem computador), o PC entra direto nela, já aprovado: monte o mapa antes e instale com os mesmos nomes. O mesmo nome pode existir no Adulto e no Infantil. Senão, ele aparece no painel em **Mapa → Novas estações** (com o piso) (botão laranja com a contagem; só para admin). Ali você confirma ou troca o nome, escolhe a zona e clica em **Aprovar**. Até aprovar, a tela de login do PC avisa que ele aguarda aprovação e ninguém entra (o modo manutenção funciona). **Recusar** bloqueia aquele PC; se foi engano, cadastre no Modo configuração uma estação com o mesmo nome e ela volta.

**Computador formatado ou trocado**: o identificador antigo se perde e o PC chega em Novas estações com sufixo (`AD-3-2`). Em **É o computador de**, escolha **Substitui a AD-3** (o painel já sugere quando o nome bate) e clique em **Substituir**: ele vira a AD-3, com o mesmo nome, zona, lugar no mapa e histórico. Desligue o computador antigo antes (com a AD-3 ligada, o painel recusa). Se o antigo voltar um dia, ele é que cai em Novas estações.

**Trocar o nome** de uma estação: clique nela no Mapa → lápis ao lado do nome. O agente 1.14 recebe o nome novo na hora e grava no `agente.cfg`; agentes antigos precisam do nome novo em Configurar conexão (`Ctrl+Shift+M`). Trocar o nome **no próprio PC** (Configurar conexão) não muda sozinho: vira um pedido em **Mapa → Novas estações** ("AD-01 quer se chamar AD-05", com Aceitar e Recusar), e até aceitar a estação segue com o nome atual.

**Atualizar uma estação**: o agente nunca se atualiza sozinho. Pelo painel (agente 1.16 ou mais novo): Controle de sessões → a estação → linha **Agente** → **Atualizar agora**, ou selecione várias e use **Atualizar agente** na barra de ações em massa; só as estações sem cliente atualizam, e o agente volta na tela de login. Pelo PC (qualquer versão desde a 1.11): `Ctrl+Shift+M` → login de operador → **Atualizar para a versão X**. Agentes até a 1.15 precisam passar uma vez pela manutenção para chegar à 1.16. Até a 1.10.x ele se atualizava sozinho ao abrir. Mudanças no instalador ou na tarefa agendada (como o fim do atraso de 5s no logon, de 30/10) só valem rodando o `instalar.bat` de novo, com os arquivos novos: ele substitui tudo e mantém o usuário.

Reinicie: o PC entra sozinho como `cliente` e o agente abre. Para desfazer: `C:\MatheCafe\desinstalar.bat` como administrador (remove a tarefa e o autologin).

- A tarefa **não pode** rodar como SYSTEM nem com senha gravada ("executar estando conectado ou não"): nos dois casos ela roda sem área de trabalho e a janela do agente nunca aparece.
- O agente roda como `cliente`, sem admin. Ele encerra os programas do próprio `cliente`, que é o que importa; processos de outros usuários ficam de fora.
- Para testar à mão (sem tarefa, como admin): `C:\MatheCafe\iniciar.bat ws://IP_DO_SERVIDOR:8000 PC-01`.
- O nome da estação precisa ser exatamente o cadastrado no Mapa.
- Antes, confira a rede: no navegador da estação, `http://IP_DO_SERVIDOR:8000` precisa abrir o painel. Se não abrir, libere o Python no Firewall do Windows **da máquina do servidor** (redes privadas).
- Servidor no Render: use `wss://` em vez de `ws://`.
- **Modo manutenção**: `Ctrl+Shift+M` na estação, depois login e senha de um operador ou admin (conferidos pelo servidor). Sem conexão, só entra quem já entrou na manutenção daquela estação com o servidor no ar. É a única saída do agente: Esc e fechar a janela só funcionam nela.
- **Trocar o servidor ou o nome da estação**: na manutenção, **Configurar conexão** → Testar → Salvar e reiniciar. Não precisa reinstalar.
- **Bloqueios fora da manutenção**: na tela de login, Win, Ctrl+Esc, Alt+Tab, Alt+Esc e Alt+F4 não fazem nada. Na sessão Win e Ctrl+Esc continuam bloqueados; a barra do Windows dá lugar à do MatheCafé (Início, apps abertos, tema, tempo, Encerrar), e o cliente também alterna e fecha os apps com Alt+Tab e Alt+F4 (o agente em si é tela cheia: não fecha, não minimiza, não diminui). Se a barra do Windows não voltar depois de um problema, sair do usuário e entrar de novo a traz de volta. Ctrl+Shift+Esc fica sempre bloqueado e o `taskmgr.exe` é fechado.
- **Estação travada sem servidor** (não dá para entrar em manutenção): Ctrl+Alt+Del → Sair e entre com a conta de admin segurando **Shift** para o autologin não entrar de novo.
- **Rede com proxy**: com o servidor num IP interno (10.x, 172.16-31.x, 192.168.x) ou num nome sem ponto, o agente conecta direto e ignora o proxy do Windows. O log do agente mostra "Conectando a ... (direto, sem proxy)".
- Erros fatais do agente ficam em `C:\MatheCafe\agente_erro.log`.

## Pisos e mapas

Configurações → **Pisos**: os pisos da biblioteca (nascem Adulto, o padrão, e Infantil). Cada um tem nome e cor; a cor marca o seletor do topo, as abas da tela Clientes e as colunas do Painel. Configurações → **Mapas**: cada mapa (sala) pertence a um piso, obrigatório ao criar. O cliente só entra nos computadores do piso dele (login no PC e arrastar para a estação).

Depois de atualizar um servidor que já tinha mapas, abra Configurações → Mapas: os mapas antigos aparecem em vermelho ("sem piso") até alguém escolher o piso de cada um. Até lá, contam como o piso padrão.

## Importar clientes do VSCyber

Os bancos do VSCyber (Firebird) ficam em `Arquivos VSCyber/`, fora do git: têm dados pessoais dos clientes. O do adulto se chama `VSCYBER.FDB` e o do infantil, `VSCYBER_INFANTIL.FDB`.

1. **Exportar para CSV** (nesta máquina, que tem o Firebird 2.5 embutido em `fb25_embed`). O Firebird grava no cabeçalho do arquivo ao abrir, então exporte de uma **cópia**:
   - adulto: `python exportar_fdb.py` → `export/`
   - infantil: `python exportar_fdb.py CAMINHO\DA\COPIA.FDB export_infantil` → `export_infantil/`
2. **Levar para o servidor**: copie `export/clientes_importacao.csv` e `export_infantil/clientes_importacao.csv` para as mesmas pastas em `Arquivos VSCyber/` na máquina do servidor, ao lado da pasta `server`.
3. **Importar o infantil** (na pasta `server`, com o venv ativo):
   - `python importar_infantil.py` só **simula**: mostra quantos entram e não grava nada.
   - `python importar_infantil.py --aplicar` faz um backup do banco e grava.

O que o `importar_infantil.py` faz:
- preenche o nascimento dos clientes do adulto que estão sem;
- cria os clientes novos no piso Infantil (ou no que vier em `--piso NOME`, como cadastrado em Configurações → Pisos), com o nascimento e a senha `1234`;
- login que já existe e é a mesma pessoa (mesmo primeiro nome e mesmo nascimento): um cadastro só, e quem tem menos de 18 anos passa para o Infantil;
- login que já existe com nome ou nascimento diferente: não importa e lista em `export_infantil/conferir_logins_repetidos.csv`, para o atendimento conferir.

Rodar de novo não duplica ninguém. Se o VSCyber do infantil continuar em uso depois da exportação, exporte e importe de novo no dia da troca: entram só os cadastros novos.

(O `importar_vscyber.py` foi a importação do adulto, em 2026; não precisa rodar de novo.)

### Histórico de uso do VSCyber

Depois dos clientes, `importar_historico.py` traz os usos do VSCyber (`tabelas/CON.csv` dos dois exports) como sessões encerradas: aparecem no histórico de cada cliente e em Históricos → Uso.

1. Copie também a pasta `tabelas` de `export` e de `export_infantil` para o servidor (só `CON.csv` e `ESTC.csv` são usados).
2. Na pasta `server`: `python importar_historico.py` (simula) e depois `python importar_historico.py --aplicar` (faz backup e grava). `--desde AAAA-MM-DD` muda o início (padrão: 01/01/2022).

- As estações do VSCyber ficam com o nome antigo, como estações inativas ("BSP-87 (VS)" do adulto, "BSP-87 (VSI)" do infantil), num mapa inativo do piso de cada banco: não aparecem no Mapa nem no Painel.
- Ficam de fora: usos sem horário de fim, com mais de 16 horas ou de clientes que não existem no MatheCafé, e os dos logins da planilha de conferência. Rodar de novo não duplica.
- **Por enquanto o histórico importado fica escondido** (a importação ainda vai ser ajustada): as sessões ficam no banco, mas não aparecem em nenhum histórico nem relatório. Para mostrar, a chave `historico_vscyber_visivel` = `true` na tabela `configuracoes`.
- Numa cópia do banco (06/11/2026): 252.469 usos do adulto e 30.489 do infantil desde 2022, em uns 20 segundos; o banco ficou com 42 MB.

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
- Variáveis: `SECRET_KEY` (obrigatória aqui: o disco do Render é apagado a cada deploy, e a chave gerada em `server/.secret_key` sumiria junto), e `ADMIN_LOGIN` / `ADMIN_SENHA` para criar o primeiro admin (o Render gratuito não tem terminal para rodar o `app.cli`).

> O SQLite do Render é apagado a cada deploy. Para uso real, configure `DATABASE_URL` com um PostgreSQL (Supabase).

**Trocar o banco** (servidor da biblioteca, sem `DATABASE_URL` no ambiente): painel → Configurações → **Servidor** → cole a URL (Supabase: Project Settings → Database → Connection string) → Testar conexão → Salvar → reinicie o servidor. Um banco vazio recebe as tabelas sozinho, mas precisa de um admin (`python -m app.cli`). Depois de atualizar o código, rode `pip install -r requirements.txt` (driver do PostgreSQL).

### Docker

```bash
cd server
docker build -t mathecafe .
docker run -d -p 8000:8000 -v mathecafe-data:/data --env-file .env mathecafe
docker exec -it <container> python -m app.cli
```
