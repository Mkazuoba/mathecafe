import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { IconCamera, IconInfoCircle, IconHistory, IconLock, IconPencil, IconTrash, IconUser } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { dataDoServidor, formatarTempo } from "@/lib/tempo"
import type { Cliente } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { ModalSaldo } from "@/components/ModalSaldo"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor, MensagemErro, Textarea } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { SeloAtivo, Vazio } from "@/components/ui/status"

type Aba = "geral" | "historico" | "seguranca"

const ABAS: { id: Aba; rotulo: string; Icone: typeof IconInfoCircle }[] = [
  { id: "geral", rotulo: "Geral", Icone: IconInfoCircle },
  { id: "historico", rotulo: "Histórico", Icone: IconHistory },
  { id: "seguranca", rotulo: "Segurança", Icone: IconLock },
]

/**
 * Ficha do cliente: dados, foto, histórico e segurança numa janela só.
 * Recebe o id e busca o cliente atualizado (a lista pode estar velha).
 */
export function FichaCliente({ clienteId, aoFechar, abaInicial = "geral" }: {
  clienteId: number | null
  aoFechar: () => void
  abaInicial?: Aba
}) {
  const [cliente, setCliente] = useState<Cliente | null>(null)
  const [aba, setAba] = useState<Aba>(abaInicial)
  const [erro, setErro] = useState("")
  const { recarregarClientes } = useDados()

  useEffect(() => {
    setCliente(null)
    setErro("")
    setAba(abaInicial)
    if (clienteId == null) return
    Api.get<Cliente>(`/api/clientes/${clienteId}`)
      .then(setCliente)
      .catch((e) => setErro((e as Error).message))
  }, [clienteId, abaInicial])

  /** Depois de salvar algo: atualiza a ficha e as listas abertas. */
  function atualizado(c: Cliente) {
    setCliente(c)
    recarregarClientes()
  }

  return (
    <Modal titulo="Ficha do cliente" aberto={clienteId != null} aoFechar={aoFechar} className="max-w-2xl">
      {!cliente ? (
        erro ? <MensagemErro>{erro}</MensagemErro> : <Vazio>Carregando...</Vazio>
      ) : (
        <>
          <div className="-mt-1 mb-4 flex items-center gap-3">
            <FotoCliente cliente={cliente} tamanho="pequena" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-base font-semibold">{cliente.nome}</span>
                <SeloAtivo ativo={cliente.ativo} />
              </div>
              <div className="text-sm text-texto-fraco">{cliente.login}</div>
            </div>
          </div>

          <div role="tablist" className="mb-5 flex gap-1 border-b border-borda">
            {ABAS.map(({ id, rotulo, Icone }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={aba === id}
                onClick={() => setAba(id)}
                className={cn(
                  "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
                  aba === id ? "border-destaque text-texto" : "border-transparent text-texto-suave hover:text-texto",
                )}
              >
                <Icone size={15} /> {rotulo}
              </button>
            ))}
          </div>

          {/* altura fixa: a janela não pula ao trocar de aba */}
          <div className="min-h-[23rem]">
            {aba === "geral" && <AbaGeral cliente={cliente} aoSalvar={atualizado} />}
            {aba === "historico" && <AbaHistorico cliente={cliente} />}
            {aba === "seguranca" && <AbaSeguranca cliente={cliente} aoSalvar={atualizado} aoExcluir={aoFechar} />}
          </div>
        </>
      )}
    </Modal>
  )
}

// ── Foto ─────────────────────────────────────────────────────────────────────

const LADO_MAXIMO = 480 // px: a foto é reduzida no navegador antes de ir ao servidor

/** Reduz a imagem escolhida e devolve um JPEG em data URL. */
function reduzirImagem(arquivo: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(arquivo)
    const img = new Image()
    img.onload = () => {
      const escala = Math.min(1, LADO_MAXIMO / Math.max(img.width, img.height))
      const canvas = document.createElement("canvas")
      canvas.width = Math.round(img.width * escala)
      canvas.height = Math.round(img.height * escala)
      canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      resolve(canvas.toDataURL("image/jpeg", 0.85))
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error("Não foi possível abrir essa imagem"))
    }
    img.src = url
  })
}

