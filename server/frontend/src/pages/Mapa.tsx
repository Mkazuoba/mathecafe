import { useEffect, useMemo, useRef, useState } from "react"
import {
  IconArrowsMove,
  IconCheck,
  IconDeviceDesktopPlus,
  IconMessage,
  IconPencil,
  IconPlayerPlay,
  IconPlayerStop,
  IconPlus,
  IconPower,
  IconRefresh,
  IconWifi,
  IconWifiOff,
  IconX,
} from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAcoes } from "@/lib/acoes"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo, restanteDaSessao } from "@/lib/tempo"
import type { Estacao, Grupo, StatusEstacao } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { CabecalhoTela } from "@/components/Layout"
import { SeletorCliente, type ClienteResumo } from "@/components/SeletorCliente"
import { Button } from "@/components/ui/button"
import { Campo, Input, MensagemErro, Select, Textarea } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { ROTULO_STATUS, SeloStatus, Vazio } from "@/components/ui/status"

// ── Medidas do quadro (px) ────────────────────────────────────────────────────
const QUADRADO = 56 // a estação
const PASSO = 64 // estação + espaço, na grade automática
const GRADE = 8 // posições arredondadas para esta grade
const CABECALHO_ZONA = 36
const MARGEM_ZONA = 12
const ESPACO_ZONAS = 24
const LARGURA_MAXIMA = 1400 // zonas automáticas quebram a linha aqui
const SEM_GRUPO = -1
const FOLGA = 800 // no modo configuração, espaço livre à direita e embaixo para levar as zonas
const BORDA_ROLAGEM = 48 // arrastando a menos disso da beirada, a tela rola
const ZOOMS = [0.4, 0.5, 0.6, 0.75, 0.9, 1, 1.15, 1.3]

function lerZoom() {
  try {
    const z = Number(localStorage.getItem("mapa.zoom"))
    return ZOOMS.includes(z) ? z : 1
  } catch {
    return 1
  }
}

/** Rola a área quando o arrasto chega perto da beirada (para levar a zona além do que aparece). */
function rolarNaBorda(area: HTMLElement | null, ev: { clientX: number; clientY: number }) {
  if (!area) return
  const r = area.getBoundingClientRect()
  const passo = 24
  if (ev.clientX > r.right - BORDA_ROLAGEM) area.scrollLeft += passo
  else if (ev.clientX < r.left + BORDA_ROLAGEM) area.scrollLeft -= passo
  if (ev.clientY > r.bottom - BORDA_ROLAGEM) area.scrollTop += passo
  else if (ev.clientY < r.top + BORDA_ROLAGEM) area.scrollTop -= passo
}

// Cores do estado (o que a imagem de referência mostra nos quadrados)
const COR_QUADRADO: Record<StatusEstacao, string> = {
  livre: "border-livre bg-livre-fundo text-livre",
  ocupada: "border-ocupada bg-ocupada text-white",
  desligada: "border-borda bg-superficie-2 text-texto-fraco",
  manutencao: "border-manutencao bg-manutencao-fundo text-manutencao",
}
const COR_LEGENDA: Record<StatusEstacao, string> = {
  livre: "border-livre bg-livre-fundo",
  ocupada: "border-ocupada bg-ocupada",
  desligada: "border-borda bg-superficie-2",
  manutencao: "border-manutencao bg-manutencao-fundo",
}

interface Retangulo {
  x: number
  y: number
  largura: number
  altura: number
}
interface ZonaNoMapa {
  id: number // SEM_GRUPO para as estações sem grupo
  nome: string
  cor: string
  grupo: Grupo | null
  ret: Retangulo
  automatica: boolean
  estacoes: { estacao: Estacao; x: number; y: number }[]
}

const arredondar = (v: number) => Math.max(0, Math.round(v / GRADE) * GRADE)

/**
 * Cada zona é uma grade de quadrantes (PASSO px): uma estação por quadrante,
 * nunca uma em cima da outra. A posição salva vai para o quadrante mais
 * próximo (as do mapa antigo eram livres); se ele já tem dono, ou se a
 * estação ainda não tem posição, ela fica no primeiro quadrante livre.
 */
type Quadrante = { col: number; lin: number }
const chave = (q: Quadrante) => `${q.col},${q.lin}`
const quadranteDe = (x: number, y: number): Quadrante => ({
  col: Math.max(0, Math.round(x / PASSO)),
  lin: Math.max(0, Math.round(y / PASSO)),
})

function primeiroLivre(ocupados: Set<string>, colunas: number): Quadrante {
  for (let i = 0; ; i++) {
    const q = { col: i % colunas, lin: Math.floor(i / colunas) }
    if (!ocupados.has(chave(q))) return q
  }
}

function posicionar(estacoes: Estacao[], colunas: number) {
  const ocupados = new Set<string>()
  const ordenadas = estacoes.slice().sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR", { numeric: true }))
  const lugar = new Map<number, Quadrante>()
  // primeiro as que têm posição salva, depois as novas
  for (const e of ordenadas.filter((e) => e.pos_x || e.pos_y)) {
    let q = quadranteDe(e.pos_x, e.pos_y)
    if (q.col >= colunas || ocupados.has(chave(q))) q = primeiroLivre(ocupados, colunas)
    ocupados.add(chave(q))
    lugar.set(e.id, q)
  }
  for (const e of ordenadas.filter((e) => !e.pos_x && !e.pos_y)) {
    const q = primeiroLivre(ocupados, colunas)
    ocupados.add(chave(q))
    lugar.set(e.id, q)
  }
  return ordenadas.map((e) => {
    const q = lugar.get(e.id)!
    return { estacao: e, x: q.col * PASSO, y: q.lin * PASSO }
  })
}

const linhasDa = (altura: number) =>
  Math.max(1, Math.floor((altura - CABECALHO_ZONA - 2 * MARGEM_ZONA + (PASSO - QUADRADO)) / PASSO))
/** Tamanho exato da zona para tantas colunas e linhas de estações. */
const tamanhoPara = (colunas: number, linhas: number) => ({
  largura: 2 * MARGEM_ZONA + colunas * PASSO - (PASSO - QUADRADO),
  altura: CABECALHO_ZONA + 2 * MARGEM_ZONA + linhas * PASSO - (PASSO - QUADRADO),
})
const colunasDa = (largura: number) => Math.max(1, Math.floor((largura - 2 * MARGEM_ZONA + (PASSO - QUADRADO)) / PASSO))

