import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import { Api } from "@/lib/api"
import type { Estacao, Grupo, ItemFila, Piso, Sessao } from "@/lib/tipos"
import { aplicarCorDoPiso, gravarPiso, lerPiso } from "@/lib/piso"
import { restanteDaSessao } from "@/lib/tempo"

interface Dados {
  /** Pisos cadastrados (Configurações → Pisos). */
  pisos: Piso[]
  /** Piso do seletor do cabeçalho. Estações, grupos, fila, sessões e buscas de clientes vêm só dele. */
  piso: Piso | null
  trocarPiso: (id: number) => void
  recarregarPisos: () => Promise<void>
  estacoes: Estacao[]
  fila: ItemFila[]
  sessoes: Sessao[]
  grupos: Grupo[]
  /** Todos os grupos, de todos os pisos: para configurar grupos e mover estações entre eles. */
  todosGrupos: Grupo[]
  carregado: boolean
  tempoReal: boolean
  /** Muda a cada recarregarClientes: as buscas de clientes abertas refazem a consulta. */
  versaoClientes: number
  /** Relógio compartilhado (ms), atualizado a cada segundo para as contagens. */
  agora: number
  recarregar: () => Promise<void>
  recarregarClientes: () => Promise<void>
  recarregarFila: () => Promise<void>
  recarregarEstacoes: () => Promise<void>
  /** PCs instalados que esperam aprovação (Mapa → Novas estações), de todos os pisos. */
  pendentes: Estacao[]
  /** Estações cujo nome foi trocado no próprio PC e espera aprovação. */
  pedidosNome: Estacao[]
  recarregarPendentes: () => Promise<void>
  sessaoDaEstacao: (nome: string) => Sessao | undefined
}

const DadosContext = createContext<Dados | null>(null)

