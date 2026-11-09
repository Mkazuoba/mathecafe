import { useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { EtiquetaPiso, textoIdade } from "@/lib/piso"
import type { Cliente } from "@/lib/tipos"
import { Button } from "@/components/ui/button"
import { Campo, Input, InputData, MensagemErro, Textarea, hojeIso, soRg } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { PainelFoto } from "@/components/QuadroFoto"

/**
 * Cadastro de cliente (aba Clientes e Painel), no mesmo formato da ficha: a foto
 * à esquerda (vai junto ao criar) e os dados à direita. Ao criar, quem chamou
 * abre a ficha.
 */
export function ModalNovoCliente({
  aberto,
  aoFechar,
  aoCriar,
}: {
  aberto: boolean
  aoFechar: () => void
  aoCriar: (c: Cliente) => void
}) {
  const avisar = useAvisos()
  const { recarregarClientes, piso } = useDados()
  const [login, setLogin] = useState("")
  const [nome, setNome] = useState("")
  const [senha, setSenha] = useState("")
  const [documento, setDocumento] = useState("")
  const [email, setEmail] = useState("")
  const [nascimento, setNascimento] = useState("")
  const [obs, setObs] = useState("")
  /** foto já ajustada (data URL), enviada depois de criar o cliente */
  const [foto, setFoto] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
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
      setEmail("")
      setNascimento("")
      setObs("")
      setFoto(null)
      setErro("")
    }
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    setErro("")
    if (!login.trim() || !nome.trim()) return setErro("Preencha login e nome")
    if (!senha) return setErro("Senha obrigatória para novo cliente")
    setSalvando(true)
    try {
      let criado = await Api.post<Cliente>("/api/clientes/", {
        login: login.trim(),
        nome: nome.trim(),
        senha,
        documento: documento.trim() || null,
        email: email.trim() || null,
        data_nascimento: nascimento || null,
        observacao: obs.trim() || null,
        piso_id: piso?.id, // nasce no piso escolhido no cabeçalho
      })
      if (foto) {
        try {
          criado = await Api.put<Cliente>(`/api/clientes/${criado.id}/foto`, { imagem: foto })
        } catch (e) {
          // o cliente já existe: avisa e segue para a ficha, onde dá para tentar de novo
          avisar(`Cliente criado, mas a foto não foi salva: ${(e as Error).message}`, "erro")
        }
      }
      avisar("Cliente criado")
      await recarregarClientes()
      aoCriar(criado)
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setSalvando(false)
    }
  }

  return (
    <Modal titulo="Novo cliente" aberto={aberto} aoFechar={aoFechar} className="max-w-2xl">
      <p className="-mt-1 mb-4 flex items-center gap-2 text-sm text-texto-suave">
        Cadastro no piso <EtiquetaPiso nome={piso?.nome ?? null} cor={piso?.cor ?? null} className="text-xs" />
        <span className="text-texto-fraco">(troque no topo da tela, se for o caso)</span>
      </p>
      <div className="flex flex-col gap-6 sm:flex-row">
        <PainelFoto url={foto} alt="Foto do cliente novo" aoEscolher={setFoto} aoRemover={() => setFoto(null)} />
        <form onSubmit={salvar} className="flex min-w-0 flex-1 flex-col gap-3.5">
          <Campo rotulo="Nome" id="cli-nome">
            <Input id="cli-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
          </Campo>
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            <Campo rotulo="Login" id="cli-login">
              <Input id="cli-login" autoComplete="off" value={login} onChange={(e) => setLogin(e.target.value)} />
            </Campo>
            <Campo rotulo="Senha" id="cli-senha">
              <Input
                id="cli-senha"
                type="password"
                autoComplete="new-password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
              />
            </Campo>
            <Campo rotulo="Documento (CPF/RG)" id="cli-doc">
              <Input
                id="cli-doc"
                autoComplete="off"
                placeholder="Opcional"
                value={documento}
                onChange={(e) => setDocumento(soRg(e.target.value))}
              />
            </Campo>
            <Campo rotulo="E-mail" id="cli-email">
              <Input
                id="cli-email"
                type="email"
                autoComplete="off"
                placeholder="Opcional"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Campo>
            <Campo rotulo="Data de nascimento" id="cli-nasc">
              <InputData id="cli-nasc" min="1900-01-01" max={hojeIso()} value={nascimento} onChange={setNascimento} />
            </Campo>
            <div className="flex flex-col justify-end pb-2 text-sm text-texto-suave">
              {textoIdade(nascimento || null) ?? ""}
            </div>
          </div>
          <Campo rotulo="Observações" id="cli-obs">
            <Textarea id="cli-obs" rows={2} value={obs} onChange={(e) => setObs(e.target.value)} />
          </Campo>
          <MensagemErro>{erro}</MensagemErro>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={aoFechar}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={salvando}>
              {salvando ? "Criando..." : "Criar e abrir a ficha"}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  )
}