/** As zonas do piso: a posição salva de cada uma, ou lado a lado. */
function montarZonas(grupos: Grupo[], estacoes: Estacao[], comSemGrupo: boolean): ZonaNoMapa[] {
  const lista: { id: number; nome: string; cor: string; grupo: Grupo | null; estacoes: Estacao[] }[] = grupos.map(
    (g) => ({ id: g.id, nome: g.nome, cor: g.cor, grupo: g, estacoes: estacoes.filter((e) => e.grupo_id === g.id) }),
  )
  const semGrupo = estacoes.filter((e) => e.grupo_id == null)
  if (comSemGrupo && semGrupo.length)
    lista.push({ id: SEM_GRUPO, nome: "Sem grupo", cor: "#64748b", grupo: null, estacoes: semGrupo })

  // zonas automáticas entram depois das salvas, da esquerda para a direita
  const salvas = lista.filter((z) => z.grupo?.zona)
  let cursorY = salvas.reduce((m, z) => Math.max(m, z.grupo!.zona!.y + z.grupo!.zona!.altura), 0)
  cursorY = salvas.length ? cursorY + ESPACO_ZONAS : ESPACO_ZONAS
  let cursorX = ESPACO_ZONAS
  let alturaLinha = 0

  return lista.map((z) => {
    const zona = z.grupo?.zona
    if (zona) {
      return { ...z, ret: zona, automatica: false, estacoes: posicionar(z.estacoes, colunasDa(zona.largura)) }
    }
    const colunas = Math.min(6, Math.max(2, Math.ceil(Math.sqrt(z.estacoes.length || 1))))
    const posicoes = posicionar(z.estacoes, colunas)
    const conteudoL = Math.max(colunas * PASSO, ...posicoes.map((p) => p.x + PASSO))
    const conteudoA = Math.max(PASSO, ...posicoes.map((p) => p.y + PASSO))
    const largura = Math.max(200, conteudoL + 2 * MARGEM_ZONA)
    const altura = CABECALHO_ZONA + conteudoA + 2 * MARGEM_ZONA
    if (cursorX + largura > LARGURA_MAXIMA && cursorX > ESPACO_ZONAS) {
      cursorX = ESPACO_ZONAS
      cursorY += alturaLinha + ESPACO_ZONAS
      alturaLinha = 0
    }
    const ret = { x: cursorX, y: cursorY, largura, altura }
    cursorX += largura + ESPACO_ZONAS
    alturaLinha = Math.max(alturaLinha, altura)
    return { ...z, ret, automatica: true, estacoes: posicoes }
  })
}