export function ProvedorDados({ children }: { children: React.ReactNode }) {
  const [pisos, setPisos] = useState<Piso[]>([])
  const [pisoId, setPisoId] = useState<number | null>(lerPiso)
  const trocarPiso = useCallback((id: number) => {
    gravarPiso(id)
    setPisoId(id)
  }, [])
  // o escolhido; se foi excluído (ou nunca escolheu), o padrão
  const piso = useMemo(
    () => pisos.find((p) => p.id === pisoId) ?? pisos.find((p) => p.padrao) ?? pisos[0] ?? null,
    [pisos, pisoId],
  )
  useEffect(() => aplicarCorDoPiso(piso?.cor), [piso])
  const [estacoes, setEstacoes] = useState<Estacao[]>([])
  const [versaoClientes, setVersaoClientes] = useState(0)
  const [fila, setFila] = useState<ItemFila[]>([])
  const [sessoes, setSessoes] = useState<Sessao[]>([])
  const [grupos, setGrupos] = useState<Grupo[]>([])
  const [carregado, setCarregado] = useState(false)
  const [tempoReal, setTempoReal] = useState(false)
  const [agora, setAgora] = useState(() => Date.now())

  const recarregarEstacoes = useCallback(async () => {
    setEstacoes(await Api.get<Estacao[]>("/api/estacoes/"))
  }, [])
  const [pendentes, setPendentes] = useState<Estacao[]>([])
  const [pedidosNome, setPedidosNome] = useState<Estacao[]>([])
  const recarregarPendentes = useCallback(async () => {
    // servidor antigo (sem a rota) devolve 404/422: sem pendentes
    const [p, n] = await Promise.all([
      Api.get<Estacao[]>("/api/estacoes/pendentes").catch(() => []),
      Api.get<Estacao[]>("/api/estacoes/pedidos_nome").catch(() => []),
    ])
    setPendentes(p)
    setPedidosNome(n)
  }, [])
  // Clientes (~43k) nunca sao carregados em massa: cada tela busca no
  // servidor com useBuscaClientes (lib/buscaClientes.ts).
  const recarregarClientes = useCallback(async () => {
    setVersaoClientes((v) => v + 1)
  }, [])
  const recarregarFila = useCallback(async () => {
    setFila(await Api.get<ItemFila[]>("/api/estacoes/fila"))
  }, [])
  const recarregarSessoes = useCallback(async () => {
    setSessoes(await Api.get<Sessao[]>("/api/sessoes/ativas"))
  }, [])
  const recarregarPisos = useCallback(async () => {
    setPisos(await Api.get<Piso[]>("/api/pisos/"))
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
      recarregarPisos(),
      recarregarPendentes(),
    ])
    setCarregado(true)
  }, [recarregarEstacoes, recarregarClientes, recarregarFila, recarregarSessoes, recarregarGrupos, recarregarPisos,
      recarregarPendentes])

  // Carga inicial + atualização de segurança a cada 30s
  useEffect(() => {
    recarregar()
    const id = setInterval(recarregar, 30000)
    return () => clearInterval(id)
  }, [recarregar])

  // Tempo real: eventos do servidor pelo WebSocket, com reconexão a cada 3s
  const recarregarRef = useRef({ recarregar, recarregarFila, recarregarClientes, recarregarEstacoes, recarregarPendentes })
  recarregarRef.current = { recarregar, recarregarFila, recarregarClientes, recarregarEstacoes, recarregarPendentes }
  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let encerrado = false

    function conectar() {
      const protocolo = window.location.protocol === "https:" ? "wss" : "ws"
      ws = new WebSocket(`${protocolo}://${window.location.host}/ws/painel?token=${Api.token()}`)
      // Expõe o WS globalmente para componentes que precisam escutar eventos
      // de captura de tela / streaming sem re-criar a conexão
      ;(window as any).__mathecafe_ws = ws
      ws.onopen = () => setTempoReal(true)
      ws.onclose = () => {
        setTempoReal(false)
        if ((window as any).__mathecafe_ws === ws) {
          (window as any).__mathecafe_ws = null
        }
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
        } else if (evento === "estacao_online" || evento === "estacao_offline") {
          r.recarregarEstacoes()
          r.recarregarPendentes()
        } else if (evento === "estacao_pendente") r.recarregarPendentes()
      }
    }
    conectar()
    return () => {
      encerrado = true
      clearTimeout(timer)
      if ((window as any).__mathecafe_ws === ws) {
        (window as any).__mathecafe_ws = null
      }
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
      if (restanteDaSessao(s, agora) <= 0 && !zerouRef.current.has(s.id)) {
        zerouRef.current.add(s.id)
        recarregar()
      }
    }
  }, [agora, sessoes, recarregar])

  // Tudo o que aparece nas telas é do piso escolhido
  const doPiso = useMemo(() => {
    const id = piso?.id
    const estacoesDoPiso = estacoes.filter((e) => e.piso_id === id)
    const ids = new Set(estacoesDoPiso.map((e) => e.id))
    const nomes = new Set(estacoesDoPiso.map((e) => e.nome))
    return {
      estacoes: estacoesDoPiso,
      // mapa antigo sem piso conta como o padrão (e Configurações → Grupos avisa)
      grupos: grupos.filter((g) => g.piso_id === id || (g.piso_id == null && !!piso?.padrao)),
      fila: fila.filter((f) => f.cliente_piso_id === id),
      // servidor antigo (até reiniciar) não manda estacao_id: vale o nome
      sessoes: sessoes.filter((s) => (s.estacao_id != null ? ids.has(s.estacao_id) : nomes.has(s.estacao_nome))),
    }
  }, [piso, estacoes, grupos, fila, sessoes])

  const valor = useMemo<Dados>(
    () => ({
      pisos,
      piso,
      trocarPiso,
      recarregarPisos,
      estacoes: doPiso.estacoes,
      versaoClientes,
      fila: doPiso.fila,
      sessoes: doPiso.sessoes,
      grupos: doPiso.grupos,
      todosGrupos: grupos,
      carregado,
      tempoReal,
      agora,
      recarregar,
      recarregarClientes,
      recarregarFila,
      recarregarEstacoes,
      pendentes,
      pedidosNome,
      recarregarPendentes,
      // o nome se repete entre os pisos (6.18): procura só nas sessões do piso
      sessaoDaEstacao: (nome) => doPiso.sessoes.find((s) => s.estacao_nome === nome),
    }),
    [pisos, piso, trocarPiso, recarregarPisos, doPiso, versaoClientes, sessoes, grupos, carregado, tempoReal, agora, recarregar,
     recarregarClientes, recarregarFila, recarregarEstacoes, pendentes, pedidosNome, recarregarPendentes],
  )

  return <DadosContext.Provider value={valor}>{children}</DadosContext.Provider>
}

export function useDados(): Dados {
  const ctx = useContext(DadosContext)
  if (!ctx) throw new Error("useDados fora do ProvedorDados")
  return ctx
}
