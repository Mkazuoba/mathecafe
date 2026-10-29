import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { IconAlertTriangle, IconCamera, IconChevronDown, IconChevronUp, IconSelector, IconClockPlay, IconMessage, IconPencil, IconSettings, IconUserPlus, IconPlayerPause, IconPlayerPlay, IconPlayerStop, IconRefresh, IconTool, IconVideo, IconVideoOff, IconWifi, IconWifiOff } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAcoes } from "@/lib/acoes"
import { useAvisos } from "@/lib/avisos"
import { FILTROS_PADRAO, gravarFiltros, lerFiltros, useBuscaClientes, type FiltrosClientes } from "@/lib/buscaClientes"
import { useDados } from "@/lib/dados"
import { dataDoServidor, formatarTempo, haQuantoTempo, restanteDaSessao } from "@/lib/tempo"
import type { Cliente, Estacao, Grupo, Sessao, StatusEstacao } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { Campo, Input, Interruptor, MensagemErro, Select } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { BotoesMover, ColunasAjustaveis, useLayoutColunas, type LayoutColunas } from "@/components/ColunasAjustaveis"
import { FiltrosBusca } from "@/components/FiltrosBusca"

import { Button } from "@/components/ui/button"
import { ROTULO_STATUS, SeloStatus, Vazio } from "@/components/ui/status"

interface SessaoHistorico {
  id: number
  cliente_id: number
  cliente_login: string
  cliente_nome: string
  estacao_nome: string
  iniciada_em: string
  encerrada_em: string | null
  tempo_total_segundos: number
  tempo_consumido_segundos: number
  motivo_encerramento: string | null
}

type AbaEstacao = "geral" | "comandos" | "historico"

// Cliente sendo arrastado (drag and drop nativo do navegador)
const TIPO_ARRASTO = "application/x-mathecafe-cliente"

type IdColuna = "estacoes" | "clientes" | "fila"
const LAYOUT_PADRAO: LayoutColunas<IdColuna> = {
  ordem: ["estacoes", "clientes", "fila"],
  larguras: { estacoes: 44, clientes: 31, fila: 25 },
}

export default function Painel() {
  const { estacoes, fila } = useDados()
  const { liberar } = useAcoes()
  const [editandoCliente, setEditandoCliente] = useState<Cliente | null>(null)
  const [novoCliente, setNovoCliente] = useState(false)
  const { layout, setLayout, mover, restaurar, alterado } = useLayoutColunas("painel.layout", LAYOUT_PADRAO)

  const contagem = useMemo(
    () => ({
      livre: estacoes.filter((e) => e.status === "livre").length,
      ocupada: estacoes.filter((e) => e.status === "ocupada").length,
      desligada: estacoes.filter((e) => e.status === "desligada").length,
      manutencao: estacoes.filter((e) => e.status === "manutencao").length,
    }),
    [estacoes],
  )

  return (
    <>
      <div className="flex shrink-0 gap-6 border-b border-borda bg-superficie px-5 py-1.5 text-sm">
        <Contador cor="bg-livre" valor={contagem.livre} rotulo="livres" />
        <Contador cor="bg-ocupada" valor={contagem.ocupada} rotulo="ocupadas" />
        <Contador cor="bg-desligada" valor={contagem.desligada} rotulo="desligadas" />
        {contagem.manutencao > 0 && <Contador cor="bg-manutencao" valor={contagem.manutencao} rotulo="em manutenção" />}
        {alterado && (
          <button type="button" onClick={restaurar} className="ml-auto hidden text-xs text-texto-fraco hover:text-destaque lg:block">
            Restaurar layout
          </button>
        )}
      </div>
      <ColunasAjustaveis layout={layout} padrao={LAYOUT_PADRAO} aoMudar={setLayout}>
        {(id, posicao) => {
          const controles = <BotoesMover posicao={posicao} total={layout.ordem.length} aoMover={(d) => mover(id, d)} />
          if (id === "estacoes") return <ColunaEstacoes controles={controles} />
          if (id === "clientes")
            return <ColunaClientes controles={controles} aoEditarCliente={setEditandoCliente} aoNovoCliente={() => setNovoCliente(true)} />
          return <ColunaFila controles={controles} total={fila.length} aoSoltarCliente={liberar} />
        }}
      </ColunasAjustaveis>
      <ModalEditarCliente cliente={editandoCliente} aoFechar={() => setEditandoCliente(null)} />
      <ModalNovoCliente aberto={novoCliente} aoFechar={() => setNovoCliente(false)} />
    </>
  )
}

function Contador({ cor, valor, rotulo }: { cor: string; valor: number; rotulo: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("size-2 rounded-full", cor)} />
      <strong className="font-semibold">{valor}</strong>
      <span className="text-xs text-texto-fraco">{rotulo}</span>
    </span>
  )
}

function Coluna({
  titulo,
  total,
  children,
  topo,
  controles,
  ...props
}: {
  titulo: string
  total: number
  children: React.ReactNode
  topo?: React.ReactNode
  controles?: React.ReactNode
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden" {...props}>
      <div className="flex shrink-0 items-center gap-2 border-b border-borda bg-superficie-2 px-3.5 py-2">
        <h2 className="truncate text-xs font-semibold tracking-wider text-texto-suave uppercase">{titulo}</h2>
        <span className="rounded-full bg-destaque px-2 text-xs font-semibold text-white">{total}</span>
        {controles && <span className="ml-auto">{controles}</span>}
      </div>
      {topo}
      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-2">{children}</div>
    </section>
  )
}

function lerClienteArrastado(ev: React.DragEvent): number | null {
  const v = ev.dataTransfer.getData(TIPO_ARRASTO)
  return v ? Number(v) : null
}

// ---------------------------------------------------------------------------
// Controle de sessões: tabela das estações, como no VSCyber — filtro por grupo,
// ordenação por coluna e contagem por status. Clique abre a modal da estação.
// ---------------------------------------------------------------------------
type ColunaOrdem = "status" | "estacao" | "login" | "tempo"
interface Ordem { coluna: ColunaOrdem; desc: boolean }
interface LinhaTabela { estacao: Estacao; sessao: Sessao | undefined; restante: number }

