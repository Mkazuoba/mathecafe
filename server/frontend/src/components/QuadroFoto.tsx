import { useEffect, useRef, useState } from "react"
import { IconArrowsMove, IconCamera, IconUser } from "@tabler/icons-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"

/** px: a foto sai quadrada, deste lado, do ajuste (e assim vai ao servidor) */
export const LADO_FOTO = 480
/** px: o quadro de ajuste na tela */
const QUADRO = 280
const ZOOM_MAXIMO = 4

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
 * Foto grande com Enviar/Trocar, Ajustar e Remover: a mesma na ficha (salva na
 * hora) e no cadastro novo (vai junto ao criar). Toda foto passa pelo ajuste
 * (arrastar e aproximar) e sai quadrada, em JPEG de LADO_FOTO px.
 */
export function PainelFoto({
  url,
  alt,
  ocupado,
  aoEscolher,
  aoRemover,
}: {
  url: string | null
  alt: string
  ocupado?: boolean
  /** a foto já ajustada, em data URL */
  aoEscolher: (imagem: string) => void
  aoRemover: () => void
}) {
  const entrada = useRef<HTMLInputElement>(null)
  /** imagem aberta no ajuste (object URL de um arquivo novo ou a foto atual) */
  const [ajustando, setAjustando] = useState<string | null>(null)
  const [deArquivo, setDeArquivo] = useState(false)

  function fecharAjuste() {
    if (ajustando && deArquivo) URL.revokeObjectURL(ajustando)
    setAjustando(null)
  }

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
          if (!arquivo) return
          setDeArquivo(true)
          setAjustando(URL.createObjectURL(arquivo))
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
        <div className="flex gap-3 text-xs">
          <button
            type="button"
            disabled={ocupado}
            onClick={() => {
              setDeArquivo(false)
              setAjustando(url)
            }}
            className="inline-flex items-center gap-1 text-texto-fraco hover:text-texto"
          >
            <IconArrowsMove size={12} /> Ajustar
          </button>
          <button type="button" onClick={aoRemover} className="text-texto-fraco hover:text-perigo">
            Remover
          </button>
        </div>
      )}
      <AjustarFoto
        imagem={ajustando}
        aoCancelar={fecharAjuste}
        aoConfirmar={(dados) => {
          fecharAjuste()
          aoEscolher(dados)
        }}
      />
    </div>
  )
}

/** Janela de ajuste: arrasta a foto dentro do quadro e aproxima com o controle. */
function AjustarFoto({
  imagem,
  aoCancelar,
  aoConfirmar,
}: {
  imagem: string | null
  aoCancelar: () => void
  aoConfirmar: (dados: string) => void
}) {
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [erro, setErro] = useState("")
  const [zoom, setZoom] = useState(1)
  const [pos, setPos] = useState({ x: 0, y: 0 }) // canto da imagem dentro do quadro
  const arrasto = useRef<{ x: number; y: number; px: number; py: number } | null>(null)

  useEffect(() => {
    setImg(null)
    setErro("")
    if (!imagem) return
    const i = new Image()
    i.onload = () => {
      const base = Math.max(QUADRO / i.naturalWidth, QUADRO / i.naturalHeight)
      setZoom(1)
      setPos({ x: (QUADRO - i.naturalWidth * base) / 2, y: (QUADRO - i.naturalHeight * base) / 2 })
      setImg(i)
    }
    i.onerror = () => setErro("Não foi possível abrir essa imagem")
    i.src = imagem
  }, [imagem])

  // tamanho mostrado: cobre o quadro inteiro já no zoom 1
  const base = img ? Math.max(QUADRO / img.naturalWidth, QUADRO / img.naturalHeight) : 1
  const largura = img ? img.naturalWidth * base * zoom : 0
  const altura = img ? img.naturalHeight * base * zoom : 0

  function limitar(x: number, y: number, l = largura, a = altura) {
    // a imagem sempre cobre o quadro: sem faixa vazia na borda
    return { x: Math.min(0, Math.max(QUADRO - l, x)), y: Math.min(0, Math.max(QUADRO - a, y)) }
  }

  function mudarZoom(novo: number) {
    if (!img) return
    const l = img.naturalWidth * base * novo
    const a = img.naturalHeight * base * novo
    // aproxima mantendo o centro do quadro
    const cx = QUADRO / 2
    const x = cx - (cx - pos.x) * (novo / zoom)
    const y = cx - (cx - pos.y) * (novo / zoom)
    setZoom(novo)
    setPos(limitar(x, y, l, a))
  }

  function confirmar() {
    if (!img) return
    const canvas = document.createElement("canvas")
    canvas.width = LADO_FOTO
    canvas.height = LADO_FOTO
    const k = LADO_FOTO / QUADRO
    canvas.getContext("2d")!.drawImage(img, pos.x * k, pos.y * k, largura * k, altura * k)
    aoConfirmar(canvas.toDataURL("image/jpeg", 0.85))
  }

  return (
    <Modal titulo="Ajustar a foto" aberto={imagem != null} aoFechar={aoCancelar} className="max-w-sm">
      <div className="flex flex-col items-center gap-4">
        <p className="-mt-1 text-sm text-texto-suave">
          Arraste a foto para enquadrar o rosto e use o controle para aproximar.
        </p>
        <div
          className="relative cursor-grab touch-none overflow-hidden rounded-xl border border-borda bg-superficie-2 active:cursor-grabbing"
          style={{ width: QUADRO, height: QUADRO }}
          onPointerDown={(ev) => {
            ev.currentTarget.setPointerCapture(ev.pointerId)
            arrasto.current = { x: ev.clientX, y: ev.clientY, px: pos.x, py: pos.y }
          }}
          onPointerMove={(ev) => {
            const a = arrasto.current
            if (a) setPos(limitar(a.px + ev.clientX - a.x, a.py + ev.clientY - a.y))
          }}
          onPointerUp={() => (arrasto.current = null)}
          onPointerCancel={() => (arrasto.current = null)}
        >
          {img && (
            <img
              src={img.src}
              alt="Foto sendo ajustada"
              draggable={false}
              className="pointer-events-none absolute max-w-none select-none"
              style={{ left: pos.x, top: pos.y, width: largura, height: altura }}
            />
          )}
          {!img && !erro && (
            <span className="absolute inset-0 grid place-items-center text-sm text-texto-fraco">Carregando...</span>
          )}
          {erro && (
            <span className="absolute inset-0 grid place-items-center p-4 text-center text-sm text-perigo">{erro}</span>
          )}
        </div>
        <label className="flex w-full items-center gap-3 text-sm text-texto-suave">
          Aproximar
          <input
            type="range"
            min={1}
            max={ZOOM_MAXIMO}
            step={0.01}
            value={zoom}
            disabled={!img}
            onChange={(e) => mudarZoom(Number(e.target.value))}
            className="flex-1"
          />
        </label>
        <div className="flex w-full gap-2">
          <Button type="button" variant="outline" className="flex-1" onClick={aoCancelar}>
            Cancelar
          </Button>
          <Button type="button" className="flex-1" disabled={!img} onClick={confirmar}>
            Usar esta foto
          </Button>
        </div>
      </div>
    </Modal>
  )
}
