import { useEffect, useRef, useState } from "react"
import { IconAdjustmentsHorizontal } from "@tabler/icons-react"
import { filtrosAtivos, type FiltrosClientes } from "@/lib/buscaClientes"
import { cn } from "@/lib/utils"
import { Select } from "@/components/ui/campos"

type CampoFiltro = "campo" | "modo" | "status" | "saldo" | "ordem"

const OPCOES: Record<CampoFiltro, { rotulo: string; opcoes: [string, string][] }> = {
  campo: { rotulo: "Buscar em", opcoes: [["tudo", "Nome e login"], ["nome", "Só nome"], ["login", "Só login"]] },
  modo: { rotulo: "Como", opcoes: [["contem", "Contém as palavras"], ["comeca", "Começa com"], ["exato", "Exatamente igual"]] },
  status: { rotulo: "Status", opcoes: [["todos", "Todos"], ["ativos", "Ativos"], ["inativos", "Inativos"]] },
  saldo: { rotulo: "Saldo", opcoes: [["todos", "Todos"], ["com", "Com saldo"], ["sem", "Sem saldo"]] },
  ordem: { rotulo: "Ordenar por", opcoes: [["nome", "Nome"], ["login", "Login"], ["saldo", "Saldo"], ["criado", "Data de cadastro"]] },
}

/** Botão que abre os filtros da busca de clientes, com selo de quantos estão ligados. */
export function FiltrosBusca({ valor, padrao, campos, aoMudar, className }: {
  valor: FiltrosClientes
  padrao: FiltrosClientes
  campos: CampoFiltro[]
  aoMudar: (f: FiltrosClientes) => void
  className?: string
}) {
  const [aberto, setAberto] = useState(false)
  const caixa = useRef<HTMLDivElement>(null)
  const ligados = filtrosAtivos(valor, padrao, campos)

  useEffect(() => {
    if (!aberto) return
    const fora = (ev: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(ev.target as Node)) setAberto(false)
    }
    const esc = (ev: KeyboardEvent) => ev.key === "Escape" && setAberto(false)
    document.addEventListener("mousedown", fora)
    document.addEventListener("keydown", esc)
    return () => {
      document.removeEventListener("mousedown", fora)
      document.removeEventListener("keydown", esc)
    }
  }, [aberto])

  return (
    <div ref={caixa} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        title="Filtros da busca"
        className={cn(
          "flex h-full items-center gap-1 rounded-md border px-2 text-sm",
          ligados ? "border-destaque text-destaque" : "border-borda text-texto-suave hover:text-texto",
        )}
      >
        <IconAdjustmentsHorizontal size={16} />
        {ligados > 0 && <span className="rounded-full bg-destaque px-1.5 text-[0.65rem] font-bold text-white">{ligados}</span>}
      </button>
      {aberto && (
        <div className="absolute top-full right-0 z-30 mt-1 flex w-64 flex-col gap-2.5 rounded-lg border border-borda bg-superficie p-3 shadow-xl">
          {campos.map((k) => (
            <label key={k} className="flex flex-col gap-1 text-xs text-texto-suave">
              {OPCOES[k].rotulo}
              <Select
                className="h-8 py-0 text-sm"
                value={String(valor[k])}
                onChange={(ev) => aoMudar({ ...valor, [k]: ev.target.value })}
              >
                {OPCOES[k].opcoes.map(([v, r]) => (
                  <option key={v} value={v}>
                    {r}
                  </option>
                ))}
              </Select>
            </label>
          ))}
          {campos.includes("ordem") && (
            <label className="flex items-center gap-2 text-xs text-texto-suave">
              <input type="checkbox" checked={valor.desc} onChange={(ev) => aoMudar({ ...valor, desc: ev.target.checked })} />
              Ordem decrescente
            </label>
          )}
          {ligados > 0 && (
            <button
              type="button"
              className="self-start text-xs text-destaque hover:underline"
              onClick={() => aoMudar({ ...valor, ...Object.fromEntries(campos.map((k) => [k, padrao[k]])), desc: padrao.desc })}
            >
              Limpar filtros
            </button>
          )}
        </div>
      )}
    </div>
  )
}