/** A foto vem com o token (uma <img src> não manda o login), então vira um blob local. */
function useFoto(cliente: Cliente) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!cliente.tem_foto) {
      setUrl(null)
      return
    }
    let objeto: string | null = null
    let cancelado = false
    fetch(`/api/clientes/${cliente.id}/foto?v=${encodeURIComponent(cliente.foto_em ?? "")}`, {
      headers: { Authorization: `Bearer ${Api.token()}` },
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (b && !cancelado) {
          objeto = URL.createObjectURL(b)
          setUrl(objeto)
        }
      })
      .catch(() => setUrl(null))
    return () => {
      cancelado = true
      if (objeto) URL.revokeObjectURL(objeto)
    }
  }, [cliente.id, cliente.tem_foto, cliente.foto_em])
  return url
}

function FotoCliente({ cliente, tamanho }: { cliente: Cliente; tamanho: "pequena" | "grande" }) {
  const url = useFoto(cliente)
  const classe = tamanho === "grande" ? "size-40 rounded-xl" : "size-12 rounded-full"
  return url ? (
    <img src={url} alt={`Foto de ${cliente.nome}`} className={cn(classe, "shrink-0 border border-borda object-cover")} />
  ) : (
    <div className={cn(classe, "flex shrink-0 items-center justify-center border border-dashed border-borda bg-superficie-2 text-texto-fraco")}>
      <IconUser size={tamanho === "grande" ? 56 : 22} stroke={1.4} />
    </div>
  )
}