export default function Mapa() {
  const { estacoes, grupos, piso, sessaoDaEstacao, agora, recarregar, recarregarEstacoes, pendentes } = useDados()
  const [vendoPendentes, setVendoPendentes] = useState(false)
  const avisar = useAvisos()
  const admin = Api.ehAdmin()
  const [modoConfig, setModoConfig] = useState(false)
  const [aberta, setAberta] = useState<number | null>(null)
  const [novaEstacaoEm, setNovaEstacaoEm] = useState<number | null | undefined>(undefined)
  const [editandoZona, setEditandoZona] = useState<Grupo | "nova" | null>(null)
  // enquanto arrasta: a posição provisória da zona ou da estação
  const [provisorio, setProvisorio] = useState<{
    zona?: { id: number; ret: Retangulo }
    estacao?: { id: number; x: number; y: number }
  } | null>(null)
  const quadro = useRef<HTMLDivElement>(null)
  const area = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(lerZoom)
  function mudarZoom(novo: number) {
    setZoom(novo)
    try {
      localStorage.setItem("mapa.zoom", String(novo))
    } catch {
      /* sem storage */
    }
  }

  const zonas = useMemo(() => montarZonas(grupos, estacoes, !!piso?.padrao), [grupos, estacoes, piso])
  const contagem = useMemo(() => {
    const c: Record<StatusEstacao, number> = { livre: 0, ocupada: 0, desligada: 0, manutencao: 0 }
    for (const e of estacoes) c[e.status]++
    return c
  }, [estacoes])

  const retDe = (z: ZonaNoMapa) => (provisorio?.zona?.id === z.id ? provisorio.zona.ret : z.ret)
  const larguraConteudo = Math.max(0, ...zonas.map((z) => retDe(z).x + retDe(z).largura + ESPACO_ZONAS))
  const alturaConteudo = Math.max(0, ...zonas.map((z) => retDe(z).y + retDe(z).altura + ESPACO_ZONAS))
  // configurando, sobra espaço para levar as zonas para qualquer lado
  const larguraQuadro = Math.max(1000, larguraConteudo + (modoConfig ? FOLGA : 0))
  const alturaQuadro = Math.max(600, alturaConteudo + (modoConfig ? FOLGA : 0))

  function ajustarATela() {
    const r = area.current?.getBoundingClientRect()
    if (!r || !larguraConteudo) return
    const cabe = Math.min(r.width / larguraConteudo, r.height / alturaConteudo)
    mudarZoom([...ZOOMS].reverse().find((z) => z <= cabe) ?? ZOOMS[0])
  }

  const estacaoAberta = estacoes.find((e) => e.id === aberta)
  const ondeAberta = (() => {
    for (const z of zonas) {
      const p = z.estacoes.find((s) => s.estacao.id === aberta)
      if (p) return { x: retDe(z).x + MARGEM_ZONA + p.x, y: retDe(z).y + CABECALHO_ZONA + MARGEM_ZONA + p.y }
    }
    return null
  })()

  /** Grava a zona; as que ainda estão automáticas são gravadas junto, para não se moverem. */
  async function salvarZona(id: number, ret: Retangulo) {
    try {
      const pedidos = zonas
        .filter((z) => z.grupo && (z.id === id || z.automatica))
        .map((z) => Api.put(`/api/estacoes/grupos/${z.id}`, { zona: z.id === id ? ret : z.ret }))
      await Promise.all(pedidos)
      await recarregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setProvisorio(null)
    }
  }

  /**
   * Solta a estação num quadrante. Se ele tem outra estação, as duas trocam de
   * lugar (vinda de outra zona, a que estava lá vai para o primeiro livre).
   * Grava a zona inteira: nada pula de lugar depois.
   */
  async function soltarEstacao(e: Estacao, pontoNoQuadro: { x: number; y: number }) {
    const destino = zonas.find((z) => {
      const r = retDe(z)
      return (
        pontoNoQuadro.x >= r.x &&
        pontoNoQuadro.x <= r.x + r.largura &&
        pontoNoQuadro.y >= r.y &&
        pontoNoQuadro.y <= r.y + r.altura
      )
    })
    const origem = zonas.find((z) => z.estacoes.some((s) => s.estacao.id === e.id))
    if (!destino || !origem || (destino.id === SEM_GRUPO && e.grupo_id != null)) {
      setProvisorio(null)
      return
    }
    const r = retDe(destino)
    const colunas = colunasDa(r.largura)
    const alvo = quadranteDe(
      pontoNoQuadro.x - r.x - MARGEM_ZONA - QUADRADO / 2,
      pontoNoQuadro.y - r.y - CABECALHO_ZONA - MARGEM_ZONA - QUADRADO / 2,
    )
    alvo.col = Math.min(alvo.col, colunas - 1)
    const mesmaZona = destino.id === origem.id
    const deOnde = origem.estacoes.find((s) => s.estacao.id === e.id)!

    // posições finais da zona de destino (quadrantes únicos)
    const finais = new Map<number, Quadrante>()
    for (const s of destino.estacoes) {
      if (s.estacao.id !== e.id) finais.set(s.estacao.id, quadranteDe(s.x, s.y))
    }
    const dono = [...finais.entries()].find(([, q]) => chave(q) === chave(alvo))?.[0]
    finais.set(e.id, alvo)
    if (dono != null) {
      if (mesmaZona)
        finais.set(dono, quadranteDe(deOnde.x, deOnde.y)) // trocam de lugar
      else {
        const ocupados = new Set([...finais.entries()].filter(([id]) => id !== dono).map(([, q]) => chave(q)))
        finais.set(dono, primeiroLivre(ocupados, colunas))
      }
    }

    const mudancas = [...finais.entries()].filter(([id, q]) => {
      const atual = destino.estacoes.find((s) => s.estacao.id === id)
      const salvo = estacoes.find((x) => x.id === id)
      // grava tudo o que muda e o que ainda estava sem posição salva (para não pular)
      return (
        id === e.id ||
        !atual ||
        atual.x !== q.col * PASSO ||
        atual.y !== q.lin * PASSO ||
        !(salvo?.pos_x || salvo?.pos_y)
      )
    })
    try {
      await Promise.all(
        mudancas.map(([id, q]) => {
          // +1: o quadrante (0, 0) gravado como 0,0 seria lido como "sem posição"
          const pos = { pos_x: q.col * PASSO + 1, pos_y: q.lin * PASSO + 1 }
          return id === e.id && !mesmaZona
            ? Api.put(`/api/estacoes/${id}`, { grupo_id: destino.id, ...pos })
            : Api.put(`/api/estacoes/${id}/posicao`, pos)
        }),
      )
      if (!mesmaZona) avisar(`${e.nome} agora está em ${destino.nome}`)
      await recarregarEstacoes()
    } catch (err) {
      avisar((err as Error).message, "erro")
    } finally {
      setProvisorio(null)
    }
  }

  async function excluir(e: Estacao) {
    if (sessaoDaEstacao(e.nome)) return avisar(`A ${e.nome} está em uso: encerre a sessão antes de excluir`, "erro")
    if (!window.confirm(`Excluir a estação ${e.nome}?`)) return
    try {
      const r = await Api.del<{ desativada?: boolean }>(`/api/estacoes/${e.id}`)
      avisar(r.desativada ? "Estação removida do mapa (o histórico de uso foi mantido)" : "Estação excluída")
      await recarregarEstacoes()
    } catch (err) {
      avisar((err as Error).message, "erro")
    }
  }

  /** Ponto do mouse no quadro, em px do mapa (desfaz o zoom). */
  function pontoNoQuadro(ev: { clientX: number; clientY: number }) {
    const r = quadro.current!.getBoundingClientRect()
    return { x: (ev.clientX - r.left) / zoom, y: (ev.clientY - r.top) / zoom }
  }

  return (
    <>
      <CabecalhoTela titulo="Mapa">
        {/* legenda dos estados, com a contagem do piso */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-texto-suave">
          {(Object.keys(COR_LEGENDA) as StatusEstacao[]).map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span className={cn("size-3 rounded-[3px] border", COR_LEGENDA[s])} />
              <span className="capitalize">{ROTULO_STATUS[s]}</span>
              <strong className="text-texto tabular-nums">{contagem[s]}</strong>
            </span>
          ))}
        </div>
        <div className="flex-1" />
        {/* zoom: para montar (e ver inteiro) um mapa grande */}
        <div className="flex items-center gap-0.5 rounded-md border border-borda bg-superficie-2 p-0.5 text-xs">
          <button
            type="button"
            aria-label="Diminuir o zoom"
            disabled={zoom === ZOOMS[0]}
            onClick={() => mudarZoom(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)])}
            className="rounded px-2 py-1 text-texto-suave hover:text-texto disabled:opacity-40"
          >
            −
          </button>
          <span className="w-10 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            aria-label="Aumentar o zoom"
            disabled={zoom === ZOOMS[ZOOMS.length - 1]}
            onClick={() => mudarZoom(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)])}
            className="rounded px-2 py-1 text-texto-suave hover:text-texto disabled:opacity-40"
          >
            +
          </button>
          <button
            type="button"
            onClick={ajustarATela}
            className="rounded px-2 py-1 text-texto-suave hover:text-texto"
            title="Mostrar o mapa inteiro"
          >
            Ajustar
          </button>
        </div>
        {admin && pendentes.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 border-manutencao-borda bg-manutencao-fundo text-manutencao hover:brightness-110"
            onClick={() => setVendoPendentes(true)}
          >
            <IconDeviceDesktopPlus size={14} /> Novas estações
            <span className="rounded-full bg-manutencao px-1.5 text-[0.7rem] font-bold text-fundo tabular-nums">
              {pendentes.length}
            </span>
          </Button>
        )}
        {admin && modoConfig && (
          <Button size="sm" variant="outline" className="gap-1" onClick={() => setEditandoZona("nova")}>
            <IconPlus size={14} /> Zona
          </Button>
        )}
        {admin && (
          <Button
            variant={modoConfig ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setModoConfig((v) => !v)
              setAberta(null)
            }}
          >
            {modoConfig ? "Concluir configuração" : "Modo configuração"}
          </Button>
        )}
      </CabecalhoTela>

      <div
        ref={area}
        className="fundo-pontilhado relative min-h-0 flex-1 overflow-auto"
        onClick={() => setAberta(null)}
      >
        {!zonas.length ? (
          <div className="pt-16">
            <Vazio>Nenhuma zona neste piso.{admin && " Use o Modo configuração → + Zona para criar."}</Vazio>
          </div>
        ) : (
          // o quadro em px do mapa, encolhido/ampliado pelo zoom (a caixa de fora reserva o tamanho na tela)
          <div style={{ width: larguraQuadro * zoom, height: alturaQuadro * zoom }}>
            <div
              ref={quadro}
              className="relative origin-top-left"
              style={{ width: larguraQuadro, height: alturaQuadro, transform: `scale(${zoom})` }}
            >
              {zonas.map((z) => (
                <ZonaDoMapa
                  key={z.id}
                  zona={z}
                  ret={retDe(z)}
                  modoConfig={modoConfig}
                  zoom={zoom}
                  area={area}
                  aoMoverZona={(ret) => setProvisorio({ zona: { id: z.id, ret } })}
                  aoSoltarZona={(ret) => z.grupo && salvarZona(z.id, ret)}
                  aoEditar={() => z.grupo && setEditandoZona(z.grupo)}
                  aoNovaEstacao={() => setNovaEstacaoEm(z.grupo ? z.id : null)}
                >
                  {z.estacoes.map(({ estacao: e, x, y }) => {
                    const arrastando = provisorio?.estacao?.id === e.id
                    const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
                    return (
                      <QuadradoEstacao
                        key={e.id}
                        estacao={e}
                        x={arrastando ? provisorio.estacao!.x : x}
                        y={arrastando ? provisorio.estacao!.y : y}
                        arrastando={arrastando}
                        restante={sessao ? restanteDaSessao(sessao, agora) : null}
                        aberta={aberta === e.id}
                        modoConfig={modoConfig}
                        aoAbrir={() => setAberta(aberta === e.id ? null : e.id)}
                        aoArrastar={(ev) => {
                          rolarNaBorda(area.current, ev)
                          // posição provisória no sistema da zona de origem (segue o mouse)
                          const p = pontoNoQuadro(ev)
                          const r = retDe(z)
                          setProvisorio({
                            estacao: {
                              id: e.id,
                              x: p.x - r.x - MARGEM_ZONA - QUADRADO / 2,
                              y: p.y - r.y - CABECALHO_ZONA - MARGEM_ZONA - QUADRADO / 2,
                            },
                          })
                        }}
                        aoSoltar={(ev) => soltarEstacao(e, pontoNoQuadro(ev))}
                        aoExcluir={() => excluir(e)}
                      />
                    )
                  })}
                </ZonaDoMapa>
              ))}

              {estacaoAberta && ondeAberta && !modoConfig && (
                <CartaoEstacao
                  estacao={estacaoAberta}
                  x={
                    ondeAberta.x + QUADRADO + 10 + 320 > larguraQuadro
                      ? ondeAberta.x - 330
                      : ondeAberta.x + QUADRADO + 10
                  }
                  y={ondeAberta.y}
                  aoFechar={() => setAberta(null)}
                />
              )}
            </div>
          </div>
        )}
      </div>

      <ModalPendentes aberto={vendoPendentes && pendentes.length > 0} aoFechar={() => setVendoPendentes(false)} />
      <ModalNovaEstacao
        aberto={novaEstacaoEm !== undefined}
        grupoInicial={novaEstacaoEm ?? null}
        aoFechar={() => setNovaEstacaoEm(undefined)}
      />
      <ModalZona
        zona={editandoZona}
        noMapa={editandoZona && editandoZona !== "nova" ? zonas.find((z) => z.id === editandoZona.id) : undefined}
        novaEm={{ x: ESPACO_ZONAS, y: alturaConteudo }}
        aoFechar={() => setEditandoZona(null)}
      />
    </>
  )
}