const SEM_GRUPO = "sem"
const ORDEM_PADRAO: Ordem = { coluna: "status", desc: false }
const ORDEM_STATUS: Record<StatusEstacao, number> = { desligada: 0, livre: 1, ocupada: 2, manutencao: 3 }
const COR_TEXTO_STATUS: Record<StatusEstacao, string> = {
  livre: "text-livre",
  ocupada: "text-ocupada",
  desligada: "text-desligada",
  manutencao: "text-manutencao",
}
const ROTULO_PLURAL: Record<StatusEstacao, string> = {
  desligada: "Desligadas",
  livre: "Livres",
  ocupada: "Ocupadas",
  manutencao: "Em manutenção",
}

// Preferências do operador neste navegador (o storage pode estar bloqueado)
function lerPreferencia(chave: string): string | null {
  try {
    return localStorage.getItem(chave)
  } catch {
    return null
  }
}
function gravarPreferencia(chave: string, valor: string) {
  try {
    localStorage.setItem(chave, valor)
  } catch {
    /* sem storage: vale só até recarregar */
  }
}
function lerOrdem(): Ordem {
  try {
    const o = JSON.parse(lerPreferencia("painel.ordem") ?? "")
    if (["status", "estacao", "login", "tempo"].includes(o?.coluna)) return { coluna: o.coluna, desc: !!o.desc }
  } catch {
    /* padrão */
  }
  return ORDEM_PADRAO
}

// AD-2 antes de AD-10
const compararNome = (a: string, b: string) => a.localeCompare(b, "pt-BR", { numeric: true, sensitivity: "base" })

function compararLinhas(a: LinhaTabela, b: LinhaTabela, coluna: ColunaOrdem): number {
  switch (coluna) {
    case "status":
      return ORDEM_STATUS[a.estacao.status] - ORDEM_STATUS[b.estacao.status]
    case "estacao":
      return 0
    case "login": {
      const la = a.sessao?.cliente_login ?? ""
      const lb = b.sessao?.cliente_login ?? ""
      if (!la || !lb) return la ? -1 : lb ? 1 : 0
      return compararNome(la, lb)
    }
    case "tempo":
      return a.restante - b.restante
  }
}

function ColunaEstacoes({ controles }: { controles?: React.ReactNode }) {
  const { estacoes, grupos, sessaoDaEstacao, agora, carregado } = useDados()
  const [grupo, setGrupo] = useState(() => lerPreferencia("painel.grupo") ?? "")
  const [ordem, setOrdem] = useState<Ordem>(lerOrdem)
  const [abertaId, setAbertaId] = useState<number | null>(null)

  // grupo apagado depois de escolhido: volta para "Todos"
  const grupoEfetivo = grupo === SEM_GRUPO || grupos.some((g) => String(g.id) === grupo) ? grupo : ""

  const linhas = useMemo(() => {
    const filtradas = estacoes.filter((e) =>
      grupoEfetivo === "" ? true : grupoEfetivo === SEM_GRUPO ? e.grupo_id == null : String(e.grupo_id) === grupoEfetivo,
    )
    const resultado: LinhaTabela[] = filtradas.map((e) => {
      const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
      const restante = sessao ? restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora) : 0
      return { estacao: e, sessao, restante }
    })
    const sinal = ordem.desc ? -1 : 1
    return resultado.sort(
      (a, b) => sinal * compararLinhas(a, b, ordem.coluna) || sinal * compararNome(a.estacao.nome, b.estacao.nome),
    )
  }, [estacoes, grupoEfetivo, ordem, sessaoDaEstacao, agora])

  const contagem = useMemo(() => {
    const c: Record<StatusEstacao, number> = { desligada: 0, livre: 0, ocupada: 0, manutencao: 0 }
    for (const l of linhas) c[l.estacao.status]++
    return c
  }, [linhas])

  function escolherGrupo(valor: string) {
    setGrupo(valor)
    gravarPreferencia("painel.grupo", valor)
  }
  function ordenar(coluna: ColunaOrdem) {
    const nova = { coluna, desc: ordem.coluna === coluna ? !ordem.desc : false }
    setOrdem(nova)
    gravarPreferencia("painel.ordem", JSON.stringify(nova))
  }

  const aberta = abertaId != null ? estacoes.find((e) => e.id === abertaId) : undefined
  const temSemGrupo = estacoes.some((e) => e.grupo_id == null)

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-borda bg-superficie-2 px-3.5 py-1.5">
        <h2 className="text-xs font-semibold tracking-wider whitespace-nowrap text-texto-suave uppercase">Controle de sessões</h2>
        <span className="rounded-full bg-destaque px-2 text-xs font-semibold text-white">{linhas.length}</span>
        <Select
          aria-label="Grupo de estações"
          className="ml-auto h-8 w-auto max-w-[45%] py-0 text-sm"
          value={grupoEfetivo}
          onChange={(ev) => escolherGrupo(ev.target.value)}
        >
          <option value="">Todos os grupos</option>
          {grupos.map((g) => (
            <option key={g.id} value={String(g.id)}>
              {g.nome}
            </option>
          ))}
          {temSemGrupo && <option value={SEM_GRUPO}>Sem grupo</option>}
        </Select>
        {controles}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!carregado ? null : estacoes.length === 0 ? (
          <Vazio>Nenhuma estação cadastrada. Cadastre em Mapa → Modo configuração.</Vazio>
        ) : linhas.length === 0 ? (
          <Vazio>Nenhuma estação neste grupo.</Vazio>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-superficie">
              <tr className="border-b border-borda text-left text-xs text-texto-suave">
                <Cabecalho coluna="status" ordem={ordem} aoOrdenar={ordenar}>Status</Cabecalho>
                <Cabecalho coluna="estacao" ordem={ordem} aoOrdenar={ordenar}>Estação</Cabecalho>
                <Cabecalho coluna="login" ordem={ordem} aoOrdenar={ordenar}>Login</Cabecalho>
                <Cabecalho coluna="tempo" ordem={ordem} aoOrdenar={ordenar} className="text-right">
                  Tempo restante
                </Cabecalho>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <LinhaEstacao key={l.estacao.id} linha={l} aoAbrir={() => setAbertaId(l.estacao.id)} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex shrink-0 flex-wrap gap-x-4 gap-y-0.5 border-t border-borda bg-superficie-2 px-3.5 py-1.5 text-xs text-texto-suave">
        {(Object.keys(ROTULO_PLURAL) as StatusEstacao[])
          .filter((s) => s !== "manutencao" || contagem.manutencao > 0)
          .map((s) => (
            <span key={s}>
              {ROTULO_PLURAL[s]}: <strong className={COR_TEXTO_STATUS[s]}>{contagem[s]}</strong>
            </span>
          ))}
      </div>

      {aberta && <ModalEstacao estacao={aberta} aoFechar={() => setAbertaId(null)} />}
    </section>
  )
}

