import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { IconPencil } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { dataDoServidor, formatarTempo, lerTempo } from "@/lib/tempo"
import type { Cliente } from "@/lib/tipos"
import { CabecalhoTela } from "@/components/Layout"
import { ModalSaldo } from "@/components/ModalSaldo"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor, MensagemErro, Select, Textarea } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { SeloAtivo, Vazio } from "@/components/ui/status"

type Filtro = "todos" | "ativos" | "inativos"

export default function Clientes() {
  const { clientes, recarregarClientes } = useDados()
  const avisar = useAvisos()
  const navigate = useNavigate()
  const admin = Api.ehAdmin()
  const [busca, setBusca] = useState("")
  const [filtro, setFiltro] = useState<Filtro>("todos")
  const [editando, setEditando] = useState<Cliente | "novo" | null>(null)
  const [editandoSaldo, setEditandoSaldo] = useState<Cliente | null>(null)

  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase()
    return clientes.filter(
      (c) =>
        (!q || c.nome.toLowerCase().includes(q) || c.login.toLowerCase().includes(q)) &&
        (filtro === "todos" || (filtro === "ativos") === c.ativo),
    )
  }, [busca, filtro, clientes])

  async function excluir(c: Cliente) {
    if (!window.confirm(`Excluir o cliente ${c.nome}? Esta ação não pode ser desfeita.`)) return
    try {
      await Api.del(`/api/clientes/${c.id}`)
      avisar("Cliente excluído")
      await recarregarClientes()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <>
      <CabecalhoTela titulo="Clientes">
        <Input
          type="search"
          aria-label="Buscar cliente"
          placeholder="Buscar por nome ou login..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          className="h-9 w-64"
        />
        <Select aria-label="Filtrar por status" value={filtro} onChange={(e) => setFiltro(e.target.value as Filtro)} className="h-9 w-32">
          <option value="todos">Todos</option>
          <option value="ativos">Ativos</option>
          <option value="inativos">Inativos</option>
        </Select>
        <div className="flex-1" />
        {admin && (
          <Button variant="outline" size="sm" onClick={() => navigate("/configuracoes?secao=relatorios")}>
            Exportar CSV
          </Button>
        )}
        <Button size="sm" onClick={() => setEditando("novo")}>
          + Novo cliente
        </Button>
      </CabecalhoTela>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs tracking-wide text-texto-fraco uppercase">
              {["Login", "Nome", "Saldo de tempo", "Status", "Criado em", "Ações"].map((t) => (
                <th key={t} className="border-b border-borda px-2.5 py-2 font-medium">
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id} className="hover:bg-superficie-2">
                <td className="border-b border-borda px-2.5 py-2.5">{c.login}</td>
                <td className="border-b border-borda px-2.5 py-2.5">{c.nome}</td>
                <td className="border-b border-borda px-2.5 py-2.5">
                  <button
                    type="button"
                    onClick={() => setEditandoSaldo(c)}
                    title="Editar saldo"
                    className={
                      "inline-flex cursor-pointer items-center gap-1.5 tabular-nums " +
                      (c.saldo_segundos > 0 ? "font-semibold text-livre" : "text-texto-fraco")
                    }
                  >
                    {formatarTempo(c.saldo_segundos)}
                    <IconPencil size={13} className="text-texto-fraco" />
                  </button>
                </td>
                <td className="border-b border-borda px-2.5 py-2.5">
                  <SeloAtivo ativo={c.ativo} />
                </td>
                <td className="border-b border-borda px-2.5 py-2.5 text-texto-suave">
                  {c.criado_em ? dataDoServidor(c.criado_em).toLocaleDateString("pt-BR") : "—"}
                </td>
                <td className="border-b border-borda px-2.5 py-2.5">
                  <div className="flex gap-1.5">
                    <Button variant="outline" size="xs" onClick={() => setEditando(c)}>
                      Editar
                    </Button>
                    {admin && (
                      <Button variant="perigo" size="xs" onClick={() => excluir(c)}>
                        Excluir
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!lista.length && <Vazio>Nenhum cliente encontrado</Vazio>}
      </div>

      <ModalCliente cliente={editando} aoFechar={() => setEditando(null)} />
      <ModalSaldo cliente={editandoSaldo} aoFechar={() => setEditandoSaldo(null)} />
    </>
  )
}

function ModalCliente({ cliente, aoFechar }: { cliente: Cliente | "novo" | null; aoFechar: () => void }) {
  const avisar = useAvisos()
  const { recarregarClientes } = useDados()
  const novo = cliente === "novo"
  const existente = cliente && cliente !== "novo" ? cliente : null

  const [login, setLogin] = useState("")
  const [nome, setNome] = useState("")
  const [senha, setSenha] = useState("")
  const [saldo, setSaldo] = useState("00:00:00")
  const [obs, setObs] = useState("")
  const [ativo, setAtivo] = useState(true)
  const [erro, setErro] = useState("")
  const [aberto, setAberto] = useState<typeof cliente>(null)

  // Preenche o formulário ao abrir
  if (cliente !== aberto) {
    setAberto(cliente)
    setLogin(existente?.login ?? "")
    setNome(existente?.nome ?? "")
    setSenha("")
    setSaldo(formatarTempo(existente?.saldo_segundos ?? 0))
    setObs(existente?.observacao ?? "")
    setAtivo(existente?.ativo ?? true)
    setErro("")
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    setErro("")
    if (!login.trim() || !nome.trim()) return setErro("Preencha login e nome")
    if (novo && !senha) return setErro("Senha obrigatória para novo cliente")
    const saldoSegundos = lerTempo(saldo)
    if (saldoSegundos === null) return setErro("Saldo no formato HH:MM:SS")

    try {
      if (existente) {
        await Api.put(`/api/clientes/${existente.id}`, {
          nome: nome.trim(),
          ativo,
          observacao: obs.trim() || null,
          saldo_segundos: saldoSegundos,
          ...(senha ? { senha } : {}),
        })
        avisar("Cliente atualizado")
      } else {
        const criado = await Api.post<Cliente>("/api/clientes/", {
          login: login.trim(),
          nome: nome.trim(),
          senha,
          observacao: obs.trim() || null,
        })
        if (saldoSegundos > 0) await Api.put(`/api/clientes/${criado.id}`, { saldo_segundos: saldoSegundos })
        avisar("Cliente criado")
      }
      aoFechar()
      await recarregarClientes()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo={novo ? "Novo cliente" : "Editar cliente"} aberto={!!cliente} aoFechar={aoFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <Campo rotulo="Login" id="cli-login">
          <Input id="cli-login" autoComplete="off" value={login} disabled={!novo} onChange={(e) => setLogin(e.target.value)} />
        </Campo>
        <Campo rotulo="Nome" id="cli-nome">
          <Input id="cli-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <Campo rotulo="Senha" id="cli-senha">
          <Input
            id="cli-senha"
            type="password"
            autoComplete="new-password"
            placeholder={novo ? "" : "Deixe em branco para não alterar"}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </Campo>
        <Campo rotulo="Saldo de tempo (HH:MM:SS)" id="cli-saldo">
          <Input id="cli-saldo" value={saldo} onChange={(e) => setSaldo(e.target.value)} />
        </Campo>
        <Campo rotulo="Observações" id="cli-obs">
          <Textarea id="cli-obs" rows={2} value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
        {!novo && (
          <div className="flex items-center justify-between">
            <label htmlFor="cli-ativo" className="text-sm text-texto-suave">
              Ativo
            </label>
            <Interruptor id="cli-ativo" rotulo="Cliente ativo" ligado={ativo} aoMudar={setAtivo} />
          </div>
        )}
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
