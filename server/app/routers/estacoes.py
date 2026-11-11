import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from app.database import get_db
from app.models import Estacao, GrupoEstacao, Autorizacao, Usuario, Sessao
from app.security import requer_perfil
from app.registro import registrar
from app.routers.agente import _numeros, _versao_dist, desatualizado
from app.websocket_manager import manager
from app import logs_estacoes
from app.tempo_diario import ESGOTADO_OPERADOR, reservar_tempo, saldo_do_dia
from app.models import Piso
from app.estacoes_novas import info_para_o_agente, nome_livre
from app.nomes_estacao import achar_estacao, exigir_nome_livre, piso_id_de, piso_id_do_grupo
from app.pisos import cor_para_o_agente, piso_da_estacao, piso_do_cliente, recusa_de_piso, resumo

router = APIRouter(prefix="/estacoes", tags=["estacoes"])

class EstacaoUpdate(BaseModel):
    nome: Optional[str] = None
    grupo_id: Optional[int] = None
    ativa: Optional[bool] = None
    pos_x: Optional[int] = None
    pos_y: Optional[int] = None
    mac_address: Optional[str] = None

class PosicaoUpdate(BaseModel):
    pos_x: int
    pos_y: int

def serial_estacao(e: Estacao):
    online = manager.estacao_conectada(e.id)
    # Status do banco: respeita a espera antes de marcar offline (main.py) e
    # mantém "manutencao" mesmo com o agente desconectado.
    status = e.status
    return {
        "id": e.id,
        "nome": e.nome,
        "grupo_id": e.grupo_id,
        "grupo_nome": e.grupo.nome if e.grupo else None,
        "grupo_cor": (e.grupo.cor or "#6366f1") if e.grupo else None,
        **resumo(piso_da_estacao(e)),
        "status": status,
        "online": online,
        "ip": e.ip,
        "ultimo_ping": e.ultimo_ping.isoformat() if e.ultimo_ping else None,
        "pos_x": e.pos_x,
        "pos_y": e.pos_y,
        "mac_address": e.mac_address,
        # 6.13: o painel avisa onde atualizar (o agente so se atualiza na manutencao)
        "versao_agente": e.versao_agente,
        "identificador": e.identificador,
        "aprovada": bool(e.aprovada),
        "nome_pedido": e.nome_pedido,
        "versao_atual": _versao_dist(),
        "agente_desatualizado": bool(e.versao_agente) and desatualizado(e.versao_agente),
    }

def serial_autorizacao(a: Autorizacao):
    return {
        "id": a.id,
        "cliente_id": a.cliente_id,
        "cliente_login": a.cliente.login,
        "cliente_nome": a.cliente.nome,
        "cliente_piso_id": (piso_do_cliente(a.cliente) or Piso()).id,
        "saldo_segundos": saldo_do_dia(a.cliente),
        "autorizado_em": a.autorizado_em.isoformat(),
        "autorizado_por": a.autorizado_por.nome,
    }

# ── Grupos ────────────────────────────────────────────────────────────────────
def serial_grupo(g: GrupoEstacao):
    return {
        "id": g.id,
        "nome": g.nome,
        "tempo_padrao_segundos": g.tempo_padrao_segundos,
        "cor": g.cor or "#6366f1",
        # posicao e tamanho da zona no Mapa (None: o painel arruma sozinho)
        "zona": ({"x": g.zona_x, "y": g.zona_y, "largura": g.zona_largura, "altura": g.zona_altura}
                 if g.zona_largura else None),
        **resumo(g.piso),  # vazio: grupo antigo sem piso (o painel avisa)
    }

