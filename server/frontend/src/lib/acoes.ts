import { useCallback } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo } from "@/lib/tempo"

/** Ações do operador usadas em mais de uma tela. */
export function useAcoes() {
  const avisar = useAvisos()
  const { recarregar, recarregarFila, recarregarClientes, estacoes } = useDados()
  // O painel mostra um piso por vez, onde o nome é único; a API recebe o id
  // (AD-01 pode existir no Adulto e no Infantil).
  const rota = (nome: string, acao: string) => {
    const id = estacoes.find((e) => e.nome === nome)?.id
    return `/api/estacoes/${encodeURIComponent(nome)}/${acao}${id != null ? `?id=${id}` : ""}`
  }

  const liberar = useCallback(
    async (clienteId: number) => {
      try {
        await Api.post(`/api/estacoes/fila/${clienteId}`)
        avisar("Cliente adicionado à fila")
        await Promise.all([recarregarFila(), recarregarClientes()])
      } catch (e) {
        avisar((e as Error).message, "erro")
      }
    },
    [avisar, recarregarFila, recarregarClientes],
  )

  const removerDaFila = useCallback(
    async (clienteId: number) => {
      try {
        await Api.del(`/api/estacoes/fila/${clienteId}`)
        avisar("Removido da fila")
        await Promise.all([recarregarFila(), recarregarClientes()])
      } catch (e) {
        avisar((e as Error).message, "erro")
      }
    },
    [avisar, recarregarFila, recarregarClientes],
  )

  const encerrarSessao = useCallback(
    async (sessaoId: number, estacao: string) => {
      if (!window.confirm(`Encerrar a sessão da estação ${estacao}?`)) return false
      try {
        const r = await Api.post<{ saldo_restante: number }>(`/api/sessoes/encerrar/${sessaoId}`)
        avisar(
          r.saldo_restante > 0
            ? `Sessão encerrada. Saldo devolvido: ${formatarTempo(r.saldo_restante)}`
            : "Sessão encerrada",
        )
        await recarregar()
        return true
      } catch (e) {
        avisar((e as Error).message, "erro")
        return false
      }
    },
    [avisar, recarregar],
  )

  const reiniciarPc = useCallback(
    async (nomeEstacao: string) => {
      if (!window.confirm(`Reiniciar o PC da estacao ${nomeEstacao}?`)) return
      try {
        await Api.post(rota(nomeEstacao, "reiniciar"))
        avisar(`Comando de reinicio enviado para ${nomeEstacao}`)
      } catch (e) {
        avisar((e as Error).message, "erro")
      }
    },
    [avisar, estacoes],
  )

  const desligarPc = useCallback(
    async (nomeEstacao: string) => {
      if (!window.confirm(`Desligar o PC da estação ${nomeEstacao}? Se houver cliente, a sessão é encerrada e o tempo que sobrou volta para ele.`)) return
      try {
        await Api.post(rota(nomeEstacao, "desligar"))
        avisar(`${nomeEstacao} desliga em 10 segundos`)
        await recarregar()
      } catch (e) {
        avisar((e as Error).message, "erro")
      }
    },
    [avisar, recarregar, estacoes],
  )

  const enviarMensagem = useCallback(
    async (nomeEstacao: string, texto: string) => {
      try {
        await Api.post(rota(nomeEstacao, "mensagem"), { texto })
        avisar("Mensagem enviada")
      } catch (e) {
        avisar((e as Error).message, "erro")
      }
    },
    [avisar, estacoes],
  )

  const alternarManutencao = useCallback(
    async (nomeEstacao: string) => {
      try {
        await Api.post(rota(nomeEstacao, "manutencao"))
        avisar("Modo manutencao alternado")
        await recarregar()
      } catch (e) {
        avisar((e as Error).message, "erro")
      }
    },
    [avisar, recarregar, estacoes],
  )

  const liberarDireto = useCallback(
    async (nomeEstacao: string, clienteId: number) => {
      try {
        await Api.post(rota(nomeEstacao, "iniciar_direto"), { cliente_id: clienteId })
        avisar(`Cliente liberado diretamente para ${nomeEstacao}`)
        await recarregar()
        return true
      } catch (e) {
        avisar((e as Error).message, "erro")
        return false
      }
    },
    [avisar, recarregar, estacoes],
  )

  return { liberar, removerDaFila, encerrarSessao, reiniciarPc, desligarPc, enviarMensagem, alternarManutencao, liberarDireto }
}
