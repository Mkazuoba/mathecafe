"""Registro das acoes dos operadores (8.1): quem fez o que, com qual cliente e
em qual estacao. Consultado em Historicos -> Acoes dos operadores."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AcaoOperador, Usuario

ROTULOS = {
    "criar_cliente": "Cadastrou cliente",
    "editar_cliente": "Editou cadastro",
    "excluir_cliente": "Excluiu cliente",
    "ativar_cliente": "Ativou cliente",
    "desativar_cliente": "Desativou cliente",
    "senha_cliente": "Trocou a senha do cliente",
    "trocar_piso": "Trocou o piso",
    "tempo_extra": "Mudou o tempo de hoje",
    "liberar": "Liberou (fila)",
    "tirar_da_fila": "Tirou da fila",
    "liberar_direto": "Liberou direto no PC",
    "encerrar_sessao": "Encerrou a sessão",
    "pausar_sessao": "Pausou a sessão",
    "retomar_sessao": "Retomou a sessão",
    "mais_tempo_sessao": "Deu mais tempo na sessão",
    "mensagem": "Mandou mensagem",
    "reiniciar_pc": "Reiniciou o PC",
    "desligar_pc": "Desligou o PC",
    "ligar_pc": "Ligou o PC",
    "manutencao": "Manutenção",
    "zerar_tempo_dia": "Zerou o tempo do dia",
    "horario": "Mudou o horário de funcionamento",
    "configuracao": "Mudou as configurações",
    "reiniciar_servidor": "Reiniciou o servidor",
    "aprovar_estacao": "Aprovou estação nova",
    "recusar_estacao": "Recusou estação nova",
    "renomear_estacao": "Renomeou estação",
    "substituir_estacao": "Substituiu o computador da estação",
    "excluir_estacao": "Excluiu estação",
    "atualizar_agente": "Atualizou o agente",
    "criar_operador": "Cadastrou operador",
    "editar_operador": "Editou operador",
    "excluir_operador": "Excluiu operador",
}


def registrar(db: Session, quem: dict, acao: str, cliente: Optional[Usuario] = None,
              estacao: Optional[str] = None, detalhe: Optional[str] = None):
    """Grava a acao (e faz o commit). `quem` e o usuario do token (requer_perfil)."""
    operador_id = int(quem["sub"]) if quem and quem.get("sub") else None
    operador = db.get(Usuario, operador_id) if operador_id else None
    db.add(AcaoOperador(
        quando=datetime.utcnow(),
        operador_id=operador_id,
        operador_nome=(operador.nome if operador else quem.get("nome")) or "?",
        acao=acao,
        cliente_id=cliente.id if cliente else None,
        cliente_login=cliente.login if cliente else None,
        cliente_nome=cliente.nome if cliente else None,
        estacao=estacao,
        detalhe=detalhe,
    ))
    db.commit()