@router.get("/grupos")
def listar_grupos(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    return [serial_grupo(g) for g in db.query(GrupoEstacao).filter(GrupoEstacao.ativo == True).all()]

@router.post("/grupos")
def criar_grupo(nome: str, piso_id: int, tempo_padrao_segundos: int = 7200, cor: str = "#6366f1",
                db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    # todo mapa novo pertence a um piso (sem ele, a sala infantil ja ficou no adulto)
    _piso_ou_400(db, piso_id)
    g = GrupoEstacao(nome=nome, tempo_padrao_segundos=tempo_padrao_segundos, cor=cor, piso_id=piso_id)
    db.add(g); db.commit(); db.refresh(g)
    return serial_grupo(g)

class GrupoUpdate(BaseModel):
    nome: Optional[str] = None
    tempo_padrao_segundos: Optional[int] = None
    cor: Optional[str] = None
    piso_id: Optional[int] = None
    zona: Optional["Zona"] = None


class Zona(BaseModel):
    x: int = Field(ge=0, le=20000)
    y: int = Field(ge=0, le=20000)
    largura: int = Field(ge=80, le=5000)  # 1 coluna de estacoes
    altura: int = Field(ge=100, le=5000)


GrupoUpdate.model_rebuild()


def _piso_ou_400(db: Session, piso_id: int):
    if db.get(Piso, piso_id) is None:
        raise HTTPException(400, "Piso não encontrado")

@router.put("/grupos/{grupo_id}")
def atualizar_grupo(grupo_id: int, data: GrupoUpdate,
                    db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    g = db.query(GrupoEstacao).filter(GrupoEstacao.id == grupo_id, GrupoEstacao.ativo == True).first()
    if not g: raise HTTPException(404, "Grupo nao encontrado")
    if data.nome is not None: g.nome = data.nome
    if data.tempo_padrao_segundos is not None: g.tempo_padrao_segundos = data.tempo_padrao_segundos
    if data.cor is not None: g.cor = data.cor
    if data.piso_id is not None:
        _piso_ou_400(db, data.piso_id)
        if data.piso_id != g.piso_id:
            for e in db.query(Estacao).filter(Estacao.grupo_id == g.id, Estacao.ativa == True):
                exigir_nome_livre(db, e.nome, data.piso_id, ignorar_id=e.id)
        g.piso_id = data.piso_id
    if data.zona is not None:
        g.zona_x, g.zona_y = data.zona.x, data.zona.y
        g.zona_largura, g.zona_altura = data.zona.largura, data.zona.altura
    db.commit()
    return serial_grupo(g)

# ── Ilhas do Mapa: duplicar e excluir varias de uma vez ──────────────────────

_NUMERO_NO_FIM = re.compile(r"^(.*?)(\d+)$")


class Proximos:
    """Proximos numeros livres por prefixo ("AD-" 07 -> AD-08), contando todas as
    estacoes (ate excluidas e pendentes) e as que ja foram dadas nesta copia."""

    def __init__(self, db: Session):
        self.nomes = {n for (n,) in db.query(Estacao.nome).all()}

    def para(self, nome: str) -> str:
        m = _NUMERO_NO_FIM.match(nome)
        if not m:
            novo = nome_livre_em(self.nomes, nome)
        else:
            prefixo, digitos = m.group(1), len(m.group(2))
            usados = [int(x.group(2)) for x in map(_NUMERO_NO_FIM.match, self.nomes)
                      if x and x.group(1) == prefixo]
            novo = f"{prefixo}{str(max(usados, default=0) + 1).zfill(digitos)}"
        self.nomes.add(novo)
        return novo


def nome_livre_em(nomes: set, base: str) -> str:
    n = 2
    while f"{base}-{n}" in nomes:
        n += 1
    return f"{base}-{n}"


class CopiaDeZona(BaseModel):
    grupo_id: int
    zona: Zona  # onde a copia fica no mapa (o painel poe embaixo de tudo)


class DuplicarBody(BaseModel):
    itens: List[CopiaDeZona] = Field(min_length=1, max_length=30)


@router.post("/grupos/duplicar")
def duplicar_grupos(data: DuplicarBody, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    """Copia cada ilha (nome, cor, tempo, piso, tamanho) com os PCs nas mesmas
    posicoes, renumerados com os proximos numeros livres. O PC real que for
    instalado com um desses nomes assume o lugar."""
    proximos = Proximos(db)
    copias = []
    for item in data.itens:
        g = db.query(GrupoEstacao).filter(GrupoEstacao.id == item.grupo_id, GrupoEstacao.ativo == True).first()
        if not g:
            raise HTTPException(404, "Zona não encontrada")
        nova = GrupoEstacao(nome=f"{g.nome} (cópia)"[:50], cor=g.cor, piso_id=g.piso_id,
                            tempo_padrao_segundos=g.tempo_padrao_segundos,
                            zona_x=item.zona.x, zona_y=item.zona.y,
                            zona_largura=item.zona.largura, zona_altura=item.zona.altura)
        db.add(nova)
        db.flush()
        pcs = db.query(Estacao).filter(Estacao.grupo_id == g.id, Estacao.ativa == True,
                                       Estacao.aprovada != False).order_by(Estacao.nome).all()
        for e in pcs:
            db.add(Estacao(nome=proximos.para(e.nome), grupo_id=nova.id, pos_x=e.pos_x, pos_y=e.pos_y))
        copias.append((g.nome, nova, len(pcs)))
    db.commit()
    for original, nova, n in copias:
        registrar(db, quem, "duplicar_zona", detalhe=f"{original} -> {nova.nome} ({n} estações)")
    return [serial_grupo(nova) for _, nova, _ in copias]


@router.delete("/grupos/{grupo_id}")
async def excluir_grupo(grupo_id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    """Exclui a ilha e os PCs dela (como Excluir estação: quem tem historico so e
    desativado). Com alguem usando um PC da ilha, nao exclui nada."""
    g = db.query(GrupoEstacao).filter(GrupoEstacao.id == grupo_id, GrupoEstacao.ativo == True).first()
    if not g:
        raise HTTPException(404, "Zona não encontrada")
    pcs = db.query(Estacao).filter(Estacao.grupo_id == g.id, Estacao.ativa == True).all()
    em_uso = [e.nome for e in pcs
              if db.query(Sessao).filter(Sessao.estacao_id == e.id, Sessao.encerrada_em == None).first()]
    if em_uso:
        raise HTTPException(400, f"{g.nome}: {', '.join(em_uso)} em uso. Encerre a sessão antes de excluir")
    nomes, ids = [], []
    for e in pcs:
        nomes.append(e.nome)
        ids.append(e.id)
        if db.query(Sessao).filter(Sessao.estacao_id == e.id).first():
            e.piso_id = piso_id_de(e)  # sem o grupo, continua no piso dela
            e.ativa = False
            e.grupo_id = None
        else:
            db.delete(e)
        logs_estacoes.apagar(e.id)
    g.ativo = False
    db.commit()
    registrar(db, quem, "excluir_zona", detalhe=f"{g.nome}" + (f" ({len(nomes)} estações)" if nomes else ""))
    for estacao_id in ids:
        await _soltar_conexao(estacao_id, 4004, "Estação excluída no painel")
    return {"ok": True, "estacoes": len(nomes)}


class LoteBody(BaseModel):
    prefixo: str = Field(min_length=1, max_length=15)
    inicio: int = Field(ge=0, le=9999)
    quantidade: int = Field(ge=1, le=60)
    digitos: int = Field(ge=1, le=4)
    grupo_id: Optional[int] = None


# ── Estações ──────────────────────────────────────────────────────────────────
@router.get("/")
def listar(grupo_id: Optional[int] = None, db: Session = Depends(get_db),
           _=Depends(requer_perfil("admin", "operador"))):
    q = db.query(Estacao).filter(Estacao.ativa == True, Estacao.aprovada != False)
    if grupo_id:
        q = q.filter(Estacao.grupo_id == grupo_id)
    return [serial_estacao(e) for e in q.order_by(Estacao.nome).all()]

@router.post("/")
def criar(nome: str, grupo_id: Optional[int] = None,
          db: Session = Depends(get_db), _=Depends(requer_perfil("admin"))):
    piso_id = piso_id_do_grupo(db, grupo_id)
    exigir_nome_livre(db, nome, piso_id)
    e = _excluida_no_piso(db, nome, piso_id)
    if e:
        # Estação excluída que tinha histórico: reativa, mantendo o histórico
        e.ativa, e.aprovada, e.grupo_id = True, True, grupo_id
    else:
        e = Estacao(nome=nome, grupo_id=grupo_id)
        db.add(e)
    db.commit(); db.refresh(e)
    return serial_estacao(e)


def _excluida_no_piso(db: Session, nome: str, piso_id: Optional[int]) -> Optional[Estacao]:
    """A estacao excluida (com historico) que tinha este nome neste piso."""
    excluidas = db.query(Estacao).filter(Estacao.nome == nome, Estacao.ativa == False).order_by(Estacao.id.desc())
    return next((x for x in excluidas if piso_id_de(x) == piso_id), None)

@router.post("/lote")
def criar_varias(data: LoteBody, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    """Varias estacoes de uma vez: prefixo + numeros (AD- 1 a 10, 2 digitos ->
    AD-01 ... AD-10). Se algum nome ja existe, nao cria nenhuma."""
    nomes = [f"{data.prefixo}{str(n).zfill(data.digitos)}"
             for n in range(data.inicio, data.inicio + data.quantidade)]
    if any(len(n) > 20 for n in nomes):
        raise HTTPException(400, "Nome muito comprido (até 20 letras)")
    piso_id = piso_id_do_grupo(db, data.grupo_id)
    no_piso = [e for e in db.query(Estacao).filter(Estacao.nome.in_(nomes)) if piso_id_de(e) == piso_id]
    repetidos = sorted({e.nome for e in no_piso if e.ativa}, key=nomes.index)
    if repetidos:
        raise HTTPException(400, f"Já existem neste piso: {', '.join(repetidos)}")
    excluidas = {e.nome: e for e in no_piso}
    for n in nomes:
        if n in excluidas:  # excluida com historico: volta, mantendo o historico
            excluidas[n].ativa, excluidas[n].aprovada, excluidas[n].grupo_id = True, True, data.grupo_id
        else:
            db.add(Estacao(nome=n, grupo_id=data.grupo_id))
    db.commit()
    registrar(db, quem, "criar_estacoes", detalhe=f"{nomes[0]} a {nomes[-1]}" if len(nomes) > 1 else nomes[0])
    return {"criadas": nomes}

# ── Novas estacoes (cadastro automatico pelo instalador; app/estacoes_novas.py) ──
class AprovarBody(BaseModel):
    nome: str = Field(min_length=1, max_length=20)
    grupo_id: Optional[int] = None


@router.get("/pendentes")
def listar_pendentes(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    q = db.query(Estacao).filter(Estacao.ativa == True, Estacao.aprovada == False)
    return [serial_estacao(e) for e in q.order_by(Estacao.id).all()]


async def _renomear(db: Session, e: Estacao, nome: str, piso_id: Optional[int] = None):
    """Troca o nome (unico no piso; piso_id: o piso para onde ela vai)."""
    nome = nome.strip()[:20]
    if not nome:
        raise HTTPException(400, "Informe o nome da estação")
    if nome == e.nome:
        return
    exigir_nome_livre(db, nome, piso_id if piso_id is not None else piso_id_de(e), ignorar_id=e.id)
    e.nome = nome
    e.nome_pedido = None  # renomeada: o pedido do PC (se havia) fica resolvido
    db.commit()


@router.get("/pedidos_nome")
def listar_pedidos_de_nome(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    """Estacoes cujo nome foi trocado no proprio PC e espera aprovacao."""
    q = db.query(Estacao).filter(Estacao.ativa == True, Estacao.aprovada != False, Estacao.nome_pedido != None)
    return [serial_estacao(e) for e in q.order_by(Estacao.nome).all()]


def _com_pedido(db: Session, id: int) -> Estacao:
    e = db.query(Estacao).filter(Estacao.id == id, Estacao.ativa == True, Estacao.nome_pedido != None).first()
    if not e:
        raise HTTPException(404, "Pedido de troca de nome não encontrado")
    return e


@router.post("/{id}/nome_pedido")
async def aceitar_nome_pedido(id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    e = _com_pedido(db, id)
    antigo, novo = e.nome, e.nome_pedido
    await _renomear(db, e, novo)
    registrar(db, quem, "renomear_estacao", estacao=e.nome, detalhe=f"pedido do PC; antes: {antigo}")
    await manager.enviar_estacao(e.id, "estacao_info", info_para_o_agente(e))
    await manager.broadcast_paineis("estacao_online", {"nome": e.nome, "estacao_id": e.id})
    return serial_estacao(e)


@router.delete("/{id}/nome_pedido")
async def recusar_nome_pedido(id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    e = _com_pedido(db, id)
    pedido = e.nome_pedido
    e.nome_pedido = None
    db.commit()
    registrar(db, quem, "recusar_nome_estacao", estacao=e.nome, detalhe=f"pedia {pedido}")
    await manager.broadcast_paineis("estacao_online", {"nome": e.nome, "estacao_id": e.id})
    return {"ok": True}


@router.post("/{id}/aprovar")
async def aprovar(id: int, body: AprovarBody, db: Session = Depends(get_db),
                  quem=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id, Estacao.ativa == True).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if body.grupo_id is not None and not db.get(GrupoEstacao, body.grupo_id):
        raise HTTPException(400, "Mapa não encontrado")
    piso_destino = piso_id_do_grupo(db, body.grupo_id) if body.grupo_id is not None else piso_id_de(e)
    if body.nome.strip()[:20] == e.nome:
        exigir_nome_livre(db, e.nome, piso_destino, ignorar_id=e.id)
    await _renomear(db, e, body.nome, piso_destino)
    e.aprovada = True
    e.grupo_id = body.grupo_id
    db.commit()
    registrar(db, quem, "aprovar_estacao", estacao=e.nome)
    await manager.enviar_estacao(e.id, "estacao_info", info_para_o_agente(e))
    await manager.broadcast_paineis("estacao_online", {"nome": e.nome, "estacao_id": e.id})
    return serial_estacao(e)


class SubstituirBody(BaseModel):
    estacao_id: int


@router.post("/{id}/substituir")
async def substituir(id: int, body: SubstituirBody, db: Session = Depends(get_db),
                     quem=Depends(requer_perfil("admin"))):
    """O PC pendente e o computador (formatado ou trocado) de uma estacao que ja
    existe: ela passa a ser dele, com o mesmo nome, zona, lugar no mapa e
    historico; o registro pendente some. O PC antigo, se voltar, cai em Novas
    estacoes."""
    p = db.query(Estacao).filter(Estacao.id == id, Estacao.ativa == True, Estacao.aprovada == False).first()
    if not p:
        raise HTTPException(404, "Estação pendente não encontrada")
    alvo = db.query(Estacao).filter(Estacao.id == body.estacao_id, Estacao.ativa == True,
                                    Estacao.aprovada != False).first()
    if not alvo:
        raise HTTPException(404, "Estação não encontrada")
    if manager.estacao_conectada(alvo.id):
        raise HTTPException(400, f"A {alvo.nome} está ligada agora: desligue o computador antigo antes de substituir")
    nome_pendente, id_pendente, identificador, versao = p.nome, p.id, p.identificador, p.versao_agente
    db.delete(p)
    db.flush()  # libera o identificador (unico) antes de passar para a estacao
    alvo.identificador = identificador
    if versao:
        alvo.versao_agente = versao
    db.commit()
    registrar(db, quem, "substituir_estacao", estacao=alvo.nome,
              detalhe=f"pelo computador que chegou como {nome_pendente}")
    # avisa o nome e derruba a conexao do pendente: o agente reconecta pelo id
    # e ja entra como a estacao antiga
    await manager.enviar_estacao(id_pendente, "estacao_info", info_para_o_agente(alvo))
    await _soltar_conexao(id_pendente, 4000, "Estação substituída: reconectando")
    await manager.broadcast_paineis("estacao_online", {"nome": alvo.nome, "estacao_id": alvo.id})
    return serial_estacao(alvo)


@router.delete("/{id}/pendente")
async def recusar(id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    """O PC fica bloqueado (o identificador dele e guardado). Para trazer de volta,
    reinstale o agente (gera outro identificador)."""
    e = db.query(Estacao).filter(Estacao.id == id, Estacao.ativa == True, Estacao.aprovada == False).first()
    if not e:
        raise HTTPException(404, "Estação pendente não encontrada")
    e.ativa = False
    db.commit()
    registrar(db, quem, "recusar_estacao", estacao=e.nome)
    await _soltar_conexao(e.id, 4004, "Estação recusada no painel")
    return {"ok": True}


@router.put("/{id}")
async def atualizar(id: int, data: EstacaoUpdate, db: Session = Depends(get_db),
                    quem=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    antigo = e.nome
    renomeada = bool(data.nome) and data.nome.strip() != e.nome
    piso_destino = piso_id_do_grupo(db, data.grupo_id) if data.grupo_id is not None else piso_id_de(e)
    if data.grupo_id is not None and not renomeada and piso_destino != piso_id_de(e):
        exigir_nome_livre(db, e.nome, piso_destino, ignorar_id=e.id)
    if data.nome:
        await _renomear(db, e, data.nome, piso_destino)
    if data.grupo_id is not None: e.grupo_id = data.grupo_id
    if data.ativa is not None: e.ativa = data.ativa
    if data.pos_x is not None: e.pos_x = data.pos_x
    if data.pos_y is not None: e.pos_y = data.pos_y
    if "mac_address" in data.model_fields_set: e.mac_address = data.mac_address
    db.commit()
    if renomeada:
        registrar(db, quem, "renomear_estacao", estacao=e.nome, detalhe=f"antes: {antigo}")
        # o agente 1.14 grava o nome novo no agente.cfg
        await manager.enviar_estacao(e.id, "estacao_info", info_para_o_agente(e))
    return serial_estacao(e)

@router.put("/{id}/posicao")
def atualizar_posicao(id: int, data: PosicaoUpdate, db: Session = Depends(get_db),
                       _=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    e.pos_x = data.pos_x
    e.pos_y = data.pos_y
    db.commit()
    return serial_estacao(e)


@router.post("/{nome}/ligar")
async def ligar_pc(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                   quem=Depends(requer_perfil("admin", "operador"))):
    """Envia magic packet Wake-on-LAN para a estacao."""
    e = achar_estacao(db, nome, id)
    _ligar(e)
    registrar(db, quem, "ligar_pc", estacao=e.nome)
    return {"ok": True}


def _ligar(e: Estacao):
    import socket
    mac = e.mac_address
    if not mac:
        raise HTTPException(400, "MAC address não configurado para esta estação")
    mac_limpo = mac.replace(":", "").replace("-", "")
    if len(mac_limpo) != 12:
        raise HTTPException(400, "MAC address inválido")
    payload = bytes.fromhex("F" * 12 + mac_limpo * 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(payload, ("255.255.255.255", 9))

@router.post("/{nome}/capturar_tela")
async def capturar_tela(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                        _=Depends(requer_perfil("admin", "operador"))):
    """Pede ao agente uma captura de tela silenciosa."""
    e = _estacao_online(db, nome, id)
    await manager.enviar_estacao(e.id, "capturar_tela", {})
    return {"ok": True}

async def _soltar_conexao(estacao_id: int, codigo: int, motivo: str):
    """Fecha a conexao do agente desta estacao (ele reconecta sozinho)."""
    ws = manager.estacoes.get(estacao_id)
    if ws:
        manager.desconectar_estacao(estacao_id, ws)
        try:
            await ws.close(code=codigo, reason=motivo)
        except Exception:
            pass


@router.delete("/{id}")
async def excluir(id: int, db: Session = Depends(get_db), quem=Depends(requer_perfil("admin"))):
    e = db.query(Estacao).filter(Estacao.id == id).first()
    if not e:
        raise HTTPException(404, "Estação não encontrada")
    if db.query(Sessao).filter(Sessao.estacao_id == id, Sessao.encerrada_em == None).first():
        raise HTTPException(400, f"A {e.nome} está em uso: encerre a sessão antes de excluir")
    nome = e.nome
    # O histórico de sessões (e os relatórios) aponta para a estação: nesse
    # caso ela só é desativada, o que já a tira de todas as listas do painel.
    desativada = db.query(Sessao).filter(Sessao.estacao_id == id).first() is not None
    if desativada:
        e.ativa = False
    else:
        db.delete(e)
    db.commit()
    logs_estacoes.apagar(id)
    registrar(db, quem, "excluir_estacao", estacao=nome,
              detalhe="o histórico de uso foi mantido" if desativada else None)
    # o agente 1.14+ que continuar instalado volta em Novas estacoes
    await _soltar_conexao(id, 4004, "Estação excluída no painel")
    return {"ok": True, "desativada": True} if desativada else {"ok": True}

@router.get("/{id}/logs")
def logs(id: int, db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    """O log de comunicacao do agente (saiu da tela do PC): as ultimas linhas, da mais antiga a mais nova."""
    if not db.query(Estacao).filter(Estacao.id == id).first():
        raise HTTPException(404, "Estação não encontrada")
    return logs_estacoes.linhas(id)

# ── Fila de espera ────────────────────────────────────────────────────────────
@router.get("/fila")
def ver_fila(db: Session = Depends(get_db), _=Depends(requer_perfil("admin", "operador"))):
    fila = db.query(Autorizacao).filter(Autorizacao.usado == False)\
             .order_by(Autorizacao.autorizado_em).all()
    return [serial_autorizacao(a) for a in fila]

@router.post("/fila/{cliente_id}")
async def autorizar_cliente(cliente_id: int, db: Session = Depends(get_db),
                             operador=Depends(requer_perfil("admin", "operador"))):
    cliente = db.query(Usuario).filter(
        Usuario.id == cliente_id, Usuario.perfil == "cliente", Usuario.ativo == True).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    auth = db.query(Autorizacao).filter(Autorizacao.cliente_id == cliente_id).first()

    if auth and not auth.usado:
        raise HTTPException(400, "Cliente já está na fila")
    if db.query(Sessao).filter(Sessao.cliente_id == cliente_id, Sessao.encerrada_em == None).first():
        raise HTTPException(400, "Cliente já está usando um computador")
    if saldo_do_dia(cliente) <= 0:
        raise HTTPException(400, ESGOTADO_OPERADOR)

    if auth:
        auth.usado = False
        auth.autorizado_por_id = int(operador["sub"])
        auth.autorizado_em = datetime.utcnow()
    else:
        auth = Autorizacao(
            cliente_id=cliente_id,
            autorizado_por_id=int(operador["sub"])
        )
        db.add(auth)

    db.commit()
    db.refresh(auth)
    registrar(db, operador, "liberar", cliente=cliente)

    await manager.broadcast_paineis("fila_atualizada", {
        "acao": "adicionado", "cliente": serial_autorizacao(auth)
    })
    return serial_autorizacao(auth)

@router.delete("/fila/{cliente_id}")
async def remover_fila(cliente_id: int, db: Session = Depends(get_db),
                        quem=Depends(requer_perfil("admin", "operador"))):
    auth = db.query(Autorizacao).filter(
        Autorizacao.cliente_id == cliente_id, Autorizacao.usado == False).first()
    if not auth:
        raise HTTPException(404, "Cliente não está na fila")
    cliente = auth.cliente
    db.delete(auth); db.commit()
    registrar(db, quem, "tirar_da_fila", cliente=cliente)
    await manager.broadcast_paineis("fila_atualizada", {"acao": "removido", "cliente_id": cliente_id})
    return {"ok": True}

# ── Comandos por estação ──────────────────────────────────────────────────────

class MensagemBody(BaseModel):
    texto: str

class LiberarDiretoBody(BaseModel):
    cliente_id: int

# ── Comandos para o PC (um a um ou em massa, em /acoes) ───────────────────────

def _estacao_online(db: Session, nome: str, estacao_id: Optional[int] = None) -> Estacao:
    e = achar_estacao(db, nome, estacao_id)
    if not manager.estacao_conectada(e.id):
        raise HTTPException(400, "Estação offline")
    return e


async def _desligar_ou_reiniciar(db: Session, e: Estacao, comando: str, quem: dict):
    """Encerra a sessao (o tempo que sobrou volta ao cliente) e manda o comando;
    o agente sai da sessao e desliga/reinicia depois de 10s."""
    if not manager.estacao_conectada(e.id):
        raise HTTPException(400, "Estação offline")
    from app.routers.sessoes import encerrar_pelo_operador
    aberta = db.query(Sessao).filter(Sessao.estacao_id == e.id, Sessao.encerrada_em == None).first()
    cliente = aberta.cliente if aberta else None
    if aberta:
        await encerrar_pelo_operador(db, aberta, avisar_agente=False)
    await manager.enviar_estacao(e.id, comando, {})
    registrar(db, quem, comando, cliente=cliente, estacao=e.nome,
              detalhe="a sessão do cliente foi encerrada" if cliente else None)


async def _mensagem(db: Session, e: Estacao, texto: str, quem: dict):
    if not manager.estacao_conectada(e.id):
        raise HTTPException(400, "Estação offline")
    await manager.enviar_estacao(e.id, "mensagem_tela", {"texto": texto})
    registrar(db, quem, "mensagem", estacao=e.nome, detalhe=texto)


async def _encerrar(db: Session, e: Estacao, quem: dict):
    aberta = db.query(Sessao).filter(Sessao.estacao_id == e.id, Sessao.encerrada_em == None).first()
    if not aberta:
        raise HTTPException(400, "Sem sessão em andamento")
    from app.routers.sessoes import encerrar_pelo_operador
    cliente = aberta.cliente
    await encerrar_pelo_operador(db, aberta)
    registrar(db, quem, "encerrar_sessao", cliente=cliente, estacao=e.nome)


@router.post("/{nome}/reiniciar")
async def reiniciar_pc(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                        quem=Depends(requer_perfil("admin", "operador"))):
    await _desligar_ou_reiniciar(db, achar_estacao(db, nome, id), "reiniciar_pc", quem)
    return {"ok": True}

@router.post("/{nome}/desligar")
async def desligar_pc(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                      quem=Depends(requer_perfil("admin", "operador"))):
    await _desligar_ou_reiniciar(db, achar_estacao(db, nome, id), "desligar_pc", quem)
    return {"ok": True}

@router.post("/{nome}/mensagem")
async def enviar_mensagem(nome: str, body: MensagemBody, id: Optional[int] = None, db: Session = Depends(get_db),
                           quem=Depends(requer_perfil("admin", "operador"))):
    await _mensagem(db, achar_estacao(db, nome, id), body.texto, quem)
    return {"ok": True}


# a partir desta versao o agente aceita "atualizar_agente" do painel; antes so
# pela manutencao (Ctrl+Shift+M -> Atualizar)
ATUALIZA_PELO_PAINEL = "1.16.0"


async def _atualizar_agente(db: Session, e: Estacao, quem: dict):
    if not manager.estacao_conectada(e.id):
        raise HTTPException(400, "Estação offline")
    nome = e.nome
    versao = e.versao_agente or "0"
    if _numeros(versao) < _numeros(ATUALIZA_PELO_PAINEL):
        raise HTTPException(400, f"O agente da {nome} (versão {e.versao_agente or 'antiga'}) só se atualiza pela "
                                 "manutenção (Ctrl+Shift+M → Atualizar). Depois disso, dá para atualizar pelo painel.")
    if e.status == "ocupada" or db.query(Sessao).filter(Sessao.estacao_id == e.id,
                                                        Sessao.encerrada_em == None).first():
        raise HTTPException(400, f"A {nome} está em uso: atualize quando o cliente terminar")
    await manager.enviar_estacao(e.id, "atualizar_agente", {"versao": _versao_dist()})
    registrar(db, quem, "atualizar_agente", estacao=nome, detalhe=f"{versao} → {_versao_dist()}")


@router.post("/{nome}/atualizar_agente")
async def atualizar_agente(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                           quem=Depends(requer_perfil("admin", "operador"))):
    """O agente baixa a versao do servidor e reinicia (volta na tela de login)."""
    await _atualizar_agente(db, achar_estacao(db, nome, id), quem)
    return {"ok": True}


class AcaoEmMassa(BaseModel):
    acao: Literal["mensagem", "encerrar", "reiniciar", "desligar", "ligar", "atualizar"]
    # pelo nome (unico) ou, desde 6.18, pelos ids (o painel manda ids)
    estacoes: List[str] = Field(default_factory=list, max_length=500)
    ids: List[int] = Field(default_factory=list, max_length=500)
    texto: Optional[str] = None


@router.post("/acoes")
async def acoes_em_massa(body: AcaoEmMassa, db: Session = Depends(get_db),
                         quem=Depends(requer_perfil("admin", "operador"))):
    """O mesmo comando para varias estacoes; cada uma diz se deu certo ("ok") ou
    o motivo (offline, sem sessao...), sem parar as outras."""
    texto = (body.texto or "").strip()
    if body.acao == "mensagem" and not texto:
        raise HTTPException(400, "Escreva a mensagem")
    if not body.estacoes and not body.ids:
        raise HTTPException(422, "Escolha as estações")
    resultados = {}
    # com ids, os nomes sao so para o servidor antigo (o painel manda os dois)
    alvos = ([(None, i) for i in dict.fromkeys(body.ids)] if body.ids
             else [(n, None) for n in dict.fromkeys(body.estacoes)])
    for nome, estacao_id in alvos:  # sem repetir, na ordem
        chave = nome
        try:
            e = achar_estacao(db, nome or "", estacao_id)
            chave = nome or e.nome
            if body.acao == "mensagem":
                await _mensagem(db, e, texto, quem)
            elif body.acao == "encerrar":
                await _encerrar(db, e, quem)
            elif body.acao in ("reiniciar", "desligar"):
                await _desligar_ou_reiniciar(db, e, f"{body.acao}_pc", quem)
            elif body.acao == "atualizar":
                await _atualizar_agente(db, e, quem)
            else:
                _ligar(e)
                registrar(db, quem, "ligar_pc", estacao=e.nome)
            resultados[chave] = "ok"
        except HTTPException as erro:
            db.rollback()
            resultados[chave or str(estacao_id)] = erro.detail
    return {"resultados": resultados}

@router.post("/{nome}/manutencao")
async def alternar_manutencao(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                               quem=Depends(requer_perfil("admin", "operador"))):
    e = _estacao_online(db, nome, id)
    if e.status == "manutencao":
        await manager.enviar_estacao(e.id, "desativar_manutencao", {})
        registrar(db, quem, "manutencao", estacao=e.nome, detalhe="saiu da manutenção")
    else:
        await manager.enviar_estacao(e.id, "ativar_manutencao", {})
        registrar(db, quem, "manutencao", estacao=e.nome, detalhe="entrou em manutenção")
    return {"ok": True}

@router.post("/{nome}/iniciar_direto")
async def iniciar_direto(nome: str, body: LiberarDiretoBody, id: Optional[int] = None,
                          db: Session = Depends(get_db),
                          operador=Depends(requer_perfil("admin", "operador"))):
    from datetime import datetime as dt
    from app.models import Sessao as SessaoModel

    e = _estacao_online(db, nome, id)
    nome = e.nome
    if e.status != "livre":
        raise HTTPException(400, "Estação não está livre")

    cliente = db.query(Usuario).filter(
        Usuario.id == body.cliente_id, Usuario.perfil == "cliente", Usuario.ativo == True).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    motivo_piso = recusa_de_piso(cliente, e)
    if motivo_piso:
        raise HTTPException(400, motivo_piso)
    from app import horario
    if horario.esta_fechada(horario.carregar(db), horario.agora_local()):
        raise HTTPException(400, horario.FECHADA)

    # Sessao ja ativa?
    sessao_existente = db.query(SessaoModel).filter(
        SessaoModel.cliente_id == cliente.id, SessaoModel.encerrada_em == None).first()
    if sessao_existente:
        raise HTTPException(400, "Cliente já tem sessão ativa")

    # Tempo do dia (zera a meia-noite de Brasilia; ver tempo_diario.py)
    tempo = reservar_tempo(db, cliente)
    if tempo is None:
        raise HTTPException(400, ESGOTADO_OPERADOR)

    # Cria/reusa autorizacao como usada
    auth = db.query(Autorizacao).filter(Autorizacao.cliente_id == cliente.id).first()
    if auth:
        auth.usado = True
        auth.autorizado_por_id = int(operador["sub"])
        auth.autorizado_em = dt.utcnow()
    else:
        auth = Autorizacao(
            cliente_id=cliente.id,
            autorizado_por_id=int(operador["sub"]),
            usado=True
        )
        db.add(auth)
    db.flush()

    # Cria sessao
    sessao = SessaoModel(
        cliente_id=cliente.id,
        estacao_id=e.id,
        tempo_total_segundos=tempo,
        iniciada_em=dt.utcnow()
    )
    db.add(sessao)
    e.status = "ocupada"
    db.commit()
    db.refresh(sessao)
    registrar(db, operador, "liberar_direto", cliente=cliente, estacao=nome)
    db.refresh(cliente)

    # Whitelist: os apps ligados no piso da estacao
    from app.models import ConfiguracaoSistema
    from app.pisos import apps_do_piso, whitelist_para_o_agente
    apps = apps_do_piso(db, piso_da_estacao(e))

    cfg_reiniciar = db.query(ConfiguracaoSistema).filter(
        ConfiguracaoSistema.chave == "reiniciar_ao_encerrar").first()
    reiniciar = cfg_reiniciar.valor == "true" if cfg_reiniciar else False

    payload = {
        "ok": True,
        "piso": cor_para_o_agente(e),
        "sessao_id": sessao.id,
        "cliente_nome": cliente.nome,
        "cliente_login": cliente.login,
        "tempo_segundos": tempo,
        "reiniciar_ao_encerrar": reiniciar,
        "whitelist": whitelist_para_o_agente(apps),
    }
    await manager.enviar_estacao(e.id, "iniciar_sessao_direta", payload)
    await manager.broadcast_paineis("estacao_atualizada", {"nome": nome, "estacao_id": e.id})

    return {"ok": True, "sessao_id": sessao.id}


@router.post("/{nome}/iniciar_streaming")
async def iniciar_streaming(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                            _=Depends(requer_perfil("admin", "operador"))):
    e = _estacao_online(db, nome, id)
    await manager.enviar_estacao(e.id, "iniciar_streaming", {})
    return {"ok": True}


@router.post("/{nome}/parar_streaming")
async def parar_streaming(nome: str, id: Optional[int] = None, db: Session = Depends(get_db),
                          _=Depends(requer_perfil("admin", "operador"))):
    e = achar_estacao(db, nome, id)
    if manager.estacao_conectada(e.id):
        await manager.enviar_estacao(e.id, "parar_streaming", {})
    return {"ok": True}

