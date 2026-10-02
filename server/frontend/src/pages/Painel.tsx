import { useEffect, useMemo, useState } from "react"
import { IconAlertTriangle, IconClockPlay, IconMessage, IconPencil, IconPlayerStop, IconRefresh, IconTool, IconWifi, IconWifiOff } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAcoes } from "@/lib/acoes"
import { useDados } from "@/lib/dados"
import { dataDoServidor, formatarTempo, haQuantoTempo, restanteDaSessao } from "@/lib/tempo"
import type { Cliente, Estacao } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { ModalSaldo } from "@/components/ModalSaldo"
import { Button } from "@/components/ui/button"
import { COR_BORDA_STATUS, SeloStatus, Vazio } from "@/components/ui/status"

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

export default function Painel() {
  const { estacoes, clientes, fila } = useDados()
  const { liberar } = useAcoes()
  const [editandoSaldo, setEditandoSaldo] = useState<Cliente | null>(null)

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
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto lg:grid-cols-[1fr_1.2fr_0.8fr] lg:overflow-hidden">
        <Coluna titulo="Estações" total={estacoes.length}>
          {estacoes.length ? (
            estacoes.map((e) => <CartaoEstacao key={e.id} estacao={e} />)
          ) : (
            <Vazio>Nenhuma estação cadastrada. Cadastre em Mapa → Modo configuração.</Vazio>
          )}
        </Coluna>
        <ColunaClientes clientes={clientes} aoEditarSaldo={setEditandoSaldo} />
        <ColunaFila total={fila.length} aoSoltarCliente={liberar} />
      </div>
      <ModalSaldo cliente={editandoSaldo} aoFechar={() => setEditandoSaldo(null)} />
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
  ...props
}: {
  titulo: string
  total: number
  children: React.ReactNode
  topo?: React.ReactNode
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden border-r border-borda last:border-r-0" {...props}>
      <div className="flex shrink-0 items-center gap-2 border-b border-borda bg-superficie-2 px-3.5 py-2">
        <h2 className="text-xs font-semibold tracking-wider text-texto-suave uppercase">{titulo}</h2>
        <span className="rounded-full bg-destaque px-2 text-xs font-semibold text-white">{total}</span>
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
// Cartao da estacao (compacto) — clique abre a modal completa
// ---------------------------------------------------------------------------
function CartaoEstacao({ estacao: e }: { estacao: Estacao }) {
  const { sessaoDaEstacao, agora } = useDados()
  const { liberarDireto } = useAcoes()
  const [alvo, setAlvo] = useState(false)
  const [modalAberta, setModalAberta] = useState(false)
  const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
  const restante = sessao ? restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora) : 0
  const aceitaCliente = e.status === "livre"

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        title="Abrir painel da estação"
        onClick={() => setModalAberta(true)}
        onKeyDown={(ev) => ev.key === "Enter" && setModalAberta(true)}
        className={cn(
          "cursor-pointer rounded-lg border border-l-[3px] border-borda bg-superficie-2 px-3 py-2.5 transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destaque",
          COR_BORDA_STATUS[e.status],
          alvo && "ring-2 ring-destaque",
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
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[0.9rem] font-semibold">{e.nome}</span>
          <div className="flex items-center gap-1.5">
            {e.online
              ? <IconWifi size={13} className="text-livre" />
              : <IconWifiOff size={13} className="text-texto-fraco" />}
            <SeloStatus status={e.status} />
          </div>
        </div>
        {sessao ? (
          <div>
            <div className="mb-0.5 truncate text-sm text-texto-suave">{sessao.cliente_nome}</div>
            <div className={cn("text-lg font-bold tracking-wide tabular-nums", restante < 300 ? "text-perigo" : "text-ocupada")}>
              {formatarTempo(restante)}
            </div>
          </div>
        ) : (
          <div className="text-sm text-texto-fraco">
            {e.status === "livre" ? "Disponivel" : e.status === "manutencao" ? "Em manutencao" : "Offline"}
          </div>
        )}
      </div>

      {modalAberta && (
        <ModalEstacao estacao={e} aoFechar={() => setModalAberta(false)} />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Modal da estacao com abas: Geral | Comandos | Historico
// ---------------------------------------------------------------------------
function ModalEstacao({ estacao: e, aoFechar }: { estacao: Estacao; aoFechar: () => void }) {
  const { sessaoDaEstacao, agora, clientes } = useDados()
  const { encerrarSessao, reiniciarPc, enviarMensagem, alternarManutencao, liberarDireto } = useAcoes()
  const [aba, setAba] = useState<AbaEstacao>("geral")
  const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
  const restante = sessao ? restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora) : 0

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
        <div className="flex items-center justify-between border-b border-borda px-5 pt-4 pb-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{e.nome}</span>
            {e.online
              ? <span className="flex items-center gap-1 text-xs text-livre"><IconWifi size={12} /> Online</span>
              : <span className="flex items-center gap-1 text-xs text-texto-fraco"><IconWifiOff size={12} /> Offline</span>}
          </div>
          <button
            type="button"
            onClick={aoFechar}
            className="mb-1 rounded p-1 text-texto-fraco hover:bg-superficie-2 hover:text-texto"
          >
            ✕
          </button>
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
              clientes={clientes}
              encerrarSessao={encerrarSessao}
              reiniciarPc={reiniciarPc}
              enviarMensagem={enviarMensagem}
              alternarManutencao={alternarManutencao}
              liberarDireto={liberarDireto}
              aoFechar={aoFechar}
            />
          )}
          {aba === "historico" && (
            <AbaHistorico estacao={e.nome} />
          )}
        </div>
      </div>
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
function AbaComandos({ estacao: e, sessao, clientes, encerrarSessao, reiniciarPc, enviarMensagem, alternarManutencao, liberarDireto, aoFechar }: {
  estacao: Estacao
  sessao: ReturnType<ReturnType<typeof useDados>["sessaoDaEstacao"]> | undefined
  clientes: Cliente[]
  encerrarSessao: (id: number, nome: string) => void
  reiniciarPc: (nome: string) => void
  enviarMensagem: (nome: string, texto: string) => void
  alternarManutencao: (nome: string) => void
  liberarDireto: (nome: string, clienteId: number) => Promise<boolean>
  aoFechar: () => void
}) {
  const { sessoes, fila } = useDados()
  const [textoMsg, setTextoMsg] = useState("")
  const [buscaCliente, setBuscaCliente] = useState("")
  const idsEmUso = useMemo(() => new Set(sessoes.map((s) => s.cliente_id)), [sessoes])
  const idsNaFila = useMemo(() => new Set(fila.map((f) => f.cliente_id)), [fila])

  const clientesDisponiveis = useMemo(() =>
    clientes
      .filter((c) => c.ativo && !idsEmUso.has(c.id))
      .filter((c) => !buscaCliente || c.nome.toLowerCase().includes(buscaCliente.toLowerCase()) || c.login.toLowerCase().includes(buscaCliente.toLowerCase())),
    [clientes, idsEmUso, buscaCliente]
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
      {/* Encerrar sessão */}
      {sessao && (
        <SecaoComando titulo="Sessão ativa">
          <div className="mb-2 text-sm text-texto-suave">
            {sessao.cliente_nome} <span className="text-texto-fraco">({sessao.cliente_login})</span>
          </div>
          <Button variant="perigo" size="sm" onClick={() => { encerrarSessao(sessao.id, e.nome); aoFechar() }}>
            <IconPlayerStop size={14} className="mr-1.5" /> Encerrar sessão
          </Button>
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
            {clientesDisponiveis.length ? clientesDisponiveis.map((c) => (
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
            )) : (
              <div className="px-3 py-3 text-center text-xs text-texto-fraco">Nenhum cliente disponível</div>
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
function ColunaClientes({ clientes, aoEditarSaldo }: { clientes: Cliente[]; aoEditarSaldo: (c: Cliente) => void }) {
  const { fila, sessoes } = useDados()
  const { liberar } = useAcoes()
  const [busca, setBusca] = useState("")
  const [liberando, setLiberando] = useState<number | null>(null)
  const idsNaFila = useMemo(() => new Set(fila.map((f) => f.cliente_id)), [fila])
  const estacaoEmUso = useMemo(() => new Map(sessoes.map((s) => [s.cliente_id, s.estacao_nome])), [sessoes])

  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase()
    const ativos = clientes.filter((c) => c.ativo)
    if (!q) return ativos
    return ativos.filter((c) => c.nome.toLowerCase().includes(q) || c.login.toLowerCase().includes(q))
  }, [busca, clientes])

  async function aoLiberar(id: number) {
    setLiberando(id)
    await liberar(id)
    setLiberando(null)
  }

  return (
    <Coluna
      titulo="Clientes"
      total={lista.length}
      topo={
        <div className="shrink-0 border-b border-borda p-2">
          <input
            type="search"
            aria-label="Buscar cliente"
            placeholder="Buscar por nome ou login..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="w-full rounded-md border border-borda bg-superficie-2 px-3 py-1.5 text-sm outline-none focus:border-destaque"
          />
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
                  ) : c.saldo_segundos > 0 ? (
                    <span className="flex items-center gap-1 font-semibold text-livre">
                      <IconClockPlay size={13} /> {formatarTempo(c.saldo_segundos)} disponível
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-manutencao">
                      <IconAlertTriangle size={13} /> Sem saldo: receberá o tempo padrão
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => aoEditarSaldo(c)}
                    title="Editar saldo"
                    aria-label={`Editar saldo de ${c.nome}`}
                    className="cursor-pointer rounded p-0.5 text-texto-fraco opacity-0 group-hover:opacity-100 hover:text-texto focus-visible:opacity-100"
                  >
                    <IconPencil size={13} />
                  </button>
                </div>
              </div>
              <Button size="xs" disabled={naFila || !!emUso || liberando === c.id} onClick={() => aoLiberar(c.id)}>
                {naFila ? "Na fila" : emUso ? "Em uso" : liberando === c.id ? "..." : "Liberar"}
              </Button>
            </div>
          )
        })
      ) : (
        <Vazio>Nenhum cliente encontrado</Vazio>
      )}
    </Coluna>
  )
}

// ---------------------------------------------------------------------------
// Coluna: Fila
// ---------------------------------------------------------------------------
function ColunaFila({ total, aoSoltarCliente }: { total: number; aoSoltarCliente: (id: number) => void }) {
  const { fila, agora } = useDados()
  const { removerDaFila } = useAcoes()

  return (
    <Coluna
      titulo="Fila de espera"
      total={total}
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
