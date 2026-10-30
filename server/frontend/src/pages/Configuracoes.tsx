import { useCallback, useEffect, useState } from "react"
import { Navigate, useSearchParams } from "react-router-dom"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo, lerTempo } from "@/lib/tempo"
import type { AppPermitido, ConfigSistema, Grupo, Operador } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor, MensagemErro, Select } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { SecaoProgramacao } from "@/components/SecaoProgramacao"
import { SeletorCliente, type ClienteResumo } from "@/components/SeletorCliente"
import { SeloAtivo, Vazio } from "@/components/ui/status"

const SECOES = [
  { id: "operadores", rotulo: "Operadores" },
  { id: "comportamento", rotulo: "Comportamento" },
  { id: "grupos", rotulo: "Grupos" },
  { id: "apps", rotulo: "Apps permitidos" },
  { id: "programacao", rotulo: "Programação" },
  { id: "relatorios", rotulo: "Relatórios" },
  { id: "historico", rotulo: "Histórico de uso" },
  { id: "conta", rotulo: "Minha conta" },
] as const
type Secao = (typeof SECOES)[number]["id"]

export default function Configuracoes() {
  const [params, setParams] = useSearchParams()
  if (!Api.ehAdmin()) return <Navigate to="/" replace />
  const secao = (SECOES.find((s) => s.id === params.get("secao"))?.id ?? "operadores") as Secao

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <nav aria-label="Seções" className="w-52 shrink-0 border-r border-borda bg-superficie py-2.5">
        {SECOES.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setParams({ secao: s.id })}
            aria-current={s.id === secao ? "page" : undefined}
            className={cn(
              "block w-full cursor-pointer px-4.5 py-2.5 text-left text-sm",
              s.id === secao ? "bg-destaque text-white" : "text-texto-suave hover:bg-superficie-2 hover:text-texto",
            )}
          >
            {s.rotulo}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-auto px-8 py-6">
        <div className="max-w-2xl">
          {secao === "operadores" && <SecaoOperadores />}
          {secao === "comportamento" && <SecaoComportamento />}
          {secao === "grupos" && <SecaoGrupos />}
          {secao === "apps" && <SecaoApps />}
          {secao === "programacao" && <SecaoProgramacao />}
          {secao === "relatorios" && <SecaoRelatorios />}
          {secao === "historico" && <SecaoHistorico />}
          {secao === "conta" && <SecaoConta />}
        </div>
      </div>
    </div>
  )
}

