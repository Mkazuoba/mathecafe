import { useCallback, useEffect, useState } from "react"
import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor, Textarea } from "@/components/ui/campos"
import { Vazio } from "@/components/ui/status"

interface Aviso {
  id: number
  titulo: string
  texto: string
  ativo: boolean
  ordem: number
}

const CAMPO =
  "w-full rounded-md border border-borda bg-superficie px-2 py-1.5 text-sm outline-none focus:border-destaque"

/** Programação e avisos → Avisos: comunicados, regras do espaço e eventos do dia, à direita da tela de apps do PC. */
export function SecaoAvisos() {
  const avisar = useAvisos()
  const [itens, setItens] = useState<Aviso[] | null>(null)
  const [titulo, setTitulo] = useState("")
  const [texto, setTexto] = useState("")

  const carregar = useCallback(async () => {
    try {
      setItens(await Api.get<Aviso[]>("/api/avisos/"))
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }, [avisar])

  useEffect(() => {
    carregar()
  }, [carregar])

  async function executar(acao: () => Promise<unknown>, ok?: string) {
    try {
      await acao()
      if (ok) avisar(ok)
      await carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  async function criar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!titulo.trim() && !texto.trim()) return avisar("Escreva o título ou o texto do aviso", "erro")
    await executar(async () => {
      await Api.post("/api/avisos/", { titulo: titulo.trim(), texto: texto.trim() })
      setTitulo("")
      setTexto("")
    }, "Aviso publicado")
  }

  function salvar(a: Aviso, dados: Partial<Pick<Aviso, "titulo" | "texto" | "ativo">>) {
    executar(() => Api.put(`/api/avisos/${a.id}`, dados))
  }

  // troca de lugar com o vizinho
  function mover(i: number, delta: -1 | 1) {
    if (!itens) return
    const a = itens[i]
    const b = itens[i + delta]
    if (!a || !b) return
    executar(async () => {
      await Api.put(`/api/avisos/${a.id}`, { ordem: b.ordem })
      await Api.put(`/api/avisos/${b.id}`, { ordem: a.ordem === b.ordem ? a.ordem + delta : a.ordem })
    })
  }

  function apagar(a: Aviso) {
    if (!window.confirm(`Apagar o aviso "${a.titulo || a.texto.slice(0, 40)}"?`)) return
    executar(() => Api.del(`/api/avisos/${a.id}`), "Aviso apagado")
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Avisos da biblioteca</h2>
      <p className="mb-5 text-sm text-texto-suave">
        Comunicados, regras do espaço e eventos do dia. Aparecem à direita da tela de apps do computador do cliente,
        nesta ordem. Iguais em todas as estações; os desligados não aparecem.
      </p>

      <form onSubmit={criar} className="mb-6 flex flex-col gap-3 rounded-lg border border-borda bg-superficie-2 p-4">
        <Campo rotulo="Título" id="aviso-titulo">
          <Input id="aviso-titulo" maxLength={80} value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Ex.: Silêncio no espaço" />
        </Campo>
        <Campo rotulo="Texto" id="aviso-texto">
          <Textarea id="aviso-texto" maxLength={400} rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ex.: Use fones de ouvido para vídeos e músicas." />
        </Campo>
        <Button type="submit" className="gap-1.5 self-start">
          <IconPlus size={16} /> Publicar aviso
        </Button>
      </form>

      {!itens ? (
        <Vazio>Carregando...</Vazio>
      ) : !itens.length ? (
        <Vazio>Nenhum aviso ainda.</Vazio>
      ) : (
        <ul className="flex flex-col gap-2">
          {itens.map((a, i) => (
            <li
              key={a.id}
              className={cn("flex items-start gap-3 rounded-lg border border-borda bg-superficie-2 p-2.5", !a.ativo && "opacity-55")}
            >
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <input
                  type="text"
                  key={`t${a.titulo}`}
                  defaultValue={a.titulo}
                  maxLength={80}
                  aria-label="Título do aviso"
                  placeholder="Sem título"
                  onBlur={(e) => e.target.value.trim() !== a.titulo && salvar(a, { titulo: e.target.value })}
                  className={cn(CAMPO, "font-medium")}
                />
                <textarea
                  key={`x${a.texto}`}
                  defaultValue={a.texto}
                  maxLength={400}
                  rows={2}
                  aria-label="Texto do aviso"
                  placeholder="Sem texto"
                  onBlur={(e) => e.target.value.trim() !== a.texto && salvar(a, { texto: e.target.value })}
                  className={cn(CAMPO, "resize-y")}
                />
              </div>
              <Interruptor id={`aviso-ativo-${a.id}`} rotulo="Mostrar este aviso" ligado={a.ativo} aoMudar={(v) => salvar(a, { ativo: v })} />
              <div className="flex flex-col">
                <button type="button" title="Subir" disabled={i === 0} onClick={() => mover(i, -1)} className="rounded p-0.5 text-texto-fraco hover:text-texto disabled:opacity-25">
                  <IconArrowUp size={15} />
                </button>
                <button type="button" title="Descer" disabled={i === itens.length - 1} onClick={() => mover(i, 1)} className="rounded p-0.5 text-texto-fraco hover:text-texto disabled:opacity-25">
                  <IconArrowDown size={15} />
                </button>
              </div>
              <button type="button" title="Apagar" onClick={() => apagar(a)} className="rounded p-1.5 text-texto-fraco hover:text-perigo">
                <IconTrash size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