function EditorFoto({ cliente, aoSalvar }: { cliente: Cliente; aoSalvar: (c: Cliente) => void }) {
  const avisar = useAvisos()
  const entrada = useRef<HTMLInputElement>(null)
  const [enviando, setEnviando] = useState(false)

  async function escolher(ev: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = ev.target.files?.[0]
    ev.target.value = "" // permite escolher o mesmo arquivo de novo
    if (!arquivo) return
    setEnviando(true)
    try {
      const imagem = await reduzirImagem(arquivo)
      aoSalvar(await Api.put<Cliente>(`/api/clientes/${cliente.id}/foto`, { imagem }))
      avisar("Foto salva")
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setEnviando(false)
    }
  }

  async function remover() {
    if (!window.confirm(`Remover a foto de ${cliente.nome}?`)) return
    try {
      aoSalvar(await Api.del<Cliente>(`/api/clientes/${cliente.id}/foto`))
      avisar("Foto removida")
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <FotoCliente cliente={cliente} tamanho="grande" />
      <input ref={entrada} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={escolher} />
      <Button type="button" variant="outline" size="sm" className="w-40 gap-1.5" disabled={enviando} onClick={() => entrada.current?.click()}>
        <IconCamera size={14} /> {enviando ? "Enviando..." : cliente.tem_foto ? "Trocar foto" : "Enviar foto"}
      </Button>
      {cliente.tem_foto && (
        <button type="button" onClick={remover} className="text-xs text-texto-fraco hover:text-perigo">
          Remover foto
        </button>
      )}
    </div>
  )
}

// ── Aba Geral ────────────────────────────────────────────────────────────────

function idade(nascimento: string): number {
  const [a, m, d] = nascimento.split("-").map(Number)
  const hoje = new Date()
  let anos = hoje.getFullYear() - a
  if (hoje.getMonth() + 1 < m || (hoje.getMonth() + 1 === m && hoje.getDate() < d)) anos--
  return anos
}

function AbaGeral({ cliente, aoSalvar }: { cliente: Cliente; aoSalvar: (c: Cliente) => void }) {
  const avisar = useAvisos()
  const [nome, setNome] = useState(cliente.nome)
  const [documento, setDocumento] = useState(cliente.documento ?? "")
  const [nascimento, setNascimento] = useState(cliente.data_nascimento ?? "")
  const [obs, setObs] = useState(cliente.observacao ?? "")
  const [erro, setErro] = useState("")
  const [salvando, setSalvando] = useState(false)
  const [editandoTempo, setEditandoTempo] = useState(false)

  const alterado =
    nome.trim() !== cliente.nome ||
    documento.trim() !== (cliente.documento ?? "") ||
    nascimento !== (cliente.data_nascimento ?? "") ||
    obs.trim() !== (cliente.observacao ?? "")

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return setErro("O nome não pode ficar vazio")
    setErro("")
    setSalvando(true)
    try {
      aoSalvar(
        await Api.put<Cliente>(`/api/clientes/${cliente.id}`, {
          nome: nome.trim(),
          documento: documento.trim(),
          data_nascimento: nascimento || null,
          observacao: obs.trim(),
        }),
      )
      avisar("Dados salvos")
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 sm:flex-row">
      <EditorFoto cliente={cliente} aoSalvar={aoSalvar} />
      <form onSubmit={salvar} className="flex min-w-0 flex-1 flex-col gap-3.5">
        <Campo rotulo="Nome" id="ficha-nome">
          <Input id="ficha-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          <Campo rotulo="Login" id="ficha-login">
            <Input id="ficha-login" value={cliente.login} disabled />
          </Campo>
          <Campo rotulo="Documento (CPF/RG)" id="ficha-doc">
            <Input id="ficha-doc" autoComplete="off" value={documento} onChange={(e) => setDocumento(e.target.value)} />
          </Campo>
          <Campo rotulo="Data de nascimento" id="ficha-nasc">
            <Input id="ficha-nasc" type="date" value={nascimento} onChange={(e) => setNascimento(e.target.value)} />
          </Campo>
          <div className="flex flex-col justify-end pb-2 text-sm text-texto-suave">
            {nascimento ? `${idade(nascimento)} anos` : ""}
          </div>
        </div>
        <Campo rotulo="Observações" id="ficha-obs">
          <Textarea id="ficha-obs" rows={2} value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>

        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-md bg-superficie-2 px-3 py-2">
            <dt className="text-xs text-texto-fraco">Tempo de hoje</dt>
            <dd className="flex items-center gap-1.5 font-semibold tabular-nums">
              {formatarTempo(cliente.saldo_segundos)}
              <button type="button" title="Dar tempo extra" onClick={() => setEditandoTempo(true)} className="text-texto-fraco hover:text-texto">
                <IconPencil size={13} />
              </button>
            </dd>
          </div>
          <div className="rounded-md bg-superficie-2 px-3 py-2">
            <dt className="text-xs text-texto-fraco">Cadastrado em</dt>
            <dd className="font-semibold">{cliente.criado_em ? dataDoServidor(cliente.criado_em).toLocaleDateString("pt-BR") : "—"}</dd>
          </div>
        </dl>

        <MensagemErro>{erro}</MensagemErro>
        <Button type="submit" className="self-end" disabled={!alterado || salvando}>
          {salvando ? "Salvando..." : "Salvar dados"}
        </Button>
      </form>
      <ModalSaldo
        cliente={editandoTempo ? cliente : null}
        aoFechar={() => {
          setEditandoTempo(false)
          // o ModalSaldo salva por conta própria: busca o tempo novo
          Api.get<Cliente>(`/api/clientes/${cliente.id}`).then(aoSalvar).catch(() => {})
        }}
      />
    </div>
  )
}

// ── Aba Histórico ────────────────────────────────────────────────────────────

interface SessaoHistorico {
  id: number
  estacao_nome: string
  iniciada_em: string
  tempo_total_segundos: number
  tempo_consumido_segundos: number
  motivo_encerramento: string | null
}

const MOTIVOS: Record<string, string> = {
  cliente: "Cliente encerrou",
  tempo_esgotado: "Tempo esgotado",
  operador: "Operador",
  manutencao: "Manutenção",
  conexao_perdida: "Queda de conexão",
  servidor_desligado: "Servidor desligado",
}

function AbaHistorico({ cliente }: { cliente: Cliente }) {
  const [sessoes, setSessoes] = useState<SessaoHistorico[] | null>(null)
  const [erro, setErro] = useState("")

  useEffect(() => {
    Api.get<SessaoHistorico[]>(`/api/sessoes/historico?cliente_id=${cliente.id}&limit=50`)
      .then(setSessoes)
      .catch((e) => setErro((e as Error).message))
  }, [cliente.id])

  if (erro) return <MensagemErro>{erro}</MensagemErro>
  if (!sessoes) return <Vazio>Carregando...</Vazio>

  const total = sessoes.reduce((s, x) => s + (x.tempo_consumido_segundos ?? 0), 0)
  return (
    <div className="flex flex-col gap-3">
      {sessoes.length ? (
        <div className="max-h-80 overflow-auto rounded-md border border-borda">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="sticky top-0 bg-superficie text-left text-xs tracking-wide text-texto-fraco uppercase">
                {["Data", "Estação", "Usou", "Encerramento"].map((h) => (
                  <th key={h} className="border-b border-borda px-2.5 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sessoes.map((s) => (
                <tr key={s.id} className="hover:bg-superficie-2">
                  <td className="border-b border-borda px-2.5 py-2 text-texto-suave">
                    {dataDoServidor(s.iniciada_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                  <td className="border-b border-borda px-2.5 py-2 font-medium">{s.estacao_nome}</td>
                  <td className="border-b border-borda px-2.5 py-2 tabular-nums">{formatarTempo(s.tempo_consumido_segundos ?? 0)}</td>
                  <td className="border-b border-borda px-2.5 py-2 text-texto-fraco">
                    {s.motivo_encerramento ? (MOTIVOS[s.motivo_encerramento] ?? s.motivo_encerramento) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Vazio>Nenhuma sessão registrada.</Vazio>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="text-texto-fraco">
          {sessoes.length === 50 ? "Últimas 50 sessões" : `${sessoes.length} sessão(ões)`} · usou{" "}
          <span className="font-semibold tabular-nums text-texto">{formatarTempo(total)}</span>
        </span>
        <Link to={`/historicos?aba=cliente&cliente=${cliente.id}`} className="text-destaque hover:underline">
          Ver quais estações ele já usou →
        </Link>
      </div>
    </div>
  )
}

// ── Aba Segurança ────────────────────────────────────────────────────────────

function AbaSeguranca({ cliente, aoSalvar, aoExcluir }: {
  cliente: Cliente
  aoSalvar: (c: Cliente) => void
  aoExcluir: () => void
}) {
  const avisar = useAvisos()
  const { recarregarClientes } = useDados()
  const admin = Api.ehAdmin()
  const [senha, setSenha] = useState("")
  const [confirmar, setConfirmar] = useState("")
  const [erro, setErro] = useState("")

  async function trocarSenha(ev: React.FormEvent) {
    ev.preventDefault()
    if (senha.length < 4) return setErro("A senha precisa ter pelo menos 4 caracteres")
    if (senha !== confirmar) return setErro("As duas senhas não são iguais")
    setErro("")
    try {
      aoSalvar(await Api.put<Cliente>(`/api/clientes/${cliente.id}`, { senha }))
      setSenha("")
      setConfirmar("")
      avisar("Senha trocada")
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  async function mudarAtivo(ativo: boolean) {
    try {
      aoSalvar(await Api.put<Cliente>(`/api/clientes/${cliente.id}`, { ativo }))
      avisar(ativo ? "Cliente ativado" : "Cliente desativado")
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  async function excluir() {
    if (!window.confirm(`Excluir o cliente ${cliente.nome}? Esta ação não pode ser desfeita.`)) return
    try {
      await Api.del(`/api/clientes/${cliente.id}`)
      avisar("Cliente excluído")
      await recarregarClientes()
      aoExcluir()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={trocarSenha} className="flex flex-col gap-3">
        <h4 className="text-sm font-semibold">Trocar a senha</h4>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Campo rotulo="Nova senha" id="ficha-senha">
            <Input id="ficha-senha" type="password" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} />
          </Campo>
          <Campo rotulo="Repita a senha" id="ficha-senha2">
            <Input id="ficha-senha2" type="password" autoComplete="new-password" value={confirmar} onChange={(e) => setConfirmar(e.target.value)} />
          </Campo>
        </div>
        <MensagemErro>{erro}</MensagemErro>
        <Button type="submit" variant="outline" size="sm" className="self-start" disabled={!senha}>
          Trocar senha
        </Button>
      </form>

      <div className="flex items-center justify-between gap-4 rounded-lg border border-borda bg-superficie-2 px-4 py-3">
        <div>
          <label htmlFor="ficha-ativo" className="block text-sm font-semibold">Cliente ativo</label>
          <span className="text-xs text-texto-suave">Desativado, não aparece para liberar e não consegue entrar nos computadores.</span>
        </div>
        <Interruptor id="ficha-ativo" rotulo="Cliente ativo" ligado={cliente.ativo} aoMudar={mudarAtivo} />
      </div>

      {admin && (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-perigo-borda px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-perigo">Excluir cliente</div>
            <span className="text-xs text-texto-suave">Só para quem nunca usou os computadores; quem tem histórico deve ser desativado.</span>
          </div>
          <Button type="button" variant="perigo" size="sm" className="gap-1.5" onClick={excluir}>
            <IconTrash size={14} /> Excluir
          </Button>
        </div>
      )}
    </div>
  )
}
