import { useCallback, useEffect, useRef, useState } from "react"
import { IconArrowDown, IconArrowUp, IconPhotoPlus, IconTrash } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { reduzirImagem } from "@/lib/imagens"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor } from "@/components/ui/campos"
import { Vazio } from "@/components/ui/status"

interface Cartaz {
  id: number
  titulo: string
  ativo: boolean
  ordem: number
  versao: number
}

// Cartazes costumam ser verticais e com texto: reduz menos que a foto
const LADO_CARTAZ = 1280

/** Configurações → Programação: os cartazes que o agente mostra ao lado dos apps. */
export function SecaoProgramacao() {
  const avisar = useAvisos()
  const entrada = useRef<HTMLInputElement>(null)
  const [itens, setItens] = useState<Cartaz[] | null>(null)
  const [segundos, setSegundos] = useState("")
  const [enviando, setEnviando] = useState(false)

  const carregar = useCallback(async () => {
    try {
      const d = await Api.get<{ segundos: number; itens: Cartaz[] }>("/api/programacao/")
      setItens(d.itens)
      setSegundos(String(d.segundos))
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }, [avisar])

  useEffect(() => {
    carregar()
  }, [carregar])

  async function enviar(ev: React.ChangeEvent<HTMLInputElement>) {
    const arquivos = [...(ev.target.files ?? [])]
    ev.target.value = ""
    if (!arquivos.length) return
    setEnviando(true)
    try {
      for (const arquivo of arquivos) {
        const imagem = await reduzirImagem(arquivo, LADO_CARTAZ)
        // o nome do arquivo vira o título (dá para trocar depois)
        await Api.post("/api/programacao/", { titulo: arquivo.name.replace(/\.[^.]+$/, ""), imagem })
      }
      avisar(arquivos.length > 1 ? `${arquivos.length} cartazes adicionados` : "Cartaz adicionado")
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setEnviando(false)
    }
  }

  async function salvar(id: number, dados: Partial<Pick<Cartaz, "titulo" | "ativo">>) {
    try {
      await Api.put(`/api/programacao/${id}`, dados)
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  async function mover(i: number, direcao: -1 | 1) {
    if (!itens) return
    const ids = itens.map((x) => x.id)
    ;[ids[i], ids[i + direcao]] = [ids[i + direcao], ids[i]]
    try {
      await Api.put("/api/programacao/ordem", { ids })
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  async function apagar(c: Cartaz) {
    if (!window.confirm(`Apagar o cartaz "${c.titulo || "sem título"}"?`)) return
    try {
      await Api.del(`/api/programacao/${c.id}`)
      avisar("Cartaz apagado")
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  async function salvarTempo(ev: React.FormEvent) {
    ev.preventDefault()
    const n = Number(segundos)
    if (!Number.isInteger(n) || n < 3 || n > 120) return avisar("Tempo de cada cartaz: de 3 a 120 segundos", "erro")
    try {
      await Api.put("/api/programacao/config", { segundos: n })
      avisar("Tempo salvo")
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Programação</h2>
      <p className="mb-5 text-sm text-texto-suave">
        Cartazes da programação da biblioteca. Aparecem no computador do cliente, ao lado dos apps, durante a sessão,
        um de cada vez. Iguais em todas as estações; os desativados não aparecem.
      </p>

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <input ref={entrada} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={enviar} />
        <Button onClick={() => entrada.current?.click()} disabled={enviando} className="gap-1.5">
          <IconPhotoPlus size={16} /> {enviando ? "Enviando..." : "Adicionar cartazes"}
        </Button>
        <form onSubmit={salvarTempo} className="ml-auto flex items-end gap-2">
          <Campo rotulo="Segundos por cartaz" id="prog-segundos">
            <Input id="prog-segundos" type="number" min={3} max={120} value={segundos} onChange={(e) => setSegundos(e.target.value)} className="w-28" />
          </Campo>
          <Button type="submit" variant="outline">Salvar</Button>
        </form>
      </div>

      {!itens ? (
        <Vazio>Carregando...</Vazio>
      ) : !itens.length ? (
        <Vazio>Nenhum cartaz ainda. Clique em "Adicionar cartazes" (pode escolher vários de uma vez).</Vazio>
      ) : (
        <ul className="flex flex-col gap-2">
          {itens.map((c, i) => (
            <li
              key={c.id}
              className={cn(
                "flex items-center gap-3 rounded-lg border border-borda bg-superficie-2 p-2.5",
                !c.ativo && "opacity-55",
              )}
            >
              {/* a imagem é aberta (o agente não tem login), então dá para usar <img> */}
              <img
                src={`/api/programacao/${c.id}/imagem?v=${c.versao}`}
                alt={c.titulo || "Cartaz"}
                className="h-20 w-16 shrink-0 rounded border border-borda bg-superficie object-cover"
              />
              <input
                type="text"
                defaultValue={c.titulo}
                aria-label="Título do cartaz"
                placeholder="Sem título"
                onBlur={(e) => e.target.value.trim() !== c.titulo && salvar(c.id, { titulo: e.target.value })}
                className="min-w-0 flex-1 rounded-md border border-borda bg-superficie px-2 py-1.5 text-sm outline-none focus:border-destaque"
              />
              <Interruptor id={`prog-ativo-${c.id}`} rotulo="Mostrar este cartaz" ligado={c.ativo} aoMudar={(v) => salvar(c.id, { ativo: v })} />
              <div className="flex flex-col">
                <button type="button" title="Subir" disabled={i === 0} onClick={() => mover(i, -1)} className="rounded p-0.5 text-texto-fraco hover:text-texto disabled:opacity-25">
                  <IconArrowUp size={15} />
                </button>
                <button type="button" title="Descer" disabled={i === itens.length - 1} onClick={() => mover(i, 1)} className="rounded p-0.5 text-texto-fraco hover:text-texto disabled:opacity-25">
                  <IconArrowDown size={15} />
                </button>
              </div>
              <button type="button" title="Apagar" onClick={() => apagar(c)} className="rounded p-1.5 text-texto-fraco hover:text-perigo">
                <IconTrash size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
