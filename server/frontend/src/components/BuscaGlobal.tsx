import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { IconDeviceDesktop, IconSearch, IconUser } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useBuscaClientes } from "@/lib/buscaClientes"
import { useDados } from "@/lib/dados"
import { ITENS } from "@/components/Layout"
import { SeloStatus } from "@/components/ui/status"
import { cn } from "@/lib/utils"

interface Resultado {
  chave: string
  grupo: "Páginas" | "Estações" | "Clientes"
  rotulo: string
  detalhe?: React.ReactNode
  icone: React.ReactNode
  ir: () => void
}

/**
 * Busca global (Ctrl+K): telas, estações do piso e clientes. Estação e cliente
 * abrem no Painel (?estacao= / ?cliente=), que mostra a janela de cada um.
 */
export function BuscaGlobal({ aberta, aoFechar }: { aberta: boolean; aoFechar: () => void }) {
  if (!aberta) return null
  return <Caixa aoFechar={aoFechar} />
}

function Caixa({ aoFechar }: { aoFechar: () => void }) {
  const [termo, setTermo] = useState("")
  const [ativo, setAtivo] = useState(0)
  const navegar = useNavigate()
  const { estacoes } = useDados()
  const { clientes, carregando } = useBuscaClientes(termo, {}, { limite: 6 })
  const entrada = useRef<HTMLInputElement>(null)

  useEffect(() => entrada.current?.focus(), [])

  const resultados = useMemo<Resultado[]>(() => {
    const q = termo.trim().toLowerCase()
    const ir = (para: string) => () => {
      aoFechar()
      navegar(para)
    }
    const paginas = ITENS.filter((i) => (Api.ehAdmin() || !i.soAdmin) && i.rotulo.toLowerCase().includes(q)).map(
      ({ para, rotulo, Icone }): Resultado => ({
        chave: `p${para}`,
        grupo: "Páginas",
        rotulo,
        icone: <Icone size={16} />,
        ir: ir(para),
      }),
    )
    const maquinas = (q ? estacoes.filter((e) => e.nome.toLowerCase().includes(q)) : [])
      .slice(0, 6)
      .map(
        (e): Resultado => ({
          chave: `e${e.id}`,
          grupo: "Estações",
          rotulo: e.nome,
          detalhe: <SeloStatus status={e.status} />,
          icone: <IconDeviceDesktop size={16} />,
          ir: ir(`/?estacao=${e.id}`),
        }),
      )
    const pessoas = clientes.map(
      (c): Resultado => ({
        chave: `c${c.id}`,
        grupo: "Clientes",
        rotulo: c.nome,
        detalhe: <span className="text-xs text-texto-fraco">{c.login}</span>,
        icone: <IconUser size={16} />,
        ir: ir(`/?cliente=${c.id}`),
      }),
    )
    return [...paginas, ...maquinas, ...pessoas]
  }, [termo, estacoes, clientes, aoFechar, navegar])

  const indice = Math.min(ativo, Math.max(resultados.length - 1, 0))

  function aoTeclar(ev: React.KeyboardEvent) {
    if (ev.key === "Escape") aoFechar()
    else if (ev.key === "ArrowDown") {
      ev.preventDefault()
      setAtivo((indice + 1) % Math.max(resultados.length, 1))
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault()
      setAtivo((indice - 1 + resultados.length) % Math.max(resultados.length, 1))
    } else if (ev.key === "Enter") resultados[indice]?.ir()
  }

  return (
    <div
      className="animar-fade fixed inset-0 z-[1000] flex items-start justify-center bg-black/50 p-4 pt-[15vh] backdrop-blur-sm"
      onMouseDown={(ev) => ev.target === ev.currentTarget && aoFechar()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Buscar"
        onKeyDown={aoTeclar}
        className="animar-zoom flex max-h-[60vh] w-[560px] max-w-full flex-col overflow-hidden rounded-xl border border-borda bg-superficie-2 shadow-2xl"
      >
        <div className="flex items-center gap-2.5 border-b border-borda px-3.5">
          <IconSearch size={16} className="shrink-0 text-texto-fraco" />
          <input
            ref={entrada}
            value={termo}
            onChange={(ev) => {
              setTermo(ev.target.value)
              setAtivo(0)
            }}
            placeholder="Buscar telas, estações ou clientes..."
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-texto-fraco focus-visible:outline-none"
          />
          <kbd className="rounded border border-borda bg-superficie-3 px-1.5 text-[10px] text-texto-fraco">Esc</kbd>
        </div>
        <div className="overflow-y-auto p-1.5">
          {resultados.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-texto-fraco">
              {carregando ? "Buscando..." : "Nada encontrado."}
            </p>
          )}
          {resultados.map((r, i) => (
            <div key={r.chave}>
              {(i === 0 || resultados[i - 1].grupo !== r.grupo) && (
                <p className="px-2.5 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-texto-fraco/70 uppercase">
                  {r.grupo}
                </p>
              )}
              <button
                type="button"
                onMouseEnter={() => setAtivo(i)}
                onClick={r.ir}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all duration-200 ease-in-out",
                  i === indice ? "bg-texto/10 text-texto" : "text-texto-suave",
                )}
              >
                <span className="text-texto-fraco">{r.icone}</span>
                <span className="truncate">{r.rotulo}</span>
                {r.detalhe && <span className="ml-auto shrink-0">{r.detalhe}</span>}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