function Cabecalho({ coluna, ordem, aoOrdenar, className, children }: {
  coluna: ColunaOrdem
  ordem: Ordem
  aoOrdenar: (c: ColunaOrdem) => void
  className?: string
  children: React.ReactNode
}) {
  const ativa = ordem.coluna === coluna
  return (
    <th
      scope="col"
      aria-sort={ativa ? (ordem.desc ? "descending" : "ascending") : "none"}
      className={cn("px-2 py-1.5 font-semibold", className)}
    >
      <button
        type="button"
        onClick={() => aoOrdenar(coluna)}
        title="Ordenar"
        className={cn(
          "inline-flex items-center gap-0.5 whitespace-nowrap hover:text-texto focus-visible:underline focus-visible:outline-none",
          ativa && "text-texto",
        )}
      >
        {children}
        {ativa ? (
          ordem.desc ? <IconChevronDown size={13} /> : <IconChevronUp size={13} />
        ) : (
          <IconSelector size={13} className="opacity-40" />
        )}
      </button>
    </th>
  )
}

function LinhaEstacao({ linha: { estacao: e, sessao, restante }, aoAbrir }: { linha: LinhaTabela; aoAbrir: () => void }) {
  const { liberarDireto } = useAcoes()
  const [alvo, setAlvo] = useState(false)
  const aceitaCliente = e.status === "livre"
  const cliente = sessao ? `${sessao.cliente_login} - ${sessao.cliente_nome}` : ""

  return (
    <tr
      tabIndex={0}
      title="Abrir painel da estação"
      onClick={aoAbrir}
      onKeyDown={(ev) => ev.key === "Enter" && aoAbrir()}
      className={cn(
        "cursor-pointer border-b border-borda/60 hover:bg-superficie-2 focus-visible:bg-superficie-2 focus-visible:outline-none",
        e.status === "desligada" && "text-texto-suave",
        alvo && "bg-destaque/15",
      )}
      onDragOver={(ev) => {
        if (aceitaCliente && ev.dataTransfer.types.includes(TIPO_ARRASTO)) {
          ev.preventDefault()
          setAlvo(true)
        }
      }}
      onDragLeave={() => setAlvo(false)}
      onDrop={(ev) => {
        ev.preventDefault()
        setAlvo(false)
        const id = lerClienteArrastado(ev)
        if (id && aceitaCliente) liberarDireto(e.nome, id)
      }}
    >
      <td className={cn("px-2 py-1.5 font-semibold whitespace-nowrap capitalize", COR_TEXTO_STATUS[e.status])}>
        {ROTULO_STATUS[e.status]}
      </td>
      <td className="px-2 py-1.5 whitespace-nowrap">
        <span className="inline-flex items-center gap-1.5">
          {e.nome}
          {!e.online && e.status !== "desligada" && (
            <IconWifiOff size={13} className="text-texto-fraco" aria-label="sem conexão" />
          )}
        </span>
      </td>
      <td className="w-full max-w-0 truncate px-2 py-1.5" title={cliente || undefined}>
        {sessao && (
          <>
            {cliente}
            {sessao.pausada && (
              <span className="ml-1.5 rounded bg-manutencao/20 px-1 py-0.5 text-[10px] font-bold text-manutencao uppercase">
                Pausada
              </span>
            )}
          </>
        )}
      </td>
      <td
        className={cn(
          "px-2 py-1.5 text-right whitespace-nowrap tabular-nums",
          !sessao ? "text-texto-fraco" : restante < 300 ? "font-semibold text-perigo" : "text-texto",
        )}
      >
        {formatarTempo(restante)}
      </td>
    </tr>
  )
}


