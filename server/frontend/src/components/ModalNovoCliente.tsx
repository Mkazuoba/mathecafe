import { useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { lerTempo } from "@/lib/tempo"
import type { Cliente } from "@/lib/tipos"
import { Button } from "@/components/ui/button"
import { Campo, Input, MensagemErro, Textarea } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"

/** Cadastro de cliente (aba Clientes e Painel). Ao criar, quem chamou abre a ficha. */
export function ModalNovoCliente({ aberto, aoFechar, aoCriar }: {
  aberto: boolean
  aoFechar: () => void
  aoCriar: (c: Cliente) => void
}) {
  const avisar = useAvisos()
  const { recarregarClientes } = useDados()
  const [login, setLogin] = useState("")
  const [nome, setNome] = useState("")
  const [senha, setSenha] = useState("")
  const [documento, setDocumento] = useState("")
  const [nascimento, setNascimento] = useState("")
  const [saldo, setSaldo] = useState("")
  const [obs, setObs] = useState("")
  const [erro, setErro] = useState("")
  const [estavaAberto, setEstavaAberto] = useState(false)

  // Limpa o formulário a cada abertura
  if (aberto !== estavaAberto) {
    setEstavaAberto(aberto)
    if (aberto) {
      setLogin("")
      setNome("")
      setSenha("")
      setDocumento("")
      setNascimento("")
      setSaldo("")
      setObs("")
      setErro("")
    }
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    setErro("")
    if (!login.trim() || !nome.trim()) return setErro("Preencha login e nome")
    if (!senha) return setErro("Senha obrigatória para novo cliente")
    const saldoSegundos = saldo.trim() ? lerTempo(saldo) : 0
    if (saldoSegundos === null) return setErro("Tempo extra no formato HH:MM:SS")
    try {
      let criado = await Api.post<Cliente>("/api/clientes/", {
        login: login.trim(),
        nome: nome.trim(),
        senha,
        documento: documento.trim() || null,
        data_nascimento: nascimento || null,
        observacao: obs.trim() || null,
      })
      if (saldoSegundos > 0) criado = await Api.put<Cliente>(`/api/clientes/${criado.id}`, { saldo_segundos: saldoSegundos })
      avisar("Cliente criado")
      await recarregarClientes()
      aoCriar(criado)
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo="Novo cliente" aberto={aberto} aoFechar={aoFechar} className="max-w-lg">
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Campo rotulo="Login" id="cli-login">
            <Input id="cli-login" autoComplete="off" value={login} onChange={(e) => setLogin(e.target.value)} />
          </Campo>
          <Campo rotulo="Senha" id="cli-senha">
            <Input id="cli-senha" type="password" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} />
          </Campo>
        </div>
        <Campo rotulo="Nome" id="cli-nome">
          <Input id="cli-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Campo rotulo="Documento (CPF/RG)" id="cli-doc">
            <Input id="cli-doc" autoComplete="off" placeholder="Opcional" value={documento} onChange={(e) => setDocumento(e.target.value)} />
          </Campo>
          <Campo rotulo="Data de nascimento" id="cli-nasc">
            <Input id="cli-nasc" type="date" value={nascimento} onChange={(e) => setNascimento(e.target.value)} />
          </Campo>
        </div>
        <Campo rotulo="Tempo de hoje (HH:MM:SS)" id="cli-saldo">
          <Input id="cli-saldo" placeholder="Em branco: o tempo do dia cheio" value={saldo} onChange={(e) => setSaldo(e.target.value)} />
        </Campo>
        <Campo rotulo="Observações" id="cli-obs">
          <Textarea id="cli-obs" rows={2} value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={aoFechar}>
            Cancelar
          </Button>
          <Button type="submit" className="flex-1">
            Criar e abrir a ficha
          </Button>
        </div>
      </form>
    </Modal>
  )
}
