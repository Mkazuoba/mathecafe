import { useEffect, useRef, useState } from "react"
import { IconChevronLeft, IconChevronRight, IconGripVertical } from "@tabler/icons-react"
import { cn } from "@/lib/utils"

/** Ordem das colunas e largura de cada uma, em % da largura da tela. */
export interface LayoutColunas<Id extends string> {
  ordem: Id[]
  larguras: Record<Id, number>
}

const LARGURA_MINIMA = 15 // %

function lerLayout<Id extends string>(chave: string, padrao: LayoutColunas<Id>): LayoutColunas<Id> {
  try {
    const salvo = JSON.parse(localStorage.getItem(chave) ?? "null") as LayoutColunas<Id> | null
    // só vale se tiver exatamente as mesmas colunas (uma coluna nova reseta o layout)
    const ids = [...padrao.ordem].sort().join()
    if (salvo && [...salvo.ordem].sort().join() === ids && salvo.ordem.every((id) => salvo.larguras[id] > 0)) return salvo
  } catch {
    /* padrão */
  }
  return padrao
}

/** Layout das colunas guardado no navegador, com mover, redimensionar e restaurar. */
export function useLayoutColunas<Id extends string>(chave: string, padrao: LayoutColunas<Id>) {
  const [layout, setLayoutBruto] = useState(() => lerLayout(chave, padrao))

  function setLayout(novo: LayoutColunas<Id>) {
    setLayoutBruto(novo)
    try {
      localStorage.setItem(chave, JSON.stringify(novo))
    } catch {
      /* sem storage: vale só até recarregar */
    }
  }

  function mover(id: Id, direcao: -1 | 1) {
    const ordem = [...layout.ordem]
    const i = ordem.indexOf(id)
    const j = i + direcao
    if (j < 0 || j >= ordem.length) return
    ;[ordem[i], ordem[j]] = [ordem[j], ordem[i]]
    setLayout({ ...layout, ordem })
  }

  const alterado = JSON.stringify(layout) !== JSON.stringify(padrao)
  return { layout, setLayout, mover, restaurar: () => setLayout(padrao), alterado }
}

const TIPO_COLUNA = "application/x-mathecafe-coluna"

/** Alça para arrastar a coluna para outro lugar (solte em cima de outra coluna). */
export function AlcaColuna({ id }: { id: string }) {
  return (
    <span
      draggable
      onDragStart={(ev) => {
        ev.dataTransfer.setData(TIPO_COLUNA, id)
        ev.dataTransfer.effectAllowed = "move"
      }}
      title="Arraste para trocar a coluna de lugar"
      aria-label="Arrastar a coluna"
      className="hidden shrink-0 cursor-grab rounded-md p-0.5 text-texto-fraco transition-colors hover:bg-texto/5 hover:text-texto active:cursor-grabbing lg:inline-flex"
    >
      <IconGripVertical size={15} />
    </span>
  )
}

/** Setas para trocar a coluna de lugar (só em tela larga). */
export function BotoesMover({ posicao, total, aoMover }: { posicao: number; total: number; aoMover: (d: -1 | 1) => void }) {
  const classe = "rounded p-0.5 text-texto-fraco hover:bg-superficie-3 hover:text-texto disabled:opacity-25 disabled:hover:bg-transparent"
  return (
    <span className="hidden shrink-0 items-center lg:flex">
      <button type="button" className={classe} title="Mover para a esquerda" disabled={posicao === 0} onClick={() => aoMover(-1)}>
        <IconChevronLeft size={14} />
      </button>
      <button type="button" className={classe} title="Mover para a direita" disabled={posicao === total - 1} onClick={() => aoMover(1)}>
        <IconChevronRight size={14} />
      </button>
    </span>
  )
}

function useTelaLarga() {
  const consulta = "(min-width: 1024px)" // lg do Tailwind
  const [larga, setLarga] = useState(() => window.matchMedia(consulta).matches)
  useEffect(() => {
    const mq = window.matchMedia(consulta)
    const mudou = () => setLarga(mq.matches)
    mq.addEventListener("change", mudou)
    return () => mq.removeEventListener("change", mudou)
  }, [])
  return larga
}

/**
 * Colunas lado a lado; arrastar a divisa muda a largura das duas vizinhas,
 * clique duplo na divisa volta as larguras ao padrão. Em tela estreita
 * as colunas ficam empilhadas.
 */