// ── Zona ─────────────────────────────────────────────────────────────────────

function ZonaDoMapa({
  zona: z,
  ret,
  modoConfig,
  zoom,
  area,
  aoMoverZona,
  aoSoltarZona,
  aoEditar,
  aoNovaEstacao,
  children,
}: {
  zona: ZonaNoMapa
  ret: Retangulo
  modoConfig: boolean
  zoom: number
  area: React.RefObject<HTMLDivElement | null>
  aoMoverZona: (ret: Retangulo) => void
  aoSoltarZona: (ret: Retangulo) => void
  aoEditar: () => void
  aoNovaEstacao: () => void
  children: React.ReactNode
}) {
  const arrasto = useRef<{
    tipo: "mover" | "tamanho"
    x: number
    y: number
    rolX: number
    rolY: number
    ret: Retangulo
    atual: Retangulo
  } | null>(null)
  const ocupadas = z.estacoes.filter((s) => s.estacao.status === "ocupada").length
  const editavel = modoConfig && z.grupo != null
  // zona estreita (1 ou 2 colunas): cabeçalho enxuto, para os botões caberem
  const estreita = ret.largura < 170

  function iniciar(tipo: "mover" | "tamanho", ev: React.PointerEvent) {
    if (!editavel) return
    // pegar numa estação ou num botão não move a zona
    if (tipo === "mover" && (ev.target as HTMLElement).closest("button, [aria-label^='Estação ']")) return
    ev.stopPropagation()
    ev.currentTarget.setPointerCapture(ev.pointerId)
    const a = area.current
    arrasto.current = {
      tipo,
      x: ev.clientX,
      y: ev.clientY,
      rolX: a?.scrollLeft ?? 0,
      rolY: a?.scrollTop ?? 0,
      ret,
      atual: ret,
    }
  }
  function mover(ev: React.PointerEvent) {
    const a = arrasto.current
    if (!a) return
    rolarNaBorda(area.current, ev)
    // o quanto o mouse andou, mais o quanto a tela rolou, em px do mapa
    const dx = (ev.clientX - a.x + (area.current?.scrollLeft ?? 0) - a.rolX) / zoom
    const dy = (ev.clientY - a.y + (area.current?.scrollTop ?? 0) - a.rolY) / zoom
    a.atual =
      a.tipo === "mover"
        ? { ...a.ret, x: arredondar(a.ret.x + dx), y: arredondar(a.ret.y + dy) }
        : {
            ...a.ret,
            largura: Math.max(tamanhoPara(1, 1).largura, arredondar(a.ret.largura + dx)),
            altura: Math.max(tamanhoPara(1, 1).altura, arredondar(a.ret.altura + dy)),
          }
    aoMoverZona(a.atual)
  }
  function soltar() {
    const a = arrasto.current
    arrasto.current = null
    if (
      a &&
      (a.atual.x !== a.ret.x ||
        a.atual.y !== a.ret.y ||
        a.atual.largura !== a.ret.largura ||
        a.atual.altura !== a.ret.altura)
    )
      aoSoltarZona(a.atual)
  }

  return (
    <section
      aria-label={`Zona ${z.nome}`}
      className={cn(
        "absolute rounded-xl border",
        modoConfig && "border-dashed",
        editavel && "cursor-grab touch-none active:cursor-grabbing",
      )}
      title={editavel ? "Arraste para mover a zona" : undefined}
      onPointerDown={(ev) => iniciar("mover", ev)}
      onPointerMove={mover}
      onPointerUp={soltar}
      style={{
        left: ret.x,
        top: ret.y,
        width: ret.largura,
        height: ret.altura,
        background: `color-mix(in srgb, ${z.cor} 10%, var(--color-fundo))`,
        borderColor: `color-mix(in srgb, ${z.cor} 55%, var(--color-borda))`,
      }}
    >
      <div
        className={cn("flex items-center overflow-hidden text-sm select-none", estreita ? "gap-1 px-2" : "gap-2 px-3")}
        style={{ height: CABECALHO_ZONA }}
        title={estreita ? `${z.nome} · ${ocupadas}/${z.estacoes.length}` : undefined}
      >
        {editavel && !estreita && <IconArrowsMove size={14} className="shrink-0 text-texto-fraco" />}
        <span className="size-2.5 shrink-0 rounded-full" style={{ background: z.cor }} />
        <span className="min-w-0 truncate font-semibold">{z.nome}</span>
        {!estreita && (
          <span className="text-xs text-texto-fraco tabular-nums">
            {ocupadas}/{z.estacoes.length}
          </span>
        )}
        <div className="flex-1" />
        {modoConfig && (
          <>
            {z.grupo && (
              <button
                type="button"
                onPointerDown={(ev) => ev.stopPropagation()}
                onClick={aoEditar}
                aria-label={`Editar a zona ${z.nome}`}
                className="shrink-0 rounded p-0.5 text-texto-suave hover:text-texto"
              >
                <IconPencil size={14} />
              </button>
            )}
            <button
              type="button"
              onPointerDown={(ev) => ev.stopPropagation()}
              onClick={aoNovaEstacao}
              aria-label={`Nova estação em ${z.nome}`}
              title="Nova estação nesta zona"
              className="shrink-0 rounded p-0.5 text-texto-suave hover:text-texto"
            >
              <IconPlus size={14} />
            </button>
          </>
        )}
      </div>
      <div className="relative" style={{ margin: MARGEM_ZONA }}>
        {/* modo configuração: as vagas (quadrantes) da zona */}
        {modoConfig &&
          Array.from({ length: colunasDa(ret.largura) * linhasDa(ret.altura) }, (_, i) => {
            const col = i % colunasDa(ret.largura)
            const lin = Math.floor(i / colunasDa(ret.largura))
            return (
              <div
                key={i}
                aria-hidden="true"
                className="pointer-events-none absolute rounded-lg border border-dashed border-borda"
                style={{ left: col * PASSO, top: lin * PASSO, width: QUADRADO, height: QUADRADO }}
              />
            )
          })}
        {children}
      </div>
      {editavel && (
        <div
          role="presentation"
          title="Arraste para mudar o tamanho"
          className="absolute right-0 bottom-0 size-4 cursor-nwse-resize touch-none rounded-br-xl border-r-2 border-b-2"
          style={{ borderColor: z.cor }}
          onPointerDown={(ev) => iniciar("tamanho", ev)}
        />
      )}
    </section>
  )
}

