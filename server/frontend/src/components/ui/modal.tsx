import { useEffect } from "react"
import { cn } from "@/lib/utils"

export function Modal({
  titulo,
  aberto,
  aoFechar,
  children,
  className,
}: {
  titulo: string
  aberto: boolean
  aoFechar: () => void
  children: React.ReactNode
  className?: string
}) {
  useEffect(() => {
    if (!aberto) return
    const aoTeclar = (ev: KeyboardEvent) => ev.key === "Escape" && aoFechar()
    document.addEventListener("keydown", aoTeclar)
    return () => document.removeEventListener("keydown", aoTeclar)
  }, [aberto, aoFechar])

  if (!aberto) return null
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4"
      onMouseDown={(ev) => ev.target === ev.currentTarget && aoFechar()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className={cn(
          "max-h-[85vh] w-full max-w-sm overflow-y-auto rounded-xl border border-borda bg-superficie p-7",
          className,
        )}
      >
        <h3 className="mb-5 text-lg font-semibold">{titulo}</h3>
        {children}
      </div>
    </div>
  )
}
