import type { Piso } from "@/lib/tipos"
import { cn } from "@/lib/utils"

/** Piso escolhido neste navegador: o PC do atendimento infantil fica sempre no Infantil. */
export function lerPiso(): number | null {
  try {
    const id = Number(localStorage.getItem("pisoId"))
    return Number.isInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

export function gravarPiso(id: number) {
  try {
    localStorage.setItem("pisoId", String(id))
  } catch {
    /* sem storage: vale até recarregar */
  }
}

/**
 * A cor do piso escolhido vira --color-piso no :root; index.css deriva dela o
 * fundo e a borda (bg-piso-fundo, border-piso-borda, text-piso...).
 */
export function aplicarCorDoPiso(cor: string | undefined) {
  if (cor) document.documentElement.style.setProperty("--color-piso", cor)
  else document.documentElement.style.removeProperty("--color-piso")
}

/** Idade em anos hoje a partir de AAAA-MM-DD (null sem data). */
export function idade(nascimento: string | null, hoje = new Date()): number | null {
  if (!nascimento) return null
  const [a, m, d] = nascimento.split("-").map(Number)
  if (!a || !m || !d) return null
  const mes = hoje.getMonth() + 1
  return hoje.getFullYear() - a - (mes < m || (mes === m && hoje.getDate() < d) ? 1 : 0)
}

export function textoIdade(nascimento: string | null): string | null {
  const anos = idade(nascimento)
  return anos == null || anos < 0 ? null : `${anos} ${anos === 1 ? "ano" : "anos"}`
}

/**
 * Abas por piso. São o mesmo seletor do cabeçalho (useDados): trocar aqui troca
 * o piso de todas as telas, para nunca mostrarem pisos diferentes.
 */
export function AbasPiso({
  pisos,
  piso,
  aoTrocar,
  rotulo,
}: {
  pisos: Piso[]
  piso: Piso | null
  aoTrocar: (id: number) => void
  rotulo: string
}) {
  return (
    <div role="tablist" aria-label="Piso" className="flex flex-wrap gap-1">
      {pisos.map((p) => {
        const ativa = piso?.id === p.id
        return (
          <button
            key={p.id}
            type="button"
            role="tab"
            aria-selected={ativa}
            onClick={() => aoTrocar(p.id)}
            className={cn(
              "-mb-px flex items-center gap-2 rounded-t-lg border border-b-0 px-4 py-2 text-sm font-semibold transition-colors",
              ativa
                ? "border-piso-borda bg-piso-fundo text-texto"
                : "border-transparent text-texto-suave hover:text-texto",
            )}
          >
            <span className="size-2.5 rounded-full" style={{ background: p.cor }} />
            {rotulo} do {p.nome}
          </button>
        )
      })}
    </div>
  )
}

/** Etiqueta do piso, na cor dele. */
export function EtiquetaPiso({
  nome,
  cor,
  className,
}: {
  nome: string | null
  cor: string | null
  className?: string
}) {
  if (!nome) return null
  return (
    <span
      className={cn("rounded-full border px-1.5 text-[0.66rem] font-semibold whitespace-nowrap", className)}
      style={{ color: cor ?? undefined, borderColor: cor ?? undefined }}
    >
      {nome}
    </span>
  )
}
