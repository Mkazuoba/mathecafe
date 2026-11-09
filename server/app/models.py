from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, LargeBinary, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String(50), unique=True, nullable=False, index=True)
    nome = Column(String(100), nullable=False)
    senha_hash = Column(String(255), nullable=False)
    perfil = Column(String(20), nullable=False)  # admin | operador | cliente
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    saldo_segundos = Column(Integer, default=0)
    saldo_dia = Column(Date, nullable=True)  # dia (Brasília) do saldo; outro dia = cota cheia (tempo_diario.py)
    observacao = Column(Text, nullable=True)
    documento = Column(String(30), nullable=True)
    email = Column(String(120), nullable=True)
    data_nascimento = Column(Date, nullable=True)
    foto_em = Column(DateTime, nullable=True)  # quando a foto mudou; None = sem foto (fotos_clientes)
    # Piso do cliente (app/pisos.py): so entra nos PCs do mesmo piso. Vazio = piso padrao.
    # A troca registra o nome de quem trocou e quando.
    piso_id = Column(Integer, ForeignKey("pisos.id"), nullable=True, index=True)
    piso_alterado_por = Column(String(100), nullable=True)
    piso_alterado_em = Column(DateTime, nullable=True)

    piso = relationship("Piso")
    sessoes = relationship("Sessao", back_populates="cliente", foreign_keys="Sessao.cliente_id")
    autorizacao = relationship("Autorizacao", back_populates="cliente", uselist=False,
                               foreign_keys="Autorizacao.cliente_id")


class Piso(Base):
    """Piso da biblioteca (Adulto, Infantil...), cadastrado pelo admin. Cada mapa
    (grupo) e cada cliente pertence a um; um deles e o padrao (app/pisos.py)."""
    __tablename__ = "pisos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(40), nullable=False, unique=True)
    cor = Column(String(7), nullable=False, default="#6366f1")
    padrao = Column(Boolean, default=False)


class GrupoEstacao(Base):
    __tablename__ = "grupos_estacao"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(50), nullable=False)
    tempo_padrao_segundos = Column(Integer, default=7200)
    cor = Column(String(7), default="#6366f1")  # hex, ex: "#6366f1"
    # Piso do mapa: obrigatorio ao criar; vazio so em grupos antigos (o painel avisa)
    # e, ate escolher, conta como o piso padrao
    piso_id = Column(Integer, ForeignKey("pisos.id"), nullable=True)
    ativo = Column(Boolean, default=True)
    # Zona no Mapa (px no quadro do piso): vazio = o painel arruma sozinho
    zona_x = Column(Integer, nullable=True)
    zona_y = Column(Integer, nullable=True)
    zona_largura = Column(Integer, nullable=True)
    zona_altura = Column(Integer, nullable=True)
    piso = relationship("Piso")
    estacoes = relationship("Estacao", back_populates="grupo")


class Estacao(Base):
    __tablename__ = "estacoes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(20), nullable=False, unique=True)
    grupo_id = Column(Integer, ForeignKey("grupos_estacao.id"), nullable=True)
    status = Column(String(20), default="desligada")
    ativa = Column(Boolean, default=True)
    ip = Column(String(50), nullable=True)
    mac_address = Column(String(17), nullable=True)
    # versao que o agente informou ao conectar (evento estado); vazio = agente antigo ou nunca conectou
    versao_agente = Column(String(20), nullable=True)
    ultimo_ping = Column(DateTime, nullable=True)
    pos_x = Column(Integer, default=0)
    pos_y = Column(Integer, default=0)
    grupo = relationship("GrupoEstacao", back_populates="estacoes")
    sessoes = relationship("Sessao", back_populates="estacao")


class Autorizacao(Base):
    __tablename__ = "autorizacoes"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("usuarios.id"), unique=True, nullable=False)
    autorizado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    autorizado_em = Column(DateTime, default=datetime.utcnow)
    usado = Column(Boolean, default=False)
    cliente = relationship("Usuario", back_populates="autorizacao", foreign_keys=[cliente_id])
    autorizado_por = relationship("Usuario", foreign_keys=[autorizado_por_id])


