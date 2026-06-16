from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
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
    observacao = Column(Text, nullable=True)

    sessoes = relationship("Sessao", back_populates="cliente", foreign_keys="Sessao.cliente_id")
    autorizacao = relationship("Autorizacao", back_populates="cliente", uselist=False,
                               foreign_keys="Autorizacao.cliente_id")


class GrupoEstacao(Base):
    __tablename__ = "grupos_estacao"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(50), nullable=False)
    tempo_padrao_segundos = Column(Integer, default=7200)
    ativo = Column(Boolean, default=True)
    estacoes = relationship("Estacao", back_populates="grupo")


class Estacao(Base):
    __tablename__ = "estacoes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(20), nullable=False, unique=True)
    grupo_id = Column(Integer, ForeignKey("grupos_estacao.id"), nullable=True)
    status = Column(String(20), default="desligada")
    ativa = Column(Boolean, default=True)
    ip = Column(String(50), nullable=True)
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
    cliente = relationship("Usuario", back_populates="sessoes", foreign_keys=[cliente_id])
    estacao = relationship("Estacao", back_populates="sessoes")


class AppPermitido(Base):
    __tablename__ = "apps_permitidos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    processo = Column(String(100), nullable=False)
    caminho = Column(String(500), nullable=True)
    grupo_id = Column(Integer, ForeignKey("grupos_estacao.id"), nullable=True)
    ativo = Column(Boolean, default=True)


class ConfiguracaoSistema(Base):
    __tablename__ = "configuracoes"
    chave = Column(String(100), primary_key=True)
    valor = Column(String(500), nullable=False)
