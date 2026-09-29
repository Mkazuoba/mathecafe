import { useEffect, useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo, lerTempo } from "@/lib/tempo"
import type { Cliente } from "@/lib/tipos"
import { Button } from "@/components/ui/button"
import { Campo, Input, MensagemErro } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"

/** Edição rápida do saldo de tempo de um cliente (HH:MM:SS). */
export function ModalSaldo({ cliente, aoFechar }: { cliente: Cliente | null; aoFechar: () => void }) {
  const avisar = useAvisos()
  const { recarregarClientes, recarregarFila } = useDados()
  const [valor, setValor] = useState("")
  const [erro, setErro] = useState("")

  useEffect(() => {
    if (cliente) {
      setValor(formatarTempo(cliente.saldo_segundos))
      setErro("")
    }
  }, [cliente])

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    const segundos = lerTempo(valor)
    if (segundos === null) {
      setErro("Use o formato HH:MM:SS, por exemplo 01:30:00")
      return
    }
    try {
      await Api.put(`/api/clientes/${cliente!.id}`, { saldo_segundos: segundos })
      avisar("Saldo atualizado")
      aoFechar()
      await Promise.all([recarregarClientes(), recarregarFila()])
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo={`Saldo de ${cliente?.nome ?? ""}`} aberto={!!cliente} aoFechar={aoFechar} className="max-w-[300px]">
      <form onSubmit={salvar} className="flex flex-col gap-3">
        <Campo rotulo="Saldo (HH:MM:SS)" id="saldo-rapido">
          <Input id="saldo-rapido" value={valor} onChange={(e) => setValor(e.target.value)} autoFocus />
        </Campo>
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={aoFechar}>
            Cancelar
          </Button>
          <Button type="submit" className="flex-1">
            Salvar
          </Button>
        </div>
      </form>
    </Modal>
  )
}
