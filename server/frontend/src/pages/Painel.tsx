import { useMemo, useState } from "react"
import { IconAlertTriangle, IconClockPlay, IconPencil } from "@tabler/icons-react"
import { useAcoes } from "@/lib/acoes"
import { useDados } from "@/lib/dados"
import { formatarTempo, haQuantoTempo, restanteDaSessao } from "@/lib/tempo"
import type { Cliente, Estacao } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { ModalSaldo } from "@/components/ModalSaldo"
import { Button } from "@/components/ui/button"
import { COR_BORDA_STATUS, SeloStatus, Vazio } from "@/components/ui/status"

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
            estacoes.map((e) => <CartaoEstacao key={e.id} estacao={e} aoSoltarCliente={liberar} />)
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

function CartaoEstacao({ estacao: e, aoSoltarCliente }: { estacao: Estacao; aoSoltarCliente: (id: number) => void }) {
  const { sessaoDaEstacao, agora } = useDados()
  const { encerrarSessao } = useAcoes()
  const [alvo, setAlvo] = useState(false)
  const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
  const restante = sessao ? restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora) : 0
  const aceitaCliente = e.status === "livre"

  return (
    <div
      className={cn(
        "rounded-lg border border-l-[3px] border-borda bg-superficie-2 px-3 py-2.5 transition-shadow",
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
        if (id && aceitaCliente) aoSoltarCliente(id)
      }}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[0.9rem] font-semibold">{e.nome}</span>
        <SeloStatus status={e.status} />
      </div>
      {sessao ? (
        <>
          <div className="mb-1 text-sm text-texto-suave">
            {sessao.cliente_nome} <span className="text-texto-fraco">({sessao.cliente_login})</span>
          </div>
          <div
            className={cn(
              "text-lg font-bold tracking-wide tabular-nums",
              restante < 300 ? "text-perigo" : "text-ocupada",
            )}
          >
            {formatarTempo(restante)}
          </div>
          <Button variant="perigo" size="xs" className="mt-2" onClick={() => encerrarSessao(sessao.id, e.nome)}>
            Encerrar sessão
          </Button>
        </>
      ) : (
        <div className="text-sm text-texto-suave">
          {e.status === "livre" ? "Disponível" : e.status === "manutencao" ? "Em manutenção" : "Offline"}
        </div>
      )}
    </div>
  )
}

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
