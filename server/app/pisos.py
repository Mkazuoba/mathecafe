"""Pisos da biblioteca (4.7): cadastrados pelo admin (tabela pisos).

Cada mapa (grupo de estacoes) e cada cliente pertence a um piso, e o cliente so
entra nos PCs do proprio piso. Um piso e o padrao: vale para estacao sem grupo,
grupo antigo ainda sem piso e cliente cadastrado sem escolher.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, object_session

from app.models import AppPermitido, AppPiso, ConfiguracaoSistema, GrupoEstacao, Piso, Usuario

# Criados na primeira subida (e os do 4.7a, que eram texto, viram estes)
PISOS_INICIAIS = [("Adulto", "#6366f1", True), ("Infantil", "#ec4899", False)]


def piso_padrao(db: Session) -> Piso:
    return db.query(Piso).filter(Piso.padrao == True).first() or db.query(Piso).order_by(Piso.id).first()


def piso_da_estacao(estacao) -> Optional[Piso]:
    grupo = estacao.grupo
    if grupo is not None and grupo.piso is not None:
        return grupo.piso
    return piso_padrao(object_session(estacao))


def piso_do_cliente(cliente) -> Optional[Piso]:
    return cliente.piso if cliente.piso is not None else piso_padrao(object_session(cliente))


def recusa_de_piso(cliente, estacao) -> Optional[str]:
    """Motivo para recusar o cliente nesta estacao, ou None se o piso bate."""
    do_cliente, da_estacao = piso_do_cliente(cliente), piso_da_estacao(estacao)
    if do_cliente is None or da_estacao is None or do_cliente.id == da_estacao.id:
        return None
    return (f"Este cadastro é do piso {do_cliente.nome} e este computador é do piso "
            f"{da_estacao.nome}. Procure o atendimento.")


def resumo(piso: Optional[Piso]) -> dict:
    """Campos de piso que vao junto de clientes, estacoes e grupos na API."""
    return {"piso_id": piso.id if piso else None, "piso_nome": piso.nome if piso else None,
            "piso_cor": piso.cor if piso else None}


def cor_para_o_agente(estacao) -> dict:
    """Piso da estacao como o agente usa (cor de destaque da tela, 9.4)."""
    piso = piso_da_estacao(estacao)
    return {"nome": piso.nome, "cor": piso.cor} if piso else {}


def _colunas(db: Session, tabela: str) -> set:
    if db.get_bind().dialect.name != "sqlite":
        return set()
    return {linha[1] for linha in db.execute(text(f"PRAGMA table_info({tabela})"))}


def garantir_pisos(db: Session):
    """Na subida: cria Adulto (padrao) e Infantil se nao houver nenhum piso, passa
    os pisos que eram texto (4.7a) para piso_id e da a todo cliente sem piso o
    padrao (gravado, para trocar o padrao depois nao mover ninguem)."""
    if db.query(Piso).count() == 0:
        for nome, cor, padrao in PISOS_INICIAIS:
            db.add(Piso(nome=nome, cor=cor, padrao=padrao))
        db.flush()
    por_nome = {p.nome.lower(): p.id for p in db.query(Piso)}
    for tabela in ("usuarios", "grupos_estacao"):
        if "piso" in _colunas(db, tabela):  # coluna de texto do 4.7a
            for nome, pid in por_nome.items():
                db.execute(text(f"UPDATE {tabela} SET piso_id = :pid WHERE piso_id IS NULL AND lower(piso) = :nome"),
                           {"pid": pid, "nome": nome})
    padrao = piso_padrao(db)
    db.query(Usuario).filter(Usuario.perfil == "cliente", Usuario.piso_id == None).update(
        {Usuario.piso_id: padrao.id}, synchronize_session=False)
    # o grupo "Padrao" criado sozinho pelo sistema ja nasce com piso
    db.query(GrupoEstacao).filter(GrupoEstacao.nome == "Padrao", GrupoEstacao.piso_id == None).update(
        {GrupoEstacao.piso_id: padrao.id}, synchronize_session=False)


# ── Apps por piso ────────────────────────────────────────────────────────────

CHAVE_APPS_POR_PISO = "apps_por_piso"


def apps_do_piso(db: Session, piso) -> list:
    """Os apps ligados neste piso (o que vai para o agente)."""
    if piso is None:
        return []
    return (db.query(AppPermitido).join(AppPiso, AppPiso.app_id == AppPermitido.id)
            .filter(AppPiso.piso_id == piso.id).order_by(AppPermitido.nome).all())


def whitelist_para_o_agente(apps) -> list:
    """Os apps como o agente recebe no inicio da sessao (login e liberar direto).
    categoria/categoria_ordem: o filtro da tela de apps (None = "Outros")."""
    return [
        {
            "nome": a.nome,
            "processo": a.processo,
            "caminho": a.caminho,
            "imagem_url": a.imagem_url,
            "categoria": a.categoria.nome if a.categoria else None,
            "categoria_ordem": a.categoria.ordem if a.categoria else None,
        }
        for a in apps
    ]


def migrar_apps_para_pisos(db: Session, forcar: bool = False):
    """Uma vez so: o app que valia em todos os mapas fica ligado em todos os
    pisos; o de um mapa, no piso desse mapa; o desligado, em nenhum. Depois
    disso quem decide e a tela de apps (por isso nao roda de novo)."""
    feito = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave == CHAVE_APPS_POR_PISO).first()
    if feito and not forcar:
        return
    pisos = db.query(Piso).all()
    padrao = piso_padrao(db)
    ja = {a for (a,) in db.query(AppPiso.app_id).distinct()}
    for app in db.query(AppPermitido).all():
        if app.id in ja or not app.ativo:
            continue
        if app.grupo_id is None:
            alvos = pisos
        else:
            grupo = db.get(GrupoEstacao, app.grupo_id)
            alvos = [grupo.piso if grupo and grupo.piso else padrao]
        for piso in alvos:
            if piso:
                db.add(AppPiso(app_id=app.id, piso_id=piso.id))
    if not feito:
        db.add(ConfiguracaoSistema(chave=CHAVE_APPS_POR_PISO, valor="feito"))
    db.flush()