class Sessao(Base):
    __tablename__ = "sessoes"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    estacao_id = Column(Integer, ForeignKey("estacoes.id"), nullable=False)
    iniciada_em = Column(DateTime, default=datetime.utcnow)
    encerrada_em = Column(DateTime, nullable=True)
    tempo_total_segundos = Column(Integer, nullable=True)
    tempo_consumido_segundos = Column(Integer, default=0)
    motivo_encerramento = Column(String(30), nullable=True)
    pausada = Column(Boolean, default=False)
    pausada_em = Column(DateTime, nullable=True)
    tempo_pausado_segundos = Column(Integer, default=0)
    # Quando o PC perdeu a conexao (queda dele, da rede ou do servidor). O cliente
    # segue usando no PC; a sessao so encerra pelo agente, pelo operador ou, se o
    # PC nunca voltar, quando o tempo acabaria (cobrando ate aqui). Vazio = conectado.
    sem_conexao_desde = Column(DateTime, nullable=True)
    cliente = relationship("Usuario", back_populates="sessoes", foreign_keys=[cliente_id])
    estacao = relationship("Estacao", back_populates="sessoes")


class CategoriaApp(Base):
    """Categoria dos apps (Internet, Jogos...), cadastrada pelo admin. Filtra a
    tela de apps do agente; app sem categoria fica em "Outros"."""
    __tablename__ = "categorias_apps"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(40), nullable=False, unique=True)
    ordem = Column(Integer, nullable=False, default=0)


class AppPermitido(Base):
    __tablename__ = "apps_permitidos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    processo = Column(String(100), nullable=False)
    caminho = Column(String(500), nullable=True)
    imagem_url = Column(String(500), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias_apps.id"), nullable=True)
    # antigo (ate 09/11/2026): o app valia num mapa ou em todos. Agora vale por
    # piso (apps_pisos); grupo_id e ativo ficam so para a conversao.
    grupo_id = Column(Integer, ForeignKey("grupos_estacao.id"), nullable=True)
    ativo = Column(Boolean, default=True)
    grupo = relationship("GrupoEstacao")
    categoria = relationship("CategoriaApp")
    pisos_ligados = relationship("AppPiso", cascade="all, delete-orphan")


class AppPiso(Base):
    """O app esta ligado neste piso: aparece no menu das estacoes do piso e nao
    e fechado nelas. Sem linha, desligado no piso."""
    __tablename__ = "apps_pisos"
    app_id = Column(Integer, ForeignKey("apps_permitidos.id"), primary_key=True)
    piso_id = Column(Integer, ForeignKey("pisos.id"), primary_key=True)


class ConfiguracaoSistema(Base):
    __tablename__ = "configuracoes"
    chave = Column(String(100), primary_key=True)
    valor = Column(String(500), nullable=False)


class FotoCliente(Base):
    """Foto do cliente, à parte para a lista de clientes não carregar imagens."""
    __tablename__ = "fotos_clientes"
    cliente_id = Column(Integer, ForeignKey("usuarios.id"), primary_key=True)
    tipo = Column(String(20), nullable=False)  # image/jpeg | image/png | image/webp
    conteudo = Column(LargeBinary, nullable=False)


class ItemProgramacao(Base):
    """Cartaz da programação da biblioteca (carrossel no agente, na sessão)."""
    __tablename__ = "programacao"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(120), default="")
    ordem = Column(Integer, default=0)
    ativo = Column(Boolean, default=True)
    tipo = Column(String(20), nullable=False)
    conteudo = Column(LargeBinary, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow)


class AcaoOperador(Base):
    """O que cada operador (ou admin) fez no painel (8.1; app/registro.py).
    Nomes e login guardados no momento da acao: o registro nao muda se o
    cadastro mudar ou for excluido."""
    __tablename__ = "acoes_operadores"
    id = Column(Integer, primary_key=True, index=True)
    quando = Column(DateTime, default=datetime.utcnow, index=True)
    operador_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    operador_nome = Column(String(100), nullable=False)
    acao = Column(String(30), nullable=False, index=True)
    cliente_id = Column(Integer, nullable=True, index=True)
    cliente_login = Column(String(50), nullable=True)
    cliente_nome = Column(String(100), nullable=True)
    estacao = Column(String(20), nullable=True, index=True)
    detalhe = Column(Text, nullable=True)