// ── Estação ──────────────────────────────────────────────────────────────────

function QuadradoEstacao({
  estacao: e,
  x,
  y,
  arrastando,
  restante,
  aberta,
  modoConfig,
  aoAbrir,
  aoArrastar,
  aoSoltar,
  aoExcluir,
}: {
  estacao: Estacao
  x: number
  y: number
  arrastando: boolean
  restante: number | null
  aberta: boolean
  modoConfig: boolean
  aoAbrir: () => void
  aoArrastar: (ev: React.PointerEvent) => void
  aoSoltar: (ev: React.PointerEvent) => void
  aoExcluir: () => void
}) {
  const pressionado = useRef(false)
  const semConexao = !e.online && e.status !== "desligada"
  return (
    <div
      role={modoConfig ? undefined : "button"}
      tabIndex={modoConfig ? undefined : 0}
      aria-label={`Estação ${e.nome}, ${ROTULO_STATUS[e.status]}`}
      aria-expanded={modoConfig ? undefined : aberta}
      title={modoConfig ? "Arraste para mover (também para outra zona)" : undefined}
      onClick={(ev) => {
        ev.stopPropagation()
        if (!modoConfig) aoAbrir()
      }}
      onKeyDown={(ev) => !modoConfig && (ev.key === "Enter" || ev.key === " ") && aoAbrir()}
      onPointerDown={(ev) => {
        if (!modoConfig || (ev.target as HTMLElement).closest("button")) return
        ev.stopPropagation()
        ev.currentTarget.setPointerCapture(ev.pointerId)
        pressionado.current = true
      }}
      onPointerMove={(ev) => pressionado.current && aoArrastar(ev)}
      onPointerUp={(ev) => {
        if (!pressionado.current) return
        pressionado.current = false
        aoSoltar(ev)
      }}
      style={{ left: x, top: y, width: QUADRADO, height: QUADRADO }}
      className={cn(
        "absolute flex touch-none flex-col items-center justify-center rounded-lg border-2 font-semibold select-none",
        COR_QUADRADO[e.status],
        modoConfig ? "cursor-grab active:cursor-grabbing" : "cursor-pointer hover:brightness-110",
        arrastando && "z-20 opacity-80 shadow-lg",
        aberta && "ring-2 ring-texto ring-offset-2 ring-offset-fundo",
      )}
    >
      <span className="max-w-[52px] truncate text-[0.8rem] leading-tight">{e.nome}</span>
      {restante != null && (
        <span className="text-[0.6rem] leading-tight tabular-nums opacity-90">{formatarTempo(restante)}</span>
      )}
      {semConexao && (
        <IconWifiOff size={12} className="absolute top-0.5 right-0.5 opacity-80" aria-label="sem conexão" />
      )}
      {/* em uso nao se exclui (o servidor tambem recusa) */}
      {modoConfig && restante == null && e.status !== "ocupada" && (
        <button
          type="button"
          onClick={(ev) => {
            ev.stopPropagation()
            aoExcluir()
          }}
          aria-label={`Excluir estação ${e.nome}`}
          className="absolute -top-2 -right-2 flex size-5 cursor-pointer items-center justify-center rounded-full bg-perigo text-white"
        >
          <IconX size={12} />
        </button>
      )}
    </div>
  )
}

// ── Cartão da estação (clicar no quadrado) ───────────────────────────────────

