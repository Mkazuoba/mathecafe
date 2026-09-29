import { useCallback } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo } from "@/lib/tempo"

/** Ações do operador usadas em mais de uma tela. */
export function useAcoes() {
  const avisar = useAvisos()
  const { recarregar, recarregarFila, recarregarClientes } = useDados()

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

  return { liberar, removerDaFila, encerrarSessao }
}
