import { useFotoDoCliente } from "@/lib/fotos"
import { cn } from "@/lib/utils"

/** Bolinha do cliente nas listas: a miniatura da foto ou, sem foto, as iniciais. */
export function AvatarCliente({
  cliente,
  className,
}: {
  cliente: { id: number; nome: string; tem_foto: boolean; foto_em: string | null }
  className?: string
}) {
  const url = useFotoDoCliente(cliente)
  return url ? (
    <img src={url} alt="" className={cn("size-8 shrink-0 rounded-full border border-borda object-cover", className)} />
  ) : (
    <span
      aria-hidden="true"
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full bg-superficie-3 text-xs font-semibold text-destaque uppercase",
        className,
      )}
    >
      {cliente.nome.slice(0, 2)}
    </span>
  )
}