function CartaoEstacao({
  estacao: e,
  x,
  y,
  aoFechar,
}: {
  estacao: Estacao
  x: number
  y: number
  aoFechar: () => void
}) {
  const { sessaoDaEstacao, agora, recarregarEstacoes } = useDados()
  const { encerrarSessao, reiniciarPc, desligarPc, enviarMensagem, liberarDireto } = useAcoes()
  const avisar = useAvisos()
  const admin = Api.ehAdmin()
  const sessao = e.status !== "manutencao" ? sessaoDaEstacao(e.nome) : undefined
  const [renomeando, setRenomeando] = useState(false)
  const [novoNome, setNovoNome] = useState(e.nome)

  async function renomear(ev: React.FormEvent) {
    ev.preventDefault()
    const nome = novoNome.trim()
    if (!nome || nome === e.nome) return setRenomeando(false)
    try {
      await Api.put(`/api/estacoes/${e.id}`, { nome })
      avisar(e.online ? `Estação renomeada para ${nome} (o computador já foi avisado)` : `Estação renomeada para ${nome}`)
      setRenomeando(false)
      await recarregarEstacoes()
    } catch (err) {
      avisar((err as Error).message, "erro")
    }
  }
  const [cliente, setCliente] = useState<ClienteResumo | null>(null)
  const [iniciando, setIniciando] = useState(false)
  const [escrevendo, setEscrevendo] = useState(false)
  const [texto, setTexto] = useState("")

  useEffect(() => {
    const aoTeclar = (ev: KeyboardEvent) => ev.key === "Escape" && aoFechar()
    document.addEventListener("keydown", aoTeclar)
    return () => document.removeEventListener("keydown", aoTeclar)
  }, [aoFechar])

  async function iniciar() {
    if (!cliente) return
    setIniciando(true)
    const ok = await liberarDireto(e.nome, cliente.id)
    setIniciando(false)
    if (ok) aoFechar()
  }

  async function ligar() {
    try {
      await Api.post(`/api/estacoes/${encodeURIComponent(e.nome)}/ligar`)
      avisar(`Comando de ligar enviado para ${e.nome}`)
    } catch (err) {
      avisar((err as Error).message, "erro")
    }
  }

  return (
    <div
      role="dialog"
      aria-label={`Estação ${e.nome}`}
      onClick={(ev) => ev.stopPropagation()}
      className="absolute z-30 w-80 rounded-xl border border-borda-forte bg-superficie p-4 shadow-2xl"
      style={{ left: Math.max(8, x), top: y }}
    >
      <div className="mb-3 flex items-center gap-2">
        {renomeando ? (
          <form onSubmit={renomear} className="flex min-w-0 flex-1 items-center gap-1">
            <Input
              aria-label="Novo nome da estação"
              className="h-8"
              maxLength={20}
              value={novoNome}
              onChange={(ev) => setNovoNome(ev.target.value)}
              onKeyDown={(ev) => ev.key === "Escape" && (ev.stopPropagation(), setRenomeando(false))}
              autoFocus
            />
            <Button type="submit" size="xs" aria-label="Salvar o nome">
              <IconCheck size={14} />
            </Button>
          </form>
        ) : (
          <>
            <span className="text-base font-semibold">{e.nome}</span>
            {admin && (
              <button
                type="button"
                onClick={() => {
                  setNovoNome(e.nome)
                  setRenomeando(true)
                }}
                aria-label="Renomear a estação"
                title="Renomear"
                className="text-texto-fraco hover:text-texto"
              >
                <IconPencil size={14} />
              </button>
            )}
          </>
        )}
        {!renomeando && <SeloStatus status={e.status} />}
        {!e.online && e.status !== "desligada" && (
          <IconWifiOff size={14} className="text-texto-fraco" aria-label="sem conexão" />
        )}
        <div className="flex-1" />
        <button type="button" onClick={aoFechar} aria-label="Fechar" className="text-texto-suave hover:text-texto">
          <IconX size={16} />
        </button>
      </div>
      {e.grupo_nome && <p className="-mt-2 mb-3 text-xs text-texto-fraco">{e.grupo_nome}</p>}

      {sessao ? (
        <>
          <div className="mb-3 rounded-lg bg-superficie-2 px-3 py-2.5">
            <div className="font-medium">{sessao.cliente_nome}</div>
            <div className="text-xs text-texto-fraco">{sessao.cliente_login}</div>
            <div className="mt-2 flex justify-between text-xs">
              <span className="text-texto-suave">
                Restante{" "}
                <strong className="text-texto tabular-nums">{formatarTempo(restanteDaSessao(sessao, agora))}</strong>
              </span>
              <span className="text-texto-suave">
                Total <span className="tabular-nums">{formatarTempo(sessao.tempo_total_segundos)}</span>
              </span>
            </div>
          </div>
          <Button
            variant="perigo"
            size="sm"
            className="mb-2 w-full gap-1.5"
            onClick={async () => (await encerrarSessao(sessao.id, e.nome)) && aoFechar()}
          >
            <IconPlayerStop size={14} /> Encerrar sessão
          </Button>
        </>
      ) : e.status === "livre" && e.online ? (
        <div className="mb-3 flex flex-col gap-2">
          <Campo rotulo="Iniciar sessão para" id={`mapa-cliente-${e.id}`}>
            <SeletorCliente
              id={`mapa-cliente-${e.id}`}
              valor={cliente}
              aoMudar={setCliente}
              placeholder="Digite o nome ou login"
            />
          </Campo>
          <Button size="sm" className="gap-1.5" disabled={!cliente || iniciando} onClick={iniciar}>
            <IconPlayerPlay size={14} /> {iniciando ? "Iniciando..." : "Iniciar"}
          </Button>
          <p className="text-xs text-texto-fraco">A sessão começa no computador sem o cliente digitar a senha.</p>
        </div>
      ) : !e.online ? (
        <p className="mb-3 text-sm text-texto-suave">
          {e.status === "desligada" ? "Computador desligado." : "Computador sem conexão com o servidor."}
        </p>
      ) : (
        <p className="mb-3 text-sm text-texto-suave">Estação em manutenção.</p>
      )}

      {/* ações do computador */}
      <div className="flex flex-wrap gap-1.5">
        {e.online ? (
          <>
            <Button size="xs" variant="outline" className="gap-1" onClick={() => setEscrevendo((v) => !v)}>
              <IconMessage size={13} /> Mensagem
            </Button>
            <Button size="xs" variant="outline" className="gap-1" onClick={() => reiniciarPc(e.nome)}>
              <IconRefresh size={13} /> Reiniciar
            </Button>
            <Button size="xs" variant="outline" className="gap-1" onClick={() => desligarPc(e.nome)}>
              <IconPower size={13} /> Desligar
            </Button>
          </>
        ) : (
          e.mac_address && (
            <Button size="xs" variant="outline" className="gap-1" onClick={ligar}>
              <IconWifi size={13} /> Ligar
            </Button>
          )
        )}
      </div>
      {escrevendo && (
        <form
          className="mt-2 flex flex-col gap-1.5"
          onSubmit={async (ev) => {
            ev.preventDefault()
            if (!texto.trim()) return
            await enviarMensagem(e.nome, texto.trim())
            setTexto("")
            setEscrevendo(false)
          }}
        >
          <Textarea
            rows={2}
            aria-label="Mensagem"
            value={texto}
            onChange={(ev) => setTexto(ev.target.value)}
            autoFocus
          />
          <Button type="submit" size="xs" disabled={!texto.trim()}>
            Enviar
          </Button>
        </form>
      )}
    </div>
  )
}