export function ColunasAjustaveis<Id extends string>({ layout, padrao, aoMudar, children }: {
  layout: LayoutColunas<Id>
  padrao: LayoutColunas<Id>
  aoMudar: (l: LayoutColunas<Id>) => void
  children: (id: Id, posicao: number) => React.ReactNode
}) {
  const larga = useTelaLarga()
  const caixa = useRef<HTMLDivElement>(null)
  const [arrastando, setArrastando] = useState<number | null>(null)

  function iniciarArrasto(ev: React.PointerEvent, i: number) {
    if (!caixa.current) return
    ev.preventDefault()
    const alvo = ev.currentTarget as HTMLElement
    alvo.setPointerCapture(ev.pointerId)
    const esquerda = layout.ordem[i]
    const direita = layout.ordem[i + 1]
    const inicioX = ev.clientX
    const larguraTotal = caixa.current.clientWidth
    const [l0, r0] = [layout.larguras[esquerda], layout.larguras[direita]]
    let atual = layout
    setArrastando(i)

    const mover = (e: PointerEvent) => {
      const delta = ((e.clientX - inicioX) / larguraTotal) * 100
      const l = Math.min(Math.max(l0 + delta, LARGURA_MINIMA), l0 + r0 - LARGURA_MINIMA)
      atual = { ...layout, larguras: { ...layout.larguras, [esquerda]: l, [direita]: l0 + r0 - l } }
      aoMudar(atual)
    }
    const soltar = () => {
      alvo.removeEventListener("pointermove", mover)
      alvo.removeEventListener("pointerup", soltar)
      alvo.removeEventListener("pointercancel", soltar)
      setArrastando(null)
      // arredonda para o layout salvo não guardar 33.33333
      aoMudar({
        ...atual,
        larguras: Object.fromEntries(Object.entries(atual.larguras).map(([k, v]) => [k, Math.round((v as number) * 10) / 10])) as Record<Id, number>,
      })
    }
    alvo.addEventListener("pointermove", mover)
    alvo.addEventListener("pointerup", soltar)
    alvo.addEventListener("pointercancel", soltar)
  }

  const [alvo, setAlvo] = useState<string | null>(null)
  function soltarColuna(ev: React.DragEvent, destino: number) {
    const id = ev.dataTransfer.getData(TIPO_COLUNA)
    setAlvo(null)
    if (!id || !layout.ordem.includes(id as Id)) return
    ev.preventDefault()
    const ordem = layout.ordem.filter((x) => x !== id)
    ordem.splice(destino, 0, id as Id)
    aoMudar({ ...layout, ordem })
  }

  return (
    <div
      ref={caixa}
      className={cn("flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-3 lg:flex-row lg:overflow-hidden", arrastando != null && "cursor-col-resize select-none")}
    >
      {layout.ordem.map((id, i) => (
        <div
          key={id}
          onDragOver={(ev) => {
            if (!ev.dataTransfer.types.includes(TIPO_COLUNA)) return
            ev.preventDefault()
            setAlvo(id)
          }}
          onDragLeave={(ev) => {
            if (!(ev.currentTarget as HTMLElement).contains(ev.relatedTarget as Node)) setAlvo(null)
          }}
          onDrop={(ev) => soltarColuna(ev, i)}
          style={larga ? { width: `calc(${layout.larguras[id]}% - ${(12 * (layout.ordem.length - 1)) / layout.ordem.length}px)` } : undefined}
          className={cn(
            "relative flex min-w-0 shrink-0 flex-col rounded-xl border border-borda bg-superficie/50 transition-shadow duration-200 lg:min-h-0",
            alvo === id && "ring-2 ring-destaque ring-offset-2 ring-offset-fundo",
          )}
        >
          {children(id, i)}
          {larga && i < layout.ordem.length - 1 && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-valuenow={Math.round(layout.larguras[id])}
              title="Arraste para mudar a largura (clique duplo volta ao padrão)"
              onPointerDown={(ev) => iniciarArrasto(ev, i)}
              onDoubleClick={() => aoMudar({ ...layout, larguras: padrao.larguras })}
              className={cn(
                "absolute top-0 -right-[10px] z-20 h-full w-2 cursor-col-resize rounded-full transition-colors hover:bg-destaque/40",
                arrastando === i && "bg-destaque/60",
              )}
            />
          )}
        </div>
      ))}
    </div>
  )
}
