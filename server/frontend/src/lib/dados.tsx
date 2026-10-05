import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import { Api } from "@/lib/api"
import type { Cliente, Estacao, Grupo, ItemFila, Sessao } from "@/lib/tipos"
import { restanteDaSessao } from "@/lib/tempo"

interface Dados {
  estacoes: Estacao[]
  clientes: Cliente[]
  fila: ItemFila[]
  sessoes: Sessao[]
  grupos: Grupo[]
  carregado: boolean
  tempoReal: boolean
  /** Relógio compartilhado (ms), atualizado a cada segundo para as contagens. */
  agora: number
  recarregar: () => Promise<void>
  recarregarClientes: () => Promise<void>
  recarregarFila: () => Promise<void>
  recarregarEstacoes: () => Promise<void>
  sessaoDaEstacao: (nome: string) => Sessao | undefined
}

const DadosContext = createContext<Dados | null>(null)

export function ProvedorDados({ children }: { children: React.ReactNode }) {
  const [estacoes, setEstacoes] = useState<Estacao[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [fila, setFila] = useState<ItemFila[]>([])
  const [sessoes, setSessoes] = useState<Sessao[]>([])
  const [grupos, setGrupos] = useState<Grupo[]>([])
  const [carregado, setCarregado] = useState(false)
  const [tempoReal, setTempoReal] = useState(false)
  const [agora, setAgora] = useState(() => Date.now())

  const recarregarEstacoes = useCallback(async () => {
    setEstacoes(await Api.get<Estacao[]>("/api/estacoes/"))
  }, [])
  const recarregarClientes = useCallback(async () => {
    setClientes(await Api.get<Cliente[]>("/api/clientes/"))
  }, [])
  const recarregarFila = useCallback(async () => {
    setFila(await Api.get<ItemFila[]>("/api/estacoes/fila"))
  }, [])
  const recarregarSessoes = useCallback(async () => {
    setSessoes(await Api.get<Sessao[]>("/api/sessoes/ativas"))
  }, [])
  const recarregarGrupos = useCallback(async () => {
    setGrupos(await Api.get<Grupo[]>("/api/estacoes/grupos"))
  }, [])

  const recarregar = useCallback(async () => {
    await Promise.allSettled([
      recarregarEstacoes(),
      recarregarClientes(),
      recarregarFila(),
      recarregarSessoes(),
      recarregarGrupos(),
    ])
    setCarregado(true)
  }, [recarregarEstacoes, recarregarClientes, recarregarFila, recarregarSessoes, recarregarGrupos])

  // Carga inicial + atualização de segurança a cada 30s
  useEffect(() => {
    recarregar()
    const id = setInterval(recarregar, 30000)
    return () => clearInterval(id)
  }, [recarregar])

  // Tempo real: eventos do servidor pelo WebSocket, com reconexão a cada 3s
  const recarregarRef = useRef({ recarregar, recarregarFila, recarregarClientes, recarregarEstacoes })
  recarregarRef.current = { recarregar, recarregarFila, recarregarClientes, recarregarEstacoes }
  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let encerrado = false

    function conectar() {
      const protocolo = window.location.protocol === "https:" ? "wss" : "ws"
      ws = new WebSocket(`${protocolo}://${window.location.host}/ws/painel?token=${Api.token()}`)
      ws.onopen = () => setTempoReal(true)
      ws.onclose = () => {
        setTempoReal(false)
        if (!encerrado) timer = setTimeout(conectar, 3000)
      }
      ws.onmessage = (ev) => {
        const { evento } = JSON.parse(ev.data) as { evento: string }
        const r = recarregarRef.current
        if (evento === "sessao_iniciada" || evento === "sessao_encerrada") r.recarregar()
        else if (evento === "sessao_pausada" || evento === "sessao_retomada" || evento === "sessao_renovada") r.recarregar()
        else if (evento === "fila_atualizada") {
          r.recarregarFila()
          r.recarregarClientes()
        } else if (evento === "estacao_online" || evento === "estacao_offline") r.recarregarEstacoes()
      }
    }
    conectar()
    return () => {
      encerrado = true
      clearTimeout(timer)
      ws?.close()
    }
  }, [])

  // Relógio das contagens; quando uma sessão zera, recarrega para refletir o fim
  useEffect(() => {
    const id = setInterval(() => setAgora(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const zerouRef = useRef(new Set<number>())
  useEffect(() => {
    for (const s of sessoes) {
      if (restanteDaSessao(s.iniciada_em, s.tempo_total_segundos, agora) <= 0 && !zerouRef.current.has(s.id)) {
        zerouRef.current.add(s.id)
        recarregar()
      }
    }
  }, [agora, sessoes, recarregar])

  const valor = useMemo<Dados>(
    () => ({
      estacoes,
      clientes,
      fila,
      sessoes,
      grupos,
      carregado,
      tempoReal,
      agora,
      recarregar,
      recarregarClientes,
      recarregarFila,
      recarregarEstacoes,
      sessaoDaEstacao: (nome) => sessoes.find((s) => s.estacao_nome === nome),
    }),
    [estacoes, clientes, fila, sessoes, grupos, carregado, tempoReal, agora, recarregar,
     recarregarClientes, recarregarFila, recarregarEstacoes],
  )

  return <DadosContext.Provider value={valor}>{children}</DadosContext.Provider>
}

export function useDados(): Dados {
  const ctx = useContext(DadosContext)
  if (!ctx) throw new Error("useDados fora do ProvedorDados")
  return ctx
}