// ── Modais do modo configuração ──────────────────────────────────────────────

function ModalZona({
  zona,
  noMapa,
  novaEm,
  aoFechar,
}: {
  zona: Grupo | "nova" | null
  /** a zona como está no mapa (posição, tamanho, estações), ao editar */
  noMapa?: ZonaNoMapa
  /** onde a zona nova entra (embaixo das outras) */
  novaEm: { x: number; y: number }
  aoFechar: () => void
}) {
  const { piso, recarregar } = useDados()
  const avisar = useAvisos()
  const [nome, setNome] = useState("")
  const [cor, setCor] = useState("#6366f1")
  const [colunas, setColunas] = useState(4)
  const [linhas, setLinhas] = useState(2)
  const [erro, setErro] = useState("")
  const nova = zona === "nova"
  const nEstacoes = noMapa?.estacoes.length ?? 0

  useEffect(() => {
    if (!zona) return
    setErro("")
    setNome(nova ? "" : zona.nome)
    setCor(nova ? "#22c55e" : zona.cor)
    setColunas(noMapa ? colunasDa(noMapa.ret.largura) : 4)
    setLinhas(noMapa ? linhasDa(noMapa.ret.altura) : 2)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zona, nova])

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return setErro("Dê um nome à zona")
    if (colunas * linhas < nEstacoes)
      return setErro(
        `A zona tem ${nEstacoes} estações: ${colunas} × ${linhas} não cabe. Aumente as colunas ou as linhas.`,
      )
    try {
      if (nova) {
        if (!piso) return setErro("Escolha o piso no topo da tela")
        const params = new URLSearchParams({ nome: nome.trim(), cor, piso_id: String(piso.id) })
        const criada = await Api.post<Grupo>(`/api/estacoes/grupos?${params}`, {})
        await Api.put(`/api/estacoes/grupos/${criada.id}`, { zona: { ...novaEm, ...tamanhoPara(colunas, linhas) } })
        avisar(`Zona criada no piso ${piso.nome}`)
      } else if (zona) {
        const tamanho = tamanhoPara(colunas, linhas)
        const mudouTamanho = noMapa && (noMapa.ret.largura !== tamanho.largura || noMapa.ret.altura !== tamanho.altura)
        await Api.put(`/api/estacoes/grupos/${zona.id}`, {
          nome: nome.trim(),
          cor,
          ...(noMapa && (mudouTamanho || noMapa.automatica)
            ? { zona: { x: noMapa.ret.x, y: noMapa.ret.y, ...tamanho } }
            : {}),
        })
        avisar("Zona atualizada")
      }
      await recarregar()
      aoFechar()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo={nova ? "Nova zona" : "Editar zona"} aberto={zona != null} aoFechar={aoFechar}>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <Campo rotulo="Nome" id="zona-nome">
          <Input
            id="zona-nome"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="ex.: Sala de leitura"
            autoFocus
          />
        </Campo>
        <Campo rotulo="Cor" id="zona-cor">
          <input
            id="zona-cor"
            type="color"
            value={cor}
            onChange={(e) => setCor(e.target.value)}
            className="h-9 w-20 cursor-pointer rounded-md border border-borda bg-transparent p-0.5"
          />
        </Campo>
        <div>
          <span className="mb-1.5 block text-xs font-medium tracking-wide text-texto-suave uppercase">
            Tamanho (estações)
          </span>
          <div className="flex items-center gap-2 text-sm">
            <Select
              aria-label="Colunas"
              className="h-9 w-20"
              value={colunas}
              onChange={(e) => setColunas(Number(e.target.value))}
            >
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
            <span className="text-texto-suave">colunas ×</span>
            <Select
              aria-label="Linhas"
              className="h-9 w-20"
              value={linhas}
              onChange={(e) => setLinhas(Number(e.target.value))}
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
            <span className="text-texto-suave">linhas</span>
          </div>
          <p className="mt-1 text-xs text-texto-fraco">
            Ex.: 1 coluna para uma fileira junto à parede. Também dá para ajustar arrastando o canto da zona.
            {nEstacoes > 0 && ` Esta zona tem ${nEstacoes} estações.`}
          </p>
        </div>
        {nova && piso && (
          <p className="text-xs text-texto-fraco">
            A zona entra no piso {piso.nome} (o do topo da tela), embaixo das outras: depois é só arrastá-la.
          </p>
        )}
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button type="button" variant="outline" className="flex-1" onClick={aoFechar}>
            Cancelar
          </Button>
          <Button type="submit" className="flex-1">
            {nova ? "Criar zona" : "Salvar"}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function ModalNovaEstacao({
  aberto,
  grupoInicial,
  aoFechar,
}: {
  aberto: boolean
  grupoInicial: number | null
  aoFechar: () => void
}) {
  const { grupos, recarregarEstacoes } = useDados()
  const avisar = useAvisos()
  const [nome, setNome] = useState("")
  const [grupoId, setGrupoId] = useState("")
  const [erro, setErro] = useState("")

  useEffect(() => {
    if (aberto) {
      setNome("")
      setErro("")
      setGrupoId(String(grupoInicial ?? grupos[0]?.id ?? ""))
    }
  }, [aberto, grupoInicial, grupos])

  async function criar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return setErro("Informe o nome da estação")
    try {
      const params = new URLSearchParams({ nome: nome.trim() })
      if (grupoId) params.append("grupo_id", grupoId)
      await Api.post(`/api/estacoes/?${params}`)
      avisar("Estação criada")
      aoFechar()
      await recarregarEstacoes()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo="Nova estação" aberto={aberto} aoFechar={aoFechar}>
      <form onSubmit={criar} className="flex flex-col gap-4">
        <Campo rotulo="Nome da estação" id="est-nome">
          <Input
            id="est-nome"
            placeholder="ex: PC-01"
            autoComplete="off"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            autoFocus
          />
        </Campo>
        <Campo rotulo="Zona" id="est-grupo">
          <Select id="est-grupo" value={grupoId} onChange={(e) => setGrupoId(e.target.value)}>
            {grupos.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nome}
              </option>
            ))}
          </Select>
        </Campo>
        <p className="text-xs text-texto-fraco">
          Computadores com o agente 1.14 aparecem sozinhos em <strong>Novas estações</strong> depois da instalação.
          Cadastrar aqui só é preciso para agentes antigos, com o mesmo nome usado neles.
        </p>
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={aoFechar}>
            Cancelar
          </Button>
          <Button type="submit" className="flex-1">
            Criar
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ── Novas estações (PCs instalados esperando aprovação) ─────────────────────

function ModalPendentes({ aberto, aoFechar }: { aberto: boolean; aoFechar: () => void }) {
  const { pendentes, piso, grupos } = useDados()
  // todas as estacoes (de todos os pisos), para "Substitui a ..."
  const [existentes, setExistentes] = useState<Estacao[]>([])
  useEffect(() => {
    if (aberto) Api.get<Estacao[]>("/api/estacoes/").then(setExistentes, () => setExistentes([]))
  }, [aberto, pendentes])
  return (
    <Modal titulo="Novas estações" aberto={aberto} aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        <p className="text-sm text-texto-suave">
          Computadores instalados que ainda não foram aprovados. Até aprovar, ninguém faz login neles. Escolha o nome
          e a zona {piso ? `(zonas do piso ${piso.nome}; troque o piso no topo para ver outras)` : ""}.
        </p>
        {pendentes.map((p) => (
          <LinhaPendente key={p.id} estacao={p} grupos={grupos} existentes={existentes} />
        ))}
      </div>
    </Modal>
  )
}

/** "AD-3-2" -> "AD-3": o nome que o PC pediu, sem o sufixo que o servidor pôs. */
function semSufixo(nome: string) {
  return nome.replace(/-\d+$/, "")
}

function LinhaPendente({
  estacao: p,
  grupos,
  existentes,
}: {
  estacao: Estacao
  grupos: Grupo[]
  existentes: Estacao[]
}) {
  const { recarregarEstacoes, recarregarPendentes } = useDados()
  const avisar = useAvisos()
  // mesmo nome de uma estacao que ja existe: provavelmente o PC dela, formatado ou trocado
  const parecida = existentes.find((e) => e.nome === semSufixo(p.nome) && e.nome !== p.nome)
  const [substitui, setSubstitui] = useState(parecida ? String(parecida.id) : "")
  // a lista de estacoes chega depois: sugere assim que ela vier
  const idParecida = parecida?.id
  useEffect(() => {
    if (idParecida) setSubstitui((atual) => atual || String(idParecida))
  }, [idParecida])
  const alvo = existentes.find((e) => String(e.id) === substitui)
  const [nome, setNome] = useState(p.nome)
  const [grupoId, setGrupoId] = useState(String(grupos[0]?.id ?? ""))
  const [erro, setErro] = useState("")
  const [salvando, setSalvando] = useState(false)

  async function aprovar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!alvo && !nome.trim()) return setErro("Informe o nome da estação")
    setSalvando(true)
    setErro("")
    try {
      if (alvo) {
        await Api.post(`/api/estacoes/${p.id}/substituir`, { estacao_id: alvo.id })
        avisar(`Este computador agora é a ${alvo.nome} (mesmo lugar no mapa e histórico)`)
      } else {
        await Api.post(`/api/estacoes/${p.id}/aprovar`, {
          nome: nome.trim(),
          grupo_id: grupoId ? Number(grupoId) : null,
        })
        avisar(`Estação ${nome.trim()} aprovada`)
      }
      await Promise.all([recarregarEstacoes(), recarregarPendentes()])
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setSalvando(false)
    }
  }

  async function recusar() {
    if (
      !window.confirm(
        `Recusar ${p.nome}? O computador fica bloqueado e não aparece mais aqui. ` +
          "Para usar depois, cadastre uma estação com esse nome no Modo configuração.",
      )
    )
      return
    try {
      await Api.del(`/api/estacoes/${p.id}/pendente`)
      avisar(`${p.nome} recusada`)
      await recarregarPendentes()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <form onSubmit={aprovar} className="rounded-lg border border-borda bg-superficie-2 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs text-texto-fraco">
        {p.online ? (
          <span className="inline-flex items-center gap-1 text-livre">
            <IconWifi size={13} /> conectado agora
          </span>
        ) : (
          <span className="inline-flex items-center gap-1">
            <IconWifiOff size={13} /> desconectado
          </span>
        )}
        {p.versao_agente && <span>agente {p.versao_agente}</span>}
        {p.ip && <span>{p.ip}</span>}
      </div>
      <Campo rotulo="É o computador de" id={`pend-subst-${p.id}`}>
        <Select
          id={`pend-subst-${p.id}`}
          className="mb-2 h-9"
          value={substitui}
          onChange={(e) => setSubstitui(e.target.value)}
        >
          <option value="">Uma estação nova</option>
          {existentes.map((e) => (
            <option key={e.id} value={e.id}>
              Substitui a {e.nome}
              {e.grupo_nome ? ` (${e.grupo_nome})` : ""}
            </option>
          ))}
        </Select>
      </Campo>
      {alvo && (
        <p className="mb-2 text-xs text-texto-fraco">
          Para um computador formatado ou trocado: ele vira a {alvo.nome}, com o mesmo nome, zona, lugar no mapa e
          histórico. {alvo.online && <strong className="text-perigo">A {alvo.nome} está ligada agora: desligue o computador antigo antes.</strong>}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-2">
        {!alvo && (
          <>
        <Campo rotulo="Nome" id={`pend-nome-${p.id}`}>
          <Input
            id={`pend-nome-${p.id}`}
            className="h-9 w-40"
            maxLength={20}
            autoComplete="off"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </Campo>
        <Campo rotulo="Zona" id={`pend-zona-${p.id}`}>
          <Select
            id={`pend-zona-${p.id}`}
            className="h-9 w-44"
            value={grupoId}
            onChange={(e) => setGrupoId(e.target.value)}
          >
            {grupos.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nome}
              </option>
            ))}
            {!grupos.length && <option value="">Sem zona</option>}
          </Select>
        </Campo>
          </>
        )}
        <div className="flex flex-1 justify-end gap-1.5">
          <Button type="button" size="sm" variant="outline" onClick={recusar}>
            Recusar
          </Button>
          <Button type="submit" size="sm" className="gap-1" disabled={salvando}>
            <IconCheck size={14} /> {salvando ? "Salvando..." : alvo ? "Substituir" : "Aprovar"}
          </Button>
        </div>
      </div>
      <MensagemErro>{erro}</MensagemErro>
    </form>
  )
}