function Titulo({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-5 text-lg font-semibold">{children}</h2>
}

function Linha({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 flex items-center gap-2.5 rounded-lg border border-borda bg-superficie-2 px-3 py-2.5">
      {children}
    </div>
  )
}

// ── Operadores ───────────────────────────────────────────────────────────────

function SecaoOperadores() {
  const avisar = useAvisos()
  const [operadores, setOperadores] = useState<Operador[] | null>(null)
  const [editando, setEditando] = useState<Operador | "novo" | null>(null)

  const carregar = useCallback(async () => {
    setOperadores(await Api.get<Operador[]>("/api/operadores/"))
  }, [])
  useEffect(() => {
    carregar().catch((e) => avisar((e as Error).message, "erro"))
  }, [carregar, avisar])

  async function excluir(o: Operador) {
    if (!window.confirm(`Excluir o operador ${o.nome}?`)) return
    try {
      await Api.del(`/api/operadores/${o.id}`)
      avisar("Operador excluído")
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <>
      <Titulo>Operadores</Titulo>
      <Button size="sm" variant="outline" className="mb-3" onClick={() => setEditando("novo")}>
        + Novo operador
      </Button>
      {operadores === null ? (
        <Vazio>Carregando...</Vazio>
      ) : operadores.length ? (
        operadores.map((o) => (
          <Linha key={o.id}>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm font-medium">
                {o.nome} <SeloAtivo ativo={o.ativo} />
                <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${o.perfil === "admin" ? "bg-manutencao-fundo text-manutencao" : "bg-superficie-3 text-texto-suave"}`}>{o.perfil}</span>
              </div>
              <div className="font-mono text-xs text-texto-fraco">{o.login}</div>
            </div>
            <Button variant="outline" size="xs" onClick={() => setEditando(o)}>
              Editar
            </Button>
            <Button variant="perigo" size="xs" onClick={() => excluir(o)}>
              Excluir
            </Button>
          </Linha>
        ))
      ) : (
        <Vazio>Nenhum operador cadastrado</Vazio>
      )}
      <ModalOperador operador={editando} aoFechar={() => setEditando(null)} aoSalvar={carregar} />
    </>
  )
}

function ModalOperador({
  operador,
  aoFechar,
  aoSalvar,
}: {
  operador: Operador | "novo" | null
  aoFechar: () => void
  aoSalvar: () => Promise<void>
}) {
  const avisar = useAvisos()
  const novo = operador === "novo"
  const existente = operador && operador !== "novo" ? operador : null
  const [login, setLogin] = useState("")
  const [nome, setNome] = useState("")
  const [senha, setSenha] = useState("")
  const [ativo, setAtivo] = useState(true)
  const [perfil, setPerfil] = useState("operador")
  const [erro, setErro] = useState("")
  const [aberto, setAberto] = useState<typeof operador>(null)

  if (operador !== aberto) {
    setAberto(operador)
    setLogin(existente?.login ?? "")
    setNome(existente?.nome ?? "")
    setSenha("")
    setAtivo(existente?.ativo ?? true)
    setPerfil(existente?.perfil ?? "operador")
    setErro("")
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!login.trim() || !nome.trim()) return setErro("Preencha login e nome")
    if (novo && !senha) return setErro("Senha obrigatória para novo operador")
    try {
      if (existente) {
        await Api.put(`/api/operadores/${existente.id}`, { nome: nome.trim(), ativo, perfil, ...(senha ? { senha } : {}) })
        avisar("Operador atualizado")
      } else {
        await Api.post("/api/operadores/", { login: login.trim(), nome: nome.trim(), senha, perfil })
        avisar("Operador criado")
      }
      aoFechar()
      await aoSalvar()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo={novo ? "Novo operador" : "Editar operador"} aberto={!!operador} aoFechar={aoFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <Campo rotulo="Login" id="op-login">
          <Input id="op-login" autoComplete="off" value={login} disabled={!novo} onChange={(e) => setLogin(e.target.value)} />
        </Campo>
        <Campo rotulo="Nome" id="op-nome">
          <Input id="op-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <Campo rotulo="Senha" id="op-senha">
          <Input
            id="op-senha"
            type="password"
            autoComplete="new-password"
            placeholder={novo ? "" : "Deixe em branco para não alterar"}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </Campo>
        <Campo rotulo="Perfil" id="op-perfil">
          <select
            id="op-perfil"
            value={perfil}
            onChange={(e) => setPerfil(e.target.value)}
            className="w-full rounded-md border border-borda bg-fundo px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primario"
          >
            <option value="operador">Operador</option>
            <option value="admin">Administrador</option>
          </select>
        </Campo>
        {!novo && (
          <div className="flex items-center justify-between">
            <label htmlFor="op-ativo" className="text-sm text-texto-suave">
              Ativo
            </label>
            <Interruptor id="op-ativo" rotulo="Operador ativo" ligado={ativo} aoMudar={setAtivo} />
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

// ── Comportamento ───────────────────────────────────────────────────────────

function SecaoComportamento() {
  const avisar = useAvisos()
  const [reiniciar, setReiniciar] = useState(false)
  const [tempo, setTempo] = useState("")
  const [erro, setErro] = useState("")
  const [zerando, setZerando] = useState(false)
  const { recarregarClientes, recarregarFila } = useDados()

  async function zerarTempoHoje() {
    if (!window.confirm("Zerar o tempo de hoje de todos os clientes? Todos voltam a ter o tempo do dia cheio.")) return
    setZerando(true)
    try {
      const r = await Api.post<{ clientes: number }>("/api/config/zerar_tempo_hoje", {})
      avisar(`Tempo de hoje zerado (${r.clientes} cliente${r.clientes === 1 ? "" : "s"})`)
      await Promise.all([recarregarClientes(), recarregarFila()])
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setZerando(false)
    }
  }

  useEffect(() => {
    Api.get<ConfigSistema>("/api/config/")
      .then((c) => {
        setReiniciar(c.reiniciar_ao_encerrar)
        setTempo(formatarTempo(c.tempo_padrao_segundos))
      })
      .catch((e) => avisar((e as Error).message, "erro"))
  }, [avisar])

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    const segundos = lerTempo(tempo)
    if (!segundos) return setErro("Tempo padrão no formato HH:MM:SS, maior que zero")
    setErro("")
    try {
      await Api.put("/api/config/", { reiniciar_ao_encerrar: reiniciar, tempo_padrao_segundos: segundos })
      avisar("Configurações salvas")
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <form onSubmit={salvar}>
      <Titulo>Comportamento do sistema</Titulo>
      <div className="mb-4 flex items-center justify-between gap-4 rounded-lg border border-borda bg-superficie-2 px-4 py-3.5">
        <div>
          <label htmlFor="cfg-reiniciar" className="mb-0.5 block text-sm font-semibold">
            Reiniciar o PC ao encerrar a sessão
          </label>
          <span className="text-xs text-texto-suave">
            Ao encerrar (tempo esgotado, operador ou cliente), o agente reinicia o computador em 30 segundos.
          </span>
        </div>
        <Interruptor id="cfg-reiniciar" rotulo="Reiniciar o PC ao encerrar a sessão" ligado={reiniciar} aoMudar={setReiniciar} />
      </div>
      <Campo rotulo="Tempo de uso por dia (HH:MM:SS)" id="cfg-tempo">
        <Input id="cfg-tempo" value={tempo} onChange={(e) => setTempo(e.target.value)} className="max-w-48" />
      </Campo>
      <p className="mt-1.5 mb-4 text-xs text-texto-fraco">
        Cada cliente pode usar esse tempo por dia, somando todas as sessões. Quando acaba, só volta amanhã; para dar
        tempo extra, edite o saldo dele. Zera à meia-noite (horário de Brasília).
      </p>
      <MensagemErro>{erro}</MensagemErro>
      <Button type="submit">Salvar configurações</Button>

      <div className="mt-8 flex items-center justify-between gap-4 rounded-lg border border-borda bg-superficie-2 px-4 py-3.5">
        <div>
          <div className="mb-0.5 text-sm font-semibold">Zerar o tempo de hoje</div>
          <span className="text-xs text-texto-suave">
            Todos os clientes voltam a ter o tempo do dia cheio agora, como acontece à meia-noite.
          </span>
        </div>
        <Button type="button" variant="outline" size="sm" disabled={zerando} onClick={zerarTempoHoje}>
          {zerando ? "..." : "Zerar agora"}
        </Button>
      </div>
    </form>
  )
}

// ── Apps permitidos ─────────────────────────────────────────────────────────

function SecaoApps() {
  const avisar = useAvisos()
  const { grupos } = useDados()
  const [apps, setApps] = useState<AppPermitido[] | null>(null)
  const [form, setForm] = useState({ nome: "", processo: "", grupo: "", caminho: "", imagem: "" })
  const [editando, setEditando] = useState<AppPermitido | null>(null)
  const [erro, setErro] = useState("")

  const carregar = useCallback(async () => {
    setApps(await Api.get<AppPermitido[]>("/api/apps/"))
  }, [])
  useEffect(() => {
    carregar().catch((e) => avisar((e as Error).message, "erro"))
  }, [carregar, avisar])

  const campo = (k: keyof typeof form) => ({
    value: form[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value }),
  })

  async function adicionar(ev: React.FormEvent) {
    ev.preventDefault()
    setErro("")
    if (!form.nome.trim() || !form.processo.trim()) return setErro("Preencha nome e processo (.exe)")
    try {
      await Api.post("/api/apps/", {
        nome: form.nome.trim(),
        processo: form.processo.trim(),
        caminho: form.caminho.trim() || null,
        grupo_id: form.grupo ? Number(form.grupo) : null,
        imagem_url: form.imagem.trim() || null,
      })
      setForm({ nome: "", processo: "", grupo: form.grupo, caminho: "", imagem: "" })
      avisar("App adicionado")
      await carregar()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  async function remover(a: AppPermitido) {
    if (!window.confirm(`Remover ${a.nome} dos apps permitidos?`)) return
    try {
      await Api.del(`/api/apps/${a.id}`)
      avisar("App removido")
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <>
      <Titulo>Apps permitidos</Titulo>
      <form onSubmit={adicionar} className="mb-5 flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input aria-label="Nome do app" placeholder="Nome (ex: Google Chrome)" className="h-9 min-w-40 flex-1" {...campo("nome")} />
          <Input aria-label="Processo" placeholder="processo.exe" className="h-9 min-w-32 flex-1" {...campo("processo")} />
          <Select aria-label="Grupo" className="h-9 w-44" {...campo("grupo")}>
            <option value="">Todos os grupos</option>
            {grupos.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nome}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-wrap gap-2">
          <Input aria-label="Caminho do executável" placeholder="Caminho completo do .exe" className="h-9 min-w-60 flex-[2]" {...campo("caminho")} />
          <Input aria-label="URL da imagem de capa" placeholder="URL da imagem (capa)" className="h-9 min-w-40 flex-1" {...campo("imagem")} />
          <Button type="submit" size="sm" className="h-9">
            + Adicionar
          </Button>
        </div>
        <MensagemErro>{erro}</MensagemErro>
      </form>

      {apps === null ? (
        <Vazio>Carregando...</Vazio>
      ) : apps.length ? (
        apps.map((a) => (
          <Linha key={a.id}>
            {a.imagem_url && (
              <img
                src={a.imagem_url}
                alt=""
                className="size-12 shrink-0 rounded-md object-cover"
                onError={(e) => (e.currentTarget.style.display = "none")}
              />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm font-medium">
                {a.nome}
                <span className="rounded-full bg-superficie-3 px-2 text-[0.66rem] text-texto-suave">{a.grupo_nome}</span>
              </div>
              <div className="truncate font-mono text-xs text-texto-fraco">
                {a.processo} · {a.caminho || "(sem caminho: não aparece no launcher)"}
              </div>
            </div>
            <Button variant="outline" size="xs" onClick={() => setEditando(a)}>
              Editar
            </Button>
            <Button variant="perigo" size="xs" onClick={() => remover(a)}>
              Remover
            </Button>
          </Linha>
        ))
      ) : (
        <Vazio>Nenhum app cadastrado. Sem apps na lista, nenhum programa é bloqueado.</Vazio>
      )}
      <ModalApp app={editando} grupos={grupos} aoFechar={() => setEditando(null)} aoSalvar={carregar} />
    </>
  )
}

function ModalApp({
  app,
  grupos,
  aoFechar,
  aoSalvar,
}: {
  app: AppPermitido | null
  grupos: { id: number; nome: string }[]
  aoFechar: () => void
  aoSalvar: () => Promise<void>
}) {
  const avisar = useAvisos()
  const [nome, setNome] = useState("")
  const [processo, setProcesso] = useState("")
  const [caminho, setCaminho] = useState("")
  const [imagem, setImagem] = useState("")
  const [grupoId, setGrupoId] = useState("")
  const [ativo, setAtivo] = useState(true)
  const [erro, setErro] = useState("")
  const [aberto, setAberto] = useState<AppPermitido | null>(null)

  if (app !== aberto) {
    setAberto(app)
    setNome(app?.nome ?? "")
    setProcesso(app?.processo ?? "")
    setCaminho(app?.caminho ?? "")
    setImagem(app?.imagem_url ?? "")
    setGrupoId(app?.grupo_id != null ? String(app.grupo_id) : "")
    setAtivo(app?.ativo ?? true)
    setErro("")
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!app) return
    if (!nome.trim() || !processo.trim()) return setErro("Preencha nome e processo")
    try {
      await Api.put(`/api/apps/${app.id}`, {
        nome: nome.trim(),
        processo: processo.trim(),
        caminho: caminho.trim() || null,
        imagem_url: imagem.trim() || null,
        ativo,
        grupo_id: grupoId ? Number(grupoId) : null,
      })
      avisar("App atualizado")
      aoFechar()
      await aoSalvar()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo="Editar app" aberto={!!app} aoFechar={aoFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <Campo rotulo="Nome" id="app-nome">
          <Input id="app-nome" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <Campo rotulo="Processo (.exe)" id="app-proc">
          <Input id="app-proc" value={processo} onChange={(e) => setProcesso(e.target.value)} />
        </Campo>
        <Campo rotulo="Caminho do .exe" id="app-cam">
          <Input id="app-cam" value={caminho} onChange={(e) => setCaminho(e.target.value)} placeholder="C:\\...\\app.exe" />
        </Campo>
        <Campo rotulo="URL da imagem" id="app-img">
          <Input id="app-img" value={imagem} onChange={(e) => setImagem(e.target.value)} placeholder="https://..." />
        </Campo>
        <Campo rotulo="Grupo" id="app-grupo">
          <Select id="app-grupo" value={grupoId} onChange={(e) => setGrupoId(e.target.value)}>
            <option value="">Todos os grupos</option>
            {grupos.map((g) => (
              <option key={g.id} value={g.id}>{g.nome}</option>
            ))}
          </Select>
        </Campo>
        <div className="flex items-center justify-between">
          <label htmlFor="app-ativo" className="text-sm text-texto-suave">Ativo</label>
          <Interruptor id="app-ativo" rotulo="App ativo" ligado={ativo} aoMudar={setAtivo} />
        </div>
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={aoFechar}>Cancelar</Button>
          <Button type="submit" className="flex-1">Salvar</Button>
        </div>
      </form>
    </Modal>
  )
}

// ── Grupos ──────────────────────────────────────────────────────────────────

interface EditGrupo { nome: string; cor: string }

function SecaoGrupos() {
  const avisar = useAvisos()
  const { grupos, recarregar } = useDados()
  const [novoNome, setNovoNome] = useState("")
  const [novaCor, setNovaCor] = useState("#6366f1")
  const [criando, setCriando] = useState(false)
  const [editando, setEditando] = useState<Record<number, Partial<EditGrupo>>>({})

  function setEdit(id: number, campo: Partial<EditGrupo>) {
    setEditando((prev) => ({ ...prev, [id]: { ...prev[id], ...campo } }))
  }

  async function criarGrupo(ev: React.FormEvent) {
    ev.preventDefault()
    if (!novoNome.trim()) return
    setCriando(true)
    try {
      const params = new URLSearchParams({ nome: novoNome.trim(), cor: novaCor })
      await Api.post(`/api/estacoes/grupos?${params}`, {})
      avisar("Grupo criado")
      setNovoNome("")
      setNovaCor("#6366f1")
      await recarregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setCriando(false)
    }
  }

  async function salvarGrupo(g: Grupo) {
    const ed = editando[g.id] ?? {}
    try {
      await Api.put(`/api/estacoes/grupos/${g.id}`, {
        nome: ed.nome ?? g.nome,
        cor: ed.cor ?? g.cor,
      })
      avisar("Grupo atualizado")
      setEditando((prev) => { const n = { ...prev }; delete n[g.id]; return n })
      await recarregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div>
      <Titulo>Grupos de estacoes</Titulo>
      <p className="mb-4 text-sm text-texto-fraco">
        Nome e cor de cada grupo (sala). A cor aparece no mapa e nas abas. O tempo de uso por dia é um só para todos, em
        Comportamento.
      </p>
      <div className="mb-4 flex flex-col gap-2">
        {grupos.map((g) => {
          const ed = editando[g.id] ?? {}
          const nomeAtual = ed.nome ?? g.nome
          const corAtual = ed.cor ?? g.cor
          const alterado = ed.nome !== undefined || ed.cor !== undefined
          return (
            <div key={g.id} className="flex items-center gap-3 rounded-lg border border-borda bg-superficie-2 px-4 py-2.5">
              {/* bolinha de cor */}
              <input
                type="color"
                value={corAtual}
                onChange={(ev) => setEdit(g.id, { cor: ev.target.value })}
                className="size-7 shrink-0 cursor-pointer rounded-full border-0 bg-transparent p-0"
                title="Cor do grupo"
              />
              {/* nome */}
              <input
                type="text"
                value={nomeAtual}
                onChange={(ev) => setEdit(g.id, { nome: ev.target.value })}
                className="min-w-0 flex-1 rounded-md border border-borda bg-superficie px-2 py-1 text-sm outline-none focus:border-destaque"
              />
              {alterado && (
                <Button size="sm" onClick={() => salvarGrupo(g)}>Salvar</Button>
              )}
            </div>
          )
        })}
        {grupos.length === 0 && (
          <p className="text-sm text-texto-fraco">Nenhum grupo cadastrado.</p>
        )}
      </div>
      <form onSubmit={criarGrupo} className="flex items-end gap-2">
        <input
          type="color"
          value={novaCor}
          onChange={(e) => setNovaCor(e.target.value)}
          className="size-9 shrink-0 cursor-pointer rounded-md border border-borda bg-transparent p-0.5"
          title="Cor do grupo"
        />
        <div className="flex-1">
          <Campo rotulo="Nome" id="novo-grupo-nome">
            <Input id="novo-grupo-nome" value={novoNome} onChange={(e) => setNovoNome(e.target.value)} placeholder="ex: Infantil" />
          </Campo>
        </div>
        <Button type="submit" disabled={criando || !novoNome.trim()}>
          {criando ? "..." : "+ Criar grupo"}
        </Button>
      </form>
    </div>
  )
}

// ── Relatórios ──────────────────────────────────────────────────────────────

function SecaoRelatorios() {
  const avisar = useAvisos()
  const { estacoes } = useDados()
  const [inicio, setInicio] = useState("")
  const [fim, setFim] = useState("")
  const [cliente, setCliente] = useState<ClienteResumo | null>(null)
  const [estacao, setEstacao] = useState("")
  const [gerando, setGerando] = useState(false)

  async function exportar(ev: React.FormEvent) {
    ev.preventDefault()
    const params = new URLSearchParams()
    if (inicio) params.append("data_inicio", inicio)
    if (fim) params.append("data_fim", fim)
    if (cliente) params.append("cliente_id", String(cliente.id))
    if (estacao) params.append("estacao_nome", estacao)
    setGerando(true)
    try {
      await Api.baixar(`/api/relatorios/csv?${params}`, "relatorio_sessoes.csv")
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setGerando(false)
    }
  }

  return (
    <form onSubmit={exportar} className="flex flex-col gap-4">
      <Titulo>Relatórios</Titulo>
      <p className="-mt-3 text-sm text-texto-suave">Sessões encerradas, em CSV (abre no Excel).</p>
      <div className="flex gap-3">
        <div className="flex-1">
          <Campo rotulo="Data início" id="rel-inicio">
            <Input id="rel-inicio" type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
          </Campo>
        </div>
        <div className="flex-1">
          <Campo rotulo="Data fim" id="rel-fim">
            <Input id="rel-fim" type="date" value={fim} onChange={(e) => setFim(e.target.value)} />
          </Campo>
        </div>
      </div>
      <Campo rotulo="Cliente" id="rel-cliente">
        <SeletorCliente id="rel-cliente" valor={cliente} aoMudar={setCliente} />
      </Campo>
      <Campo rotulo="Estação" id="rel-estacao">
        <Select id="rel-estacao" value={estacao} onChange={(e) => setEstacao(e.target.value)}>
          <option value="">Todas</option>
          {estacoes.map((e) => (
            <option key={e.id} value={e.nome}>
              {e.nome}
            </option>
          ))}
        </Select>
      </Campo>
      <Button type="submit" className="self-start" disabled={gerando}>
        {gerando ? "Gerando..." : "Exportar CSV"}
      </Button>
    </form>
  )
}

// ─── Seção: Histórico de uso ─────────────────────────────────────────────────
interface SessaoHist {
  id: number
  cliente_nome: string
  cliente_login: string
  estacao_nome: string
  iniciada_em: string
  encerrada_em: string | null
  tempo_consumido_segundos: number
  motivo_encerramento: string | null
}

const MOTIVOS: Record<string, string> = {
  tempo_esgotado: "Tempo esgotado",
  encerrado_operador: "Operador",
  conexao_perdida: "Queda de conexão",
  encerrado_cliente: "Cliente encerrou",
  saldo_zerado: "Saldo zerado",
}

function SecaoHistorico() {
  const [sessoes, setSessoes] = useState<SessaoHist[] | null>(null)
  const [filtroCliente, setFiltroCliente] = useState("")
  const [filtroEstacao, setFiltroEstacao] = useState("")
  const [filtroDe, setFiltroDe] = useState("")
  const [filtroAte, setFiltroAte] = useState("")
  const [carregando, setCarregando] = useState(false)

  const carregar = useCallback(async () => {
    setCarregando(true)
    try {
      const params = new URLSearchParams({ limit: "500" })
      const data = await Api.get<SessaoHist[]>(`/api/sessoes/historico?${params}`)
      setSessoes(data)
    } finally {
      setCarregando(false)
    }
  }, [])

  useEffect(() => { void carregar() }, [carregar])

  // listas únicas para os selects
  const clientes = Array.from(new Map((sessoes ?? []).map(s => [s.cliente_login, s.cliente_nome])).entries())
    .sort((a, b) => a[1].localeCompare(b[1]))
  const estacoes = Array.from(new Set((sessoes ?? []).map(s => s.estacao_nome))).sort()

  const lista = (sessoes ?? []).filter((s) => {
    if (filtroCliente && s.cliente_login !== filtroCliente) return false
    if (filtroEstacao && s.estacao_nome !== filtroEstacao) return false
    if (filtroDe) {
      const inicio = new Date(s.iniciada_em)
      const de = new Date(filtroDe + "T00:00:00")
      if (inicio < de) return false
    }
    if (filtroAte) {
      const inicio = new Date(s.iniciada_em)
      const ate = new Date(filtroAte + "T23:59:59")
      if (inicio > ate) return false
    }
    return true
  })

  const temFiltro = filtroCliente || filtroEstacao || filtroDe || filtroAte
  const selectCls = "rounded-md border border-borda bg-superficie-2 px-2 py-1.5 text-sm outline-none focus:border-destaque"

  return (
    <>
      <Titulo>Histórico de uso</Titulo>
      <div className="mb-4 flex flex-wrap gap-2">
        <select value={filtroCliente} onChange={(e) => setFiltroCliente(e.target.value)} className={selectCls}>
          <option value="">Todos os clientes</option>
          {clientes.map(([login, nome]) => (
            <option key={login} value={login}>{nome} ({login})</option>
          ))}
        </select>
        <select value={filtroEstacao} onChange={(e) => setFiltroEstacao(e.target.value)} className={selectCls}>
          <option value="">Todas as estações</option>
          {estacoes.map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
        <div className="flex items-center gap-1">
          <span className="text-xs text-texto-suave">De</span>
          <input type="date" value={filtroDe} onChange={(e) => setFiltroDe(e.target.value)} className={selectCls} />
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-texto-suave">até</span>
          <input type="date" value={filtroAte} onChange={(e) => setFiltroAte(e.target.value)} className={selectCls} />
        </div>
        {temFiltro && (
          <button type="button" onClick={() => { setFiltroCliente(""); setFiltroEstacao(""); setFiltroDe(""); setFiltroAte("") }}
            className="text-xs text-texto-suave underline hover:text-texto">
            Limpar filtros
          </button>
        )}
        <Button variant="outline" size="xs" onClick={carregar} disabled={carregando} className="ml-auto">
          {carregando ? "..." : "Atualizar"}
        </Button>
      </div>
      {sessoes === null ? (
        <Vazio>Carregando...</Vazio>
      ) : lista.length === 0 ? (
        <Vazio>Nenhuma sessão encontrada</Vazio>
      ) : (
        <div className="overflow-auto rounded-lg border border-borda">
          <table className="w-full text-sm">
            <thead className="bg-superficie-2 text-xs text-texto-suave">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Cliente</th>
                <th className="px-3 py-2 text-left font-medium">Estação</th>
                <th className="px-3 py-2 text-left font-medium">Início</th>
                <th className="px-3 py-2 text-left font-medium">Duração</th>
                <th className="px-3 py-2 text-left font-medium">Motivo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borda">
              {lista.map((s) => (
                <tr key={s.id} className="hover:bg-superficie-2">
                  <td className="px-3 py-2">
                    <div className="font-medium">{s.cliente_nome}</div>
                    <div className="font-mono text-xs text-texto-fraco">{s.cliente_login}</div>
                  </td>
                  <td className="px-3 py-2 text-texto-suave">{s.estacao_nome}</td>
                  <td className="px-3 py-2 font-mono text-xs text-texto-suave">
                    {new Date(s.iniciada_em).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {formatarTempo(s.tempo_consumido_segundos)}
                  </td>
                  <td className="px-3 py-2 text-xs text-texto-suave">
                    {MOTIVOS[s.motivo_encerramento ?? ""] ?? s.motivo_encerramento ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

// ─── Seção: Minha conta ───────────────────────────────────────────────────────
function SecaoConta() {
  const avisar = useAvisos()
  const [senhaAtual, setSenhaAtual] = useState("")
  const [novaSenha, setNovaSenha] = useState("")
  const [confirmar, setConfirmar] = useState("")
  const [erro, setErro] = useState("")
  const [salvando, setSalvando] = useState(false)

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    setErro("")
    if (!senhaAtual) return setErro("Informe a senha atual")
    if (novaSenha.length < 4) return setErro("Nova senha muito curta (mínimo 4 caracteres)")
    if (novaSenha !== confirmar) return setErro("As senhas não coincidem")
    setSalvando(true)
    try {
      await Api.put("/api/auth/trocar-senha", { senha_atual: senhaAtual, nova_senha: novaSenha })
      avisar("Senha alterada com sucesso")
      setSenhaAtual(""); setNovaSenha(""); setConfirmar("")
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setSalvando(false)
    }
  }

  return (
    <>
      <Titulo>Minha conta</Titulo>
      <div className="max-w-sm">
        <h3 className="mb-4 text-sm font-semibold text-texto-suave uppercase tracking-wide">Alterar senha</h3>
        <form onSubmit={salvar} className="flex flex-col gap-4">
          <Campo rotulo="Senha atual" id="mc-atual">
            <Input id="mc-atual" type="password" autoComplete="current-password" value={senhaAtual} onChange={(e) => setSenhaAtual(e.target.value)} />
          </Campo>
          <Campo rotulo="Nova senha" id="mc-nova">
            <Input id="mc-nova" type="password" autoComplete="new-password" value={novaSenha} onChange={(e) => setNovaSenha(e.target.value)} />
          </Campo>
          <Campo rotulo="Confirmar nova senha" id="mc-confirmar">
            <Input id="mc-confirmar" type="password" autoComplete="new-password" value={confirmar} onChange={(e) => setConfirmar(e.target.value)} />
          </Campo>
          <MensagemErro>{erro}</MensagemErro>
          <Button type="submit" disabled={salvando} className="w-full">
            {salvando ? "Salvando..." : "Salvar nova senha"}
          </Button>
        </form>
      </div>
    </>
  )
}
