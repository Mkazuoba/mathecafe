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
