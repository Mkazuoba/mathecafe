import { useRef } from "react"
import { IconCamera, IconUser } from "@tabler/icons-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

/** px: a foto é reduzida no navegador (lib/imagens.ts) antes de ir ao servidor */
export const LADO_FOTO = 480

/** A foto do cliente (ou o espaço vazio dela), grande na ficha e pequena no topo. */
export function QuadroFoto({ url, alt, tamanho }: { url: string | null; alt: string; tamanho: "pequena" | "grande" }) {
  const classe = tamanho === "grande" ? "size-40 rounded-xl" : "size-12 rounded-full"
  return url ? (
    <img src={url} alt={alt} className={cn(classe, "shrink-0 border border-borda object-cover")} />
  ) : (
    <div
      className={cn(
        classe,
        "flex shrink-0 items-center justify-center border border-dashed border-borda bg-superficie-2 text-texto-fraco",
      )}
    >
      <IconUser size={tamanho === "grande" ? 56 : 22} stroke={1.4} />
    </div>
  )
}

/**
 * Foto grande com Enviar/Trocar e Remover: a mesma na ficha (salva na hora) e
 * no cadastro novo (vai junto ao criar).
 */
export function PainelFoto({ url, alt, ocupado, aoEscolher, aoRemover }: {
  url: string | null
  alt: string
  ocupado?: boolean
  aoEscolher: (arquivo: File) => void
  aoRemover: () => void
}) {
  const entrada = useRef<HTMLInputElement>(null)
  return (
    <div className="flex flex-col items-center gap-2">
      <QuadroFoto url={url} alt={alt} tamanho="grande" />
      <input
        ref={entrada}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(ev) => {
          const arquivo = ev.target.files?.[0]
          ev.target.value = "" // permite escolher o mesmo arquivo de novo
          if (arquivo) aoEscolher(arquivo)
        }}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-40 gap-1.5"
        disabled={ocupado}
        onClick={() => entrada.current?.click()}
      >
        <IconCamera size={14} /> {ocupado ? "Enviando..." : url ? "Trocar foto" : "Enviar foto"}
      </Button>
      {url && (
        <button type="button" onClick={aoRemover} className="text-xs text-texto-fraco hover:text-perigo">
          Remover foto
        </button>
      )}
    </div>
  )
}