// ---------------------------------------------------------------------------
// Form inline: editar nome e grupo da estação
// ---------------------------------------------------------------------------
function FormEditarEstacao({ estacao, grupos, aoSalvar, aoCancelar }: {
  estacao: Estacao
  grupos: Grupo[]
  aoSalvar: () => Promise<void>
  aoCancelar: () => void
}) {
  const avisar = useAvisos()
  const [nome, setNome] = useState(estacao.nome)
  const [grupoId, setGrupoId] = useState<number | "">(estacao.grupo_id ?? "")
  const [mac, setMac] = useState(estacao.mac_address ?? "")
  const [salvando, setSalvando] = useState(false)

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return
    setSalvando(true)
    try {
      await Api.put(`/api/estacoes/${estacao.id}`, {
        nome: nome.trim(),
        grupo_id: grupoId === "" ? null : grupoId,
        mac_address: mac.trim() || null,
      })
      await aoSalvar()
      avisar("Estação atualizada")
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setSalvando(false)
    }
  }

  return (
    <form onSubmit={salvar} className="flex flex-1 items-center gap-2">
      <input
        autoFocus
        type="text"
        value={nome}
        onChange={(ev) => setNome(ev.target.value)}
        className="w-32 rounded-md border border-destaque bg-superficie-2 px-2 py-1 text-sm font-semibold outline-none"
      />
      <select
        value={grupoId}
        onChange={(ev) => setGrupoId(ev.target.value === "" ? "" : Number(ev.target.value))}
        className="rounded-md border border-borda bg-superficie-2 px-2 py-1 text-sm outline-none focus:border-destaque"
      >
        <option value="">Sem grupo</option>
        {grupos.map((g) => (
          <option key={g.id} value={g.id}>{g.nome}</option>
        ))}
      </select>
      <input
        type="text"
        placeholder="MAC (AA:BB:CC:DD:EE:FF)"
        value={mac}
        onChange={(ev) => setMac(ev.target.value)}
        className="w-44 rounded-md border border-borda bg-superficie-2 px-2 py-1 font-mono text-xs outline-none focus:border-destaque"
      />
      <Button type="submit" size="xs" disabled={salvando || !nome.trim()}>
        {salvando ? "..." : "Salvar"}
      </Button>
      <Button type="button" variant="outline" size="xs" onClick={aoCancelar}>
        Cancelar
      </Button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Modal da estacao com abas: Geral | Comandos | Historico
// ---------------------------------------------------------------------------
function ModalEstacao({ estacao: e, aoFechar }: { estacao: Estacao; aoFechar: () => void }) {
  const { sessaoDaEstacao, agora, grupos, recarregarEstacoes } = useDados()
  const { encerrarSessao, reiniciarPc, enviarMensagem, alternarManutencao, liberarDireto } = useAcoes()
  const avisar = useAvisos()
  const [aba, setAba] = useState<AbaEstacao>("geral")
  const [editandoNome, setEditandoNome] = useState(false)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
  const restante = sessao ? restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora) : 0

  const [streaming, setStreaming] = useState(false)
  const [frameUrl, setFrameUrl] = useState<string | null>(null)

  // Escuta captura_tela, tela_frame e log_agente via WebSocket.
  // Usa polling para re-registrar quando o WS for substituido apos reconexao.
  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.dados?.estacao !== e.nome) return
        if (msg.evento === "captura_tela") {
          setScreenshot("data:image/jpeg;base64," + msg.dados.imagem)
        }
        if (msg.evento === "tela_frame") {
          setFrameUrl("data:image/jpeg;base64," + msg.dados.imagem)
        }
        if (msg.evento === "log_agente") {
          const ts = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
          void ts // log_agente ignorado nesta versao
        }
      } catch { /* ignore */ }
    }
    let wsAtual: WebSocket | undefined
    function registrar() {
      const ws = (window as any).__mathecafe_ws as WebSocket | undefined
      if (ws && ws !== wsAtual) {
        if (wsAtual) wsAtual.removeEventListener("message", onMessage)
        wsAtual = ws
        ws.addEventListener("message", onMessage)
      }
    }
    registrar()
    const intervalo = setInterval(registrar, 1000)
    return () => {
      clearInterval(intervalo)
      if (wsAtual) wsAtual.removeEventListener("message", onMessage)
    }
  }, [e.nome])

  // Para o streaming ao desmontar o modal
  useEffect(() => {
    return () => {
      if (streaming) {
        Api.post(`/api/estacoes/${e.nome}/parar_streaming`, {}).catch(() => {})
      }
    }
  }, [streaming, e.nome])

  async function toggleStreaming() {
    if (streaming) {
      await Api.post(`/api/estacoes/${e.nome}/parar_streaming`, {})
      setStreaming(false)
      setFrameUrl(null)
    } else {
      await Api.post(`/api/estacoes/${e.nome}/iniciar_streaming`, {})
      setStreaming(true)
    }
  }

  const abas: { id: AbaEstacao; label: string }[] = [
    { id: "geral", label: "Geral" },
    { id: "comandos", label: "Comandos" },
    { id: "historico", label: "Historico" },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={aoFechar}>
      <div
        className="flex w-[520px] max-w-[95vw] flex-col rounded-xl border border-borda bg-superficie shadow-xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        {/* cabeçalho */}
        <div className="flex items-center justify-between border-b border-borda px-5 pt-4 pb-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            {editandoNome ? (
              <FormEditarEstacao
                estacao={e}
                grupos={grupos}
                aoSalvar={async () => { await recarregarEstacoes(); setEditandoNome(false) }}
                aoCancelar={() => setEditandoNome(false)}
              />
            ) : (
              <>
                <span className="font-semibold">{e.nome}</span>
                <button
                  type="button"
                  title="Editar estação"
                  onClick={() => setEditandoNome(true)}
                  className="rounded p-0.5 text-texto-fraco hover:bg-superficie-2 hover:text-texto"
                >
                  <IconPencil size={13} />
                </button>
                {e.online
                  ? <span className="flex items-center gap-1 text-xs text-livre"><IconWifi size={12} /> Online</span>
                  : <span className="flex items-center gap-1 text-xs text-texto-fraco"><IconWifiOff size={12} /> Offline</span>}
              </>
            )}
          </div>
          {!editandoNome && (
            <button
              type="button"
              onClick={aoFechar}
              className="ml-2 shrink-0 rounded p-1 text-texto-fraco hover:bg-superficie-2 hover:text-texto"
            >
              ✕
            </button>
          )}
        </div>

        {/* abas */}
        <div className="flex border-b border-borda px-5">
          {abas.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setAba(a.id)}
              className={cn(
                "border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
                aba === a.id
                  ? "border-destaque text-destaque"
                  : "border-transparent text-texto-fraco hover:text-texto",
              )}
            >
              {a.label}
            </button>
          ))}
        </div>

        {/* conteúdo */}
        <div className="flex-1 p-5">
          {aba === "geral" && (
            <AbaGeral estacao={e} sessao={sessao} restante={restante} />
          )}
          {aba === "comandos" && (
            <AbaComandos
              estacao={e}
              sessao={sessao}
              encerrarSessao={encerrarSessao}
              reiniciarPc={reiniciarPc}
              enviarMensagem={enviarMensagem}
              alternarManutencao={alternarManutencao}
              liberarDireto={liberarDireto}
              aoFechar={aoFechar}
              aoCapturarTela={() => Api.post(`/api/estacoes/${e.nome}/capturar_tela`, {})}
              streaming={streaming}
              frameUrl={frameUrl}
              toggleStreaming={toggleStreaming}
            />
          )}
          {aba === "historico" && (
            <AbaHistorico estacao={e.nome} />
          )}
        </div>

        {/* Botão Ligar PC — só quando offline e tem MAC */}
        {!e.online && e.mac_address && (
          <div className="border-t border-borda px-5 py-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                Api.post(`/api/estacoes/${e.nome}/ligar`, {})
                  .then(() => avisar("Magic packet enviado!"))
                  .catch((err: Error) => avisar(err.message, "erro"))
              }
            >
              <IconWifi size={14} className="mr-1.5" /> Ligar PC
            </Button>
          </div>
        )}
      </div>

      {/* Screenshot overlay */}
      {screenshot && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80"
          onClick={() => setScreenshot(null)}
        >
          <div className="relative max-h-[90vh] max-w-[90vw]" onClick={(ev) => ev.stopPropagation()}>
            <img src={screenshot} alt={`Tela de ${e.nome}`} className="max-h-[85vh] rounded-lg shadow-2xl" />
            <button
              type="button"
              onClick={() => setScreenshot(null)}
              className="absolute top-2 right-2 rounded-full bg-black/60 px-2 py-1 text-xs text-white hover:bg-black/80"
            >
              Fechar ✕
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Aba: Geral
// ---------------------------------------------------------------------------
function AbaGeral({ estacao: e, sessao, restante }: {
  estacao: Estacao
  sessao: ReturnType<ReturnType<typeof useDados>["sessaoDaEstacao"]> | undefined
  restante: number
}) {
  const rows: [string, React.ReactNode][] = [
    ["Status", <SeloStatus status={e.status} />],
    ["Conexão", e.online ? <span className="text-livre">Online</span> : <span className="text-texto-fraco">Offline</span>],
    ...(e.grupo_nome ? [["Grupo", e.grupo_nome] as [string, React.ReactNode]] : []),
    ...(e.mac_address ? [["MAC", <span className="font-mono text-xs text-texto-suave">{e.mac_address}</span>] as [string, React.ReactNode]] : []),
  ]

  if (sessao) {
    rows.push(
      ["Cliente", `${sessao.cliente_nome} (${sessao.cliente_login})`],
      ["Tempo restante", (
        <span className={cn("tabular-nums font-semibold", restante < 300 ? "text-perigo" : "text-ocupada")}>
          {formatarTempo(restante)}
        </span>
      )],
      ["Tempo total", formatarTempo(sessao.tempo_total_segundos)],
    )
  }

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
      {rows.map(([label, valor]) => (
        <>
          <dt key={`dt-${label}`} className="text-texto-fraco">{label}</dt>
          <dd key={`dd-${label}`} className="text-texto">{valor}</dd>
        </>
      ))}
    </dl>
  )
}

