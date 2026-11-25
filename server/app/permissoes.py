"""Grupos de operadores: o admin marca, por grupo, quais areas que eram so dele
os operadores do grupo tambem usam. O admin pode tudo. A permissao e lida do
banco a cada pedido: mudar o grupo vale na hora, sem sair e entrar de novo."""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GrupoOperadores, Usuario
from app.security import get_usuario_atual

PERMISSOES = {
    "divulgacao": "Programação e avisos",
    "relatorios": "Relatórios de uso e registro de ações",
}


def ler(texto) -> list:
    return [p for p in (texto or "").split(",") if p in PERMISSOES]


def do_usuario(db: Session, usuario_id) -> list:
    """Chaves que o usuario tem (todas para o admin; nenhuma se inativo)."""
    u = db.get(Usuario, int(usuario_id)) if usuario_id else None
    if not u or not u.ativo:
        return []
    if u.perfil == "admin":
        return list(PERMISSOES)
    if u.perfil != "operador" or not u.grupo_operadores_id:
        return []
    grupo = db.get(GrupoOperadores, u.grupo_operadores_id)
    return ler(grupo.permissoes) if grupo else []


def requer_permissao(chave: str):
    def verificar(usuario=Depends(get_usuario_atual), db: Session = Depends(get_db)):
        if chave not in do_usuario(db, usuario.get("sub")):
            raise HTTPException(status_code=403, detail="Sem permissão")
        return usuario
    return verificar


# ── Pisos do grupo: o operador so ve e mexe nas estacoes, sessoes e fila deles ──
def ler_pisos(texto) -> list:
    return [int(p) for p in (texto or "").split(",") if p.strip().isdigit()]


def pisos_do_usuario(db: Session, usuario_id):
    """Ids dos pisos que o usuario ve, ou None para todos (admin, operador sem
    grupo ou grupo sem pisos marcados)."""
    u = db.get(Usuario, int(usuario_id)) if usuario_id else None
    if not u or u.perfil != "operador" or not u.grupo_operadores_id:
        return None
    grupo = db.get(GrupoOperadores, u.grupo_operadores_id)
    pisos = ler_pisos(grupo.pisos) if grupo else []
    return set(pisos) or None


def ve_piso(pisos, piso) -> bool:
    """pisos: o de pisos_do_usuario; piso: objeto Piso (ou None)."""
    return pisos is None or (piso is not None and piso.id in pisos)


def ve_estacao(db: Session, quem: dict, estacao) -> bool:
    from app.pisos import piso_da_estacao
    return ve_piso(pisos_do_usuario(db, (quem or {}).get("sub")), piso_da_estacao(estacao))


def conferir_estacao(db: Session, quem: dict, estacao):
    if not ve_estacao(db, quem, estacao):
        raise HTTPException(status_code=403, detail="Esta estação é de um piso fora do seu grupo")
    return estacao


def conferir_cliente(db: Session, quem: dict, cliente):
    from app.pisos import piso_do_cliente
    if not ve_piso(pisos_do_usuario(db, (quem or {}).get("sub")), piso_do_cliente(cliente)):
        raise HTTPException(status_code=403, detail="Este cliente é de um piso fora do seu grupo")
    return cliente
