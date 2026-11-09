import * as React from "react"
import { cn } from "@/lib/utils"

const base =
  "w-full rounded-lg border border-borda bg-superficie-2 px-3 py-2 text-sm text-texto outline-none transition-colors placeholder:text-texto-fraco focus:border-destaque disabled:cursor-not-allowed disabled:opacity-60"

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(base, "h-10", className)} {...props} />,
)
Input.displayName = "Input"

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => <select ref={ref} className={cn(base, "h-10", className)} {...props} />,
)
Select.displayName = "Select"

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(base, "resize-y", className)} {...props} />,
)
Textarea.displayName = "Textarea"

/** Hoje no relógio do computador, como AAAA-MM-DD (o formato do input date). */
export function hojeIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/** Primeiro dia com histórico possível nos relatórios (o VSCyber importado é de 2022). */
export const INICIO_RELATORIOS = "2000-01-01"

/**
 * Data que dá para digitar: só repassa (onChange) a data completa e dentro de
 * min..max. Digitar o ano dígito a dígito passa por 0002, 0020, 0202... e cada
 * um virava uma consulta de dois mil anos, que travava a tela. Fora do
 * intervalo o campo fica vermelho e, ao sair dele, volta ao último valor bom.
 */
export function InputData({
  value,
  onChange,
  min,
  max,
  className,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
  value: string
  onChange: (valor: string) => void
  min?: string
  max?: string
}) {
  const [texto, setTexto] = React.useState(value)
  React.useEffect(() => setTexto(value), [value])
  const valida = (v: string) => v === "" || (/^\d{4}-\d{2}-\d{2}$/.test(v) && (!min || v >= min) && (!max || v <= max))
  const ok = valida(texto)
  return (
    <input
      type="date"
      min={min}
      max={max}
      value={texto}
      aria-invalid={!ok || undefined}
      title={!ok ? (max && texto > max ? "Data depois do permitido" : "Data antes do permitido") : undefined}
      onChange={(e) => {
        const v = e.target.value
        setTexto(v)
        if (valida(v)) onChange(v)
      }}
      onBlur={() => !valida(texto) && setTexto(value)}
      className={cn(base, "h-10", !ok && "border-perigo focus:border-perigo", className)}
      {...props}
    />
  )
}

/** RG: só números e X (x vira X; o resto some enquanto digita). */
export function soRg(texto: string) {
  return texto.toUpperCase().replace(/[^0-9X]/g, "").slice(0, 20)
}

/** Rótulo + campo, empilhados. */
export function Campo({ rotulo, id, children }: { rotulo: string; id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs tracking-wider text-texto-suave uppercase">
        {rotulo}
      </label>
      {children}
    </div>
  )
}

export function Interruptor({
  id,
  ligado,
  aoMudar,
  rotulo,
}: {
  id: string
  ligado: boolean
  aoMudar: (v: boolean) => void
  rotulo: string
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={ligado}
      aria-label={rotulo}
      onClick={() => aoMudar(!ligado)}
      className={cn(
        "relative h-6 w-11 shrink-0 cursor-pointer rounded-full border border-borda transition-colors",
        ligado ? "bg-destaque" : "bg-superficie-3",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 left-0.5 size-[18px] rounded-full transition-transform",
          ligado ? "translate-x-5 bg-white" : "bg-texto-suave",
        )}
      />
    </button>
  )
}

export function MensagemErro({ children }: { children: React.ReactNode }) {
  return <p className="min-h-5 text-sm text-perigo" role="alert">{children}</p>
}