// ---------------------------------------------------------------------------
// Aba: Comandos
// ---------------------------------------------------------------------------

function AbaComandos({ estacao: e, sessao, encerrarSessao, reiniciarPc, enviarMensagem, alternarManutencao, liberarDireto, aoFechar, aoCapturarTela, streaming, frameUrl, toggleStreaming }: {
  estacao: Estacao
  sessao: ReturnType<ReturnType<typeof useDados>["sessaoDaEstacao"]> | undefined
  encerrarSessao: (id: number, nome: string) => void
  reiniciarPc: (nome: string) => void
  enviarMensagem: (nome: string, texto: string) => void
  alternarManutencao: (nome: string) => void
  liberarDireto: (nome: string, clienteId: number) => Promise<boolean>
  aoFechar: () => void
  aoCapturarTela: () => void
  streaming: boolean
  frameUrl: string | null
  toggleStreaming: () => Promise<void>
}) {
  const { sessoes, fila } = useDados()
  const [textoMsg, setTextoMsg] = useState("")
  const [buscaCliente, setBuscaCliente] = useState("")
  const idsEmUso = useMemo(() => new Set(sessoes.map((s) => s.cliente_id)), [sessoes])
  const idsNaFila = useMemo(() => new Set(fila.map((f) => f.cliente_id)), [fila])

  const { clientes: clientesBusca, carregando: buscando } = useBuscaClientes(buscaCliente)
  const clientesDisponiveis = useMemo(() =>
    clientesBusca.filter((c) => c.ativo && !idsEmUso.has(c.id)),
    [clientesBusca, idsEmUso]
  )

  if (!e.online) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
        <IconWifiOff size={32} className="text-texto-fraco" />
        <p className="text-sm text-texto-fraco">Estação offline — comandos indisponíveis</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <SecaoComando titulo="Monitoramento">
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={aoCapturarTela}>
              <IconCamera size={14} className="mr-1.5" /> Captura rápida
            </Button>
            <Button
              variant={streaming ? "perigo" : "outline"}
              size="sm"
              onClick={toggleStreaming}
            >
              {streaming
                ? <><IconVideoOff size={14} className="mr-1.5" /> Parar live</>
                : <><IconVideo size={14} className="mr-1.5" /> Ver ao vivo</>}
            </Button>
          </div>
          {streaming && (
            <div className="relative mt-1 overflow-hidden rounded-lg border border-borda bg-black">
              {frameUrl
                ? <img src={frameUrl} alt="Stream ao vivo" className="w-full rounded-lg" />
                : <div className="flex h-32 items-center justify-center text-xs text-texto-fraco">Aguardando primeiro frame...</div>
              }
              <span className="absolute top-1.5 left-1.5 rounded bg-red-600/80 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">● ao vivo</span>
            </div>
          )}
        </div>
      </SecaoComando>
      {/* Sessão ativa: pausar/retomar/renovar/encerrar */}
      {sessao && (
        <SecaoComando titulo="Sessão ativa">
          <div className="mb-2 text-sm text-texto-suave">
            {sessao.cliente_nome} <span className="text-texto-fraco">({sessao.cliente_login})</span>
            {sessao.pausada && <span className="ml-2 rounded bg-yellow-500/20 px-1.5 py-0.5 text-xs font-semibold text-yellow-400">PAUSADA</span>}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  if (sessao.pausada) {
                    await Api.post(`/api/sessoes/retomar/${sessao.id}`)
                  } else {
                    await Api.post(`/api/sessoes/pausar/${sessao.id}`)
                  }
                } catch (err) { console.error(err) }
              }}
            >
              {sessao.pausada
                ? <><IconPlayerPlay size={14} className="mr-1.5" /> Retomar</>
                : <><IconPlayerPause size={14} className="mr-1.5" /> Pausar</>}
            </Button>
            <Button variant="perigo" size="sm" onClick={() => { encerrarSessao(sessao.id, e.nome); aoFechar() }}>
              <IconPlayerStop size={14} className="mr-1.5" /> Encerrar
            </Button>
          </div>
          <RenovarSaldo sessaoId={sessao.id} />
        </SecaoComando>
      )}

      {/* Liberar direto */}
      {e.status === "livre" && (
        <SecaoComando titulo="Liberar cliente direto">
          <input
            type="search"
            placeholder="Buscar cliente..."
            value={buscaCliente}
            onChange={(ev) => setBuscaCliente(ev.target.value)}
            className="mb-2 w-full rounded-md border border-borda bg-superficie-2 px-3 py-1.5 text-sm outline-none focus:border-destaque"
          />
          <div className="max-h-36 overflow-y-auto rounded-md border border-borda">
            {buscando ? (
              <div className="px-3 py-3 text-center text-xs text-texto-fraco">Buscando...</div>
            ) : !buscaCliente.trim() ? (
              <div className="px-3 py-3 text-center text-xs text-texto-fraco">Digite para buscar um cliente</div>
            ) : clientesDisponiveis.length === 0 ? (
              <div className="px-3 py-3 text-center text-xs text-texto-fraco">Nenhum cliente encontrado</div>
            ) : (
              clientesDisponiveis.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => liberarDireto(e.nome, c.id).then((ok) => { if (ok) aoFechar() })}
                  className="flex w-full items-center gap-2 border-b border-borda px-3 py-2 text-left text-sm last:border-0 hover:bg-superficie-2"
                >
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-superficie-3 text-xs font-semibold text-destaque uppercase">
                    {c.nome.slice(0, 2)}
                  </span>
                  <span className="flex-1 truncate">{c.nome}</span>
                  <span className="text-xs text-texto-fraco">{c.login}{idsNaFila.has(c.id) ? " · fila" : ""}</span>
                </button>
              ))
            )}
          </div>
        </SecaoComando>
      )}

      {/* Mensagem na tela */}
      <SecaoComando titulo="Mensagem na tela">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Digite a mensagem..."
            value={textoMsg}
            onChange={(ev) => setTextoMsg(ev.target.value)}
            onKeyDown={(ev) => { if (ev.key === "Enter" && textoMsg.trim()) { enviarMensagem(e.nome, textoMsg.trim()); setTextoMsg("") } }}
            className="flex-1 rounded-md border border-borda bg-superficie-2 px-3 py-1.5 text-sm outline-none focus:border-destaque"
          />
          <Button size="sm" disabled={!textoMsg.trim()} onClick={() => { enviarMensagem(e.nome, textoMsg.trim()); setTextoMsg("") }}>
            <IconMessage size={14} />
          </Button>
        </div>
      </SecaoComando>

      {/* Manutenção + Reiniciar */}
      <SecaoComando titulo="Outros">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="flex-1" onClick={() => { alternarManutencao(e.nome); aoFechar() }}>
            <IconTool size={14} className="mr-1.5" />
            {e.status === "manutencao" ? "Sair da manutenção" : "Modo manutenção"}
          </Button>
          <Button variant="perigo" size="sm" onClick={() => { reiniciarPc(e.nome); aoFechar() }}>
            <IconRefresh size={14} className="mr-1.5" /> Reiniciar
          </Button>
        </div>
      </SecaoComando>
    </div>
  )
}

function RenovarSaldo({ sessaoId }: { sessaoId: number }) {
  const avisar = useAvisos()
  const [minutos, setMinutos] = useState("")
  const [salvando, setSalvando] = useState(false)

  async function renovar() {
    const m = parseInt(minutos)
    if (!m || m <= 0) return
    setSalvando(true)
    try {
      await Api.post(`/api/sessoes/renovar/${sessaoId}?minutos=${m}`, {})
      avisar(`+${m} min adicionados`)
      setMinutos("")
    } catch (err) {
      avisar((err as Error).message, "erro")
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div className="mt-3 flex items-center gap-2">
      <input
        type="number"
        min={1}
        placeholder="min"
        value={minutos}
        onChange={(ev) => setMinutos(ev.target.value)}
        onKeyDown={(ev) => ev.key === "Enter" && renovar()}
        className="w-20 rounded-md border border-borda bg-superficie-2 px-2 py-1 text-sm tabular-nums outline-none focus:border-destaque"
      />
      <Button size="sm" variant="outline" disabled={!minutos || salvando} onClick={renovar}>
        {salvando ? "..." : "Renovar saldo"}
      </Button>
    </div>
  )
}

function SecaoComando({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold tracking-wider text-texto-fraco uppercase">{titulo}</p>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Aba: Histórico
// ---------------------------------------------------------------------------
function AbaHistorico({ estacao }: { estacao: string }) {
  const [sessoes, setSessoes] = useState<SessaoHistorico[]>([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState("")

  useEffect(() => {
    setCarregando(true)
    setErro("")
    Api.get<SessaoHistorico[]>(`/api/sessoes/historico?estacao_nome=${encodeURIComponent(estacao)}`)
      .then((r) => setSessoes(r ?? []))
      .catch((e) => setErro((e as Error).message))
      .finally(() => setCarregando(false))
  }, [estacao])

  function motivoLabel(motivo: string | null) {
    if (!motivo) return "—"
    const mapa: Record<string, string> = {
      saldo_zerado: "Saldo zerado", encerrado_operador: "Operador",
      desconexao: "Desconexao", reinicio: "Reinicio", manual: "Manual",
    }
    return mapa[motivo] ?? motivo
  }

  const totalConsuming = sessoes.reduce((s, x) => s + (x.tempo_consumido_segundos ?? 0), 0)

  if (carregando) return <p className="py-8 text-center text-sm text-texto-fraco">Carregando...</p>
  if (erro) return <p className="text-sm text-perigo">{erro}</p>

  return (
    <div className="flex flex-col gap-3">
      <div className="max-h-72 overflow-auto rounded-md border border-borda">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="sticky top-0 bg-superficie text-left text-xs tracking-wide text-texto-fraco uppercase">
              {["Data", "Cliente", "Duracao", "Consumido", "Encerr."].map((h) => (
                <th key={h} className="border-b border-borda px-2.5 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sessoes.map((s) => (
              <tr key={s.id} className="hover:bg-superficie-2">
                <td className="border-b border-borda px-2.5 py-2 text-texto-suave">
                  {s.iniciada_em ? dataDoServidor(s.iniciada_em).toLocaleDateString("pt-BR") : "—"}
                </td>
                <td className="border-b border-borda px-2.5 py-2">
                  <div className="font-medium">{s.cliente_nome}</div>
                  <div className="text-xs text-texto-fraco">{s.cliente_login}</div>
                </td>
                <td className="border-b border-borda px-2.5 py-2 tabular-nums">{formatarTempo(s.tempo_total_segundos ?? 0)}</td>
                <td className="border-b border-borda px-2.5 py-2 tabular-nums text-texto-suave">{formatarTempo(s.tempo_consumido_segundos ?? 0)}</td>
                <td className="border-b border-borda px-2.5 py-2 text-texto-fraco">{motivoLabel(s.motivo_encerramento)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!sessoes.length && <div className="px-3 py-6 text-center text-sm text-texto-fraco">Nenhuma sessao registrada</div>}
      </div>
      <Link to={`/historicos?aba=estacao&estacao=${encodeURIComponent(estacao)}`} className="self-start text-sm text-destaque hover:underline">
        Ver quais clientes já passaram por aqui →
      </Link>
      {sessoes.length > 0 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-texto-fraco">{sessoes.length} sessão(ões)</span>
          <span className="text-texto-suave">
            Total consumido: <span className="font-semibold tabular-nums text-texto">{formatarTempo(totalConsuming)}</span>
          </span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Coluna: Clientes
// ---------------------------------------------------------------------------
function ColunaClientes({ aoEditarCliente, aoNovoCliente, controles }: {
  aoEditarCliente: (c: Cliente) => void
  aoNovoCliente: () => void
  controles?: React.ReactNode
}) {
  const { fila, sessoes } = useDados()
  const { liberar } = useAcoes()
  const [busca, setBusca] = useState("")
  const [filtros, setFiltros] = useState(() => lerFiltros("painel.busca", FILTROS_PADRAO))
  const [liberando, setLiberando] = useState<number | null>(null)
  const idsNaFila = useMemo(() => new Set(fila.map((f) => f.cliente_id)), [fila])
  const estacaoEmUso = useMemo(() => new Map(sessoes.map((s) => [s.cliente_id, s.estacao_nome])), [sessoes])

  // inativos nunca aparecem aqui: não podem ser liberados
  const { clientes: lista, carregando } = useBuscaClientes(busca, {
    campo: filtros.campo, modo: filtros.modo, saldo: filtros.saldo, status: "ativos",
  })

  function mudarFiltros(f: FiltrosClientes) {
    setFiltros(f)
    gravarFiltros("painel.busca", f)
  }
  const dica = filtros.campo === "login" ? "Buscar por login..." : filtros.campo === "nome" ? "Buscar por nome..." : "Buscar por nome ou login..."

  async function aoLiberar(id: number) {
    setLiberando(id)
    await liberar(id)
    setLiberando(null)
  }

  return (
    <Coluna
      titulo="Clientes"
      total={lista.length}
      controles={controles}
      topo={
        <div className="shrink-0 border-b border-borda p-2 flex flex-col gap-2">
          <Button size="xs" variant="outline" className="w-full gap-1 justify-center" onClick={aoNovoCliente}><IconUserPlus size={14} /> Novo cliente</Button>
          <div className="flex gap-1.5">
            <input
              type="search"
              aria-label="Buscar cliente"
              placeholder={dica}
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-borda bg-superficie-2 px-3 py-1.5 text-sm outline-none focus:border-destaque"
            />
            <FiltrosBusca valor={filtros} padrao={FILTROS_PADRAO} campos={["campo", "modo", "saldo"]} aoMudar={mudarFiltros} />
          </div>
        </div>
      }
    >
      {lista.length ? (
        lista.map((c) => {
          const naFila = idsNaFila.has(c.id) || c.na_fila
          const emUso = estacaoEmUso.get(c.id)
          return (
            <div
              key={c.id}
              draggable={!naFila}
              onDragStart={(ev) => ev.dataTransfer.setData(TIPO_ARRASTO, String(c.id))}
              className={cn(
                "group flex items-center gap-2.5 rounded-lg border px-3 py-2 transition-colors",
                naFila
                  ? "border-destaque bg-destaque-fundo"
                  : "cursor-grab border-borda bg-superficie-2 hover:border-borda-forte",
              )}
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-superficie-3 text-xs font-semibold text-destaque uppercase">
                {c.nome.slice(0, 2)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {c.nome}
                  {naFila && (
                    <span className="rounded-full border border-destaque px-1.5 text-[0.66rem] font-semibold text-destaque">
                      Na fila
                    </span>
                  )}
                </div>
                <div className="text-xs text-texto-fraco">{c.login}</div>
                <div className="mt-0.5 flex items-center gap-1 text-xs">
                  {emUso ? (
                    <span className="font-semibold text-ocupada">Em uso no {emUso}</span>
                  ) : c.saldo_segundos <= 0 ? (
                    <span className="flex items-center gap-1 font-semibold text-perigo">
                      <IconAlertTriangle size={13} /> Tempo de hoje esgotado
                    </span>
                  ) : c.saldo_segundos > 0 ? (
                    <span className="flex items-center gap-1 font-semibold text-livre">
                      <IconClockPlay size={13} /> {formatarTempo(c.saldo_segundos)} disponível
                    </span>
                  ) : null}
                </div>
              </div>
              <button type="button" onClick={() => aoEditarCliente(c)} title="Editar cliente" className="shrink-0 rounded p-1 text-texto-fraco opacity-0 group-hover:opacity-100 hover:text-texto focus-visible:opacity-100"><IconSettings size={15} /></button>
              <Button size="xs" disabled={naFila || !!emUso || liberando === c.id} onClick={() => aoLiberar(c.id)}>
                {naFila ? "Na fila" : emUso ? "Em uso" : liberando === c.id ? "..." : "Liberar"}
              </Button>
            </div>
          )
        })
      ) : carregando ? (
        <Vazio>Buscando...</Vazio>
      ) : busca.trim() ? (
        <Vazio>Nenhum cliente encontrado</Vazio>
      ) : (
        <Vazio>Digite o nome ou login para buscar</Vazio>
      )}
    </Coluna>
  )
}

// ---------------------------------------------------------------------------
// Coluna: Fila
// ---------------------------------------------------------------------------
function ColunaFila({ total, aoSoltarCliente, controles }: {
  total: number
  aoSoltarCliente: (id: number) => void
  controles?: React.ReactNode
}) {
  const { fila, agora } = useDados()
  const { removerDaFila } = useAcoes()

  return (
    <Coluna
      titulo="Fila de espera"
      total={total}
      controles={controles}
      onDragOver={(ev) => ev.dataTransfer.types.includes(TIPO_ARRASTO) && ev.preventDefault()}
      onDrop={(ev) => {
        ev.preventDefault()
        const id = lerClienteArrastado(ev)
        if (id) aoSoltarCliente(id)
      }}
    >
      {fila.length ? (
        fila.map((f, i) => (
          <div key={f.id} className="rounded-lg border border-destaque bg-superficie-2 px-3 py-2.5">
            <div className="mb-1 flex items-center gap-2">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-destaque text-xs font-bold text-white">
                {i + 1}
              </span>
              <span className="flex-1 text-sm font-semibold">{f.cliente_nome}</span>
              <Button variant="perigo" size="xs" onClick={() => removerDaFila(f.cliente_id)}>
                Remover
              </Button>
            </div>
            <div className="ml-8 text-xs text-texto-suave">
              {f.cliente_login} · Saldo:{" "}
              <span className="font-semibold text-livre">
                {f.saldo_segundos > 0 ? formatarTempo(f.saldo_segundos) : "sessão nova"}
              </span>{" "}
              · aguardando há {haQuantoTempo(f.autorizado_em, agora)}
            </div>
          </div>
        ))
      ) : (
        <Vazio>Nenhum cliente na fila. Clique em Liberar ou arraste um cliente para cá.</Vazio>
      )}
    </Coluna>
  )
}

// ─── Modal de edição completa do cliente ────────────────────────────────────
function ModalEditarCliente({ cliente, aoFechar }: { cliente: Cliente | null; aoFechar: () => void }) {
  const avisar = useAvisos()
  const { recarregarClientes, recarregarFila } = useDados()
  const [nome, setNome] = useState("")
  const [senha, setSenha] = useState("")
  const [ativo, setAtivo] = useState(true)
  const [obs, setObs] = useState("")
  const [erro, setErro] = useState("")
  const [aberto, setAberto] = useState<Cliente | null>(null)

  if (cliente !== aberto) {
    setAberto(cliente)
    setNome(cliente?.nome ?? "")
    setSenha("")
    setAtivo(cliente?.ativo ?? true)
    setObs(cliente?.observacao ?? "")
    setErro("")
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return setErro("Nome obrigatório")
    try {
      await Api.put(`/api/clientes/${cliente!.id}`, {
        nome: nome.trim(),
        ativo,
        observacao: obs.trim() || null,
        ...(senha ? { senha } : {}),
      })
      avisar("Cliente atualizado")
      aoFechar()
      await Promise.all([recarregarClientes(), recarregarFila()])
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo={`Editar: ${cliente?.nome ?? ""}`} aberto={!!cliente} aoFechar={aoFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <Campo rotulo="Login" id="ec-login">
          <Input id="ec-login" value={cliente?.login ?? ""} disabled />
        </Campo>
        <Campo rotulo="Nome" id="ec-nome">
          <Input id="ec-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <Campo rotulo="Nova senha" id="ec-senha">
          <Input
            id="ec-senha"
            type="password"
            autoComplete="new-password"
            placeholder="Deixe em branco para não alterar"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </Campo>
        <Campo rotulo="Observação" id="ec-obs">
          <Input id="ec-obs" autoComplete="off" placeholder="Opcional" value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
        <div className="flex items-center justify-between">
          <label htmlFor="ec-ativo" className="text-sm text-texto-suave">Ativo</label>
          <Interruptor id="ec-ativo" rotulo="Cliente ativo" ligado={ativo} aoMudar={setAtivo} />
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

// ─── Modal de criação de novo cliente ───────────────────────────────────────
function ModalNovoCliente({ aberto, aoFechar }: { aberto: boolean; aoFechar: () => void }) {
  const avisar = useAvisos()
  const { recarregarClientes } = useDados()
  const [login, setLogin] = useState("")
  const [nome, setNome] = useState("")
  const [senha, setSenha] = useState("")
  const [obs, setObs] = useState("")
  const [erro, setErro] = useState("")

  function resetar() {
    setLogin(""); setNome(""); setSenha(""); setObs(""); setErro("")
  }

  function fechar() { resetar(); aoFechar() }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!login.trim()) return setErro("Login obrigatório")
    if (!nome.trim()) return setErro("Nome obrigatório")
    if (!senha) return setErro("Senha obrigatória")
    try {
      await Api.post("/api/clientes/", {
        login: login.trim(),
        nome: nome.trim(),
        senha,
        observacao: obs.trim() || null,
      })
      avisar("Cliente criado")
      fechar()
      await recarregarClientes()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo="Novo cliente" aberto={aberto} aoFechar={fechar}>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <Campo rotulo="Login" id="nc-login">
          <Input id="nc-login" autoComplete="off" value={login} onChange={(e) => setLogin(e.target.value)} autoFocus />
        </Campo>
        <Campo rotulo="Nome" id="nc-nome">
          <Input id="nc-nome" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} />
        </Campo>
        <Campo rotulo="Senha" id="nc-senha">
          <Input id="nc-senha" type="password" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} />
        </Campo>
        <Campo rotulo="Observação" id="nc-obs">
          <Input id="nc-obs" autoComplete="off" placeholder="Opcional" value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={fechar}>Cancelar</Button>
          <Button type="submit" className="flex-1">Criar cliente</Button>
        </div>
      </form>
    </Modal>
  )
}
