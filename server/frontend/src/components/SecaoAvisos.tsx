import { useCallback, useEffect, useState } from "react"
import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor, Select, Textarea } from "@/components/ui/campos"
import { Vazio } from "@/components/ui/status"

interface Aviso {
  id: number
  titulo: string
  texto: string
  ativo: boolean
  ordem: number
  /** chip no PC: alerta (âmbar), evento (violeta), info (azul) */
  tipo: TipoAviso
  /** livre, ex.: "16:00" (à direita do título no PC) */
  horario: string | null
  /** período em que aparece no PC (hora de Brasília, "AAAA-MM-DDTHH:MM"); null = sem limite */
  mostrar_de: string | null
  mostrar_ate: string | null
  situacao: "no_ar" | "agendado" | "encerrado" | "desligado"
}

/** "2026-11-25T18:00" -> "25/11 18:00" */
function dataCurta(d: string | null) {
  if (!d) return ""
  const [dia, hora] = d.split("T")
  const [, mes, dd] = dia.split("-")
  return `${dd}/${mes} ${hora}`
}

function SeloSituacao({ a }: { a: Aviso }) {
  if (a.situacao === "desligado") return <span className="text-xs text-texto-fraco">Desligado</span>
  if (a.situacao === "agendado")
    return (
      <span className="rounded bg-destaque-fundo px-1.5 py-0.5 text-xs text-destaque">Agendado: entra {dataCurta(a.mostrar_de)}</span>
    )
  if (a.situacao === "encerrado")
    return (
      <span className="rounded bg-superficie-3 px-1.5 py-0.5 text-xs text-texto-suave">
        Encerrado: saiu {dataCurta(a.mostrar_ate)}
      </span>
    )
  return (
    <span className="rounded bg-livre-fundo px-1.5 py-0.5 text-xs text-livre">
      No ar{a.mostrar_ate ? ` até ${dataCurta(a.mostrar_ate)}` : ""}
    </span>
  )
}

type TipoAviso = "alerta" | "evento" | "info"
const TIPOS: { valor: TipoAviso; rotulo: string }[] = [
  { valor: "info", rotulo: "Informativo" },
  { valor: "alerta", rotulo: "Alerta" },
  { valor: "evento", rotulo: "Evento" },
]

const CAMPO =
  "w-full rounded-md border border-borda bg-superficie px-2 py-1.5 text-sm outline-none focus:border-destaque"

/** Programação e avisos → Avisos: comunicados, regras do espaço e eventos do dia, à direita da tela de apps do PC. */
export function SecaoAvisos() {
  const avisar = useAvisos()
  const [itens, setItens] = useState<Aviso[] | null>(null)
  const [titulo, setTitulo] = useState("")
  const [texto, setTexto] = useState("")
  const [tipo, setTipo] = useState<TipoAviso>("info")
  const [horario, setHorario] = useState("")
  const [de, setDe] = useState("")
  const [ate, setAte] = useState("")

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
      await Api.post("/api/avisos/", {
        titulo: titulo.trim(),
        texto: texto.trim(),
        tipo,
        horario: horario.trim(),
        mostrar_de: de,
        mostrar_ate: ate,
      })
      setTitulo("")
      setTexto("")
      setHorario("")
      setDe("")
      setAte("")
    }, "Aviso publicado")
  }

  function salvar(a: Aviso, dados: Partial<Pick<Aviso, "titulo" | "texto" | "ativo" | "tipo" | "horario" | "mostrar_de" | "mostrar_ate">>) {
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
        nesta ordem. Iguais em todas as estações; os desligados não aparecem. Com início e fim, o aviso entra e sai
        sozinho da tela no dia e hora marcados.
      </p>

      <form onSubmit={criar} className="mb-6 flex flex-col gap-3 rounded-lg border border-borda bg-superficie-2 p-4">
        <Campo rotulo="Título" id="aviso-titulo">
          <Input id="aviso-titulo" maxLength={80} value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Ex.: Silêncio no espaço" />
        </Campo>
        <Campo rotulo="Texto" id="aviso-texto">
          <Textarea id="aviso-texto" maxLength={400} rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ex.: Use fones de ouvido para vídeos e músicas." />
        </Campo>
        <div className="flex gap-3">
          <Campo rotulo="Tipo" id="aviso-tipo">
            <Select id="aviso-tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoAviso)}>
              {TIPOS.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.rotulo}
                </option>
              ))}
            </Select>
          </Campo>
          <Campo rotulo="Horário (opcional)" id="aviso-horario">
            <Input id="aviso-horario" maxLength={20} value={horario} onChange={(e) => setHorario(e.target.value)} placeholder="Ex.: 16:00" />
          </Campo>
        </div>
        <div className="flex flex-wrap gap-3">
          <Campo rotulo="Mostrar a partir de (opcional)" id="aviso-de">
            <Input id="aviso-de" type="datetime-local" value={de} onChange={(e) => setDe(e.target.value)} />
          </Campo>
          <Campo rotulo="Até (opcional)" id="aviso-ate">
            <Input id="aviso-ate" type="datetime-local" value={ate} onChange={(e) => setAte(e.target.value)} />
          </Campo>
        </div>
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
              className={cn("flex items-start gap-3 rounded-lg border border-borda bg-superficie-2 p-2.5", (a.situacao === "desligado" || a.situacao === "encerrado") && "opacity-55")}
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
                <div className="flex gap-1.5">
                  <select
                    aria-label="Tipo do aviso"
                    value={a.tipo}
                    onChange={(e) => salvar(a, { tipo: e.target.value as TipoAviso })}
                    className={cn(CAMPO, "w-36")}
                  >
                    {TIPOS.map((t) => (
                      <option key={t.valor} value={t.valor}>
                        {t.rotulo}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    key={`h${a.horario ?? ""}`}
                    defaultValue={a.horario ?? ""}
                    maxLength={20}
                    aria-label="Horário do aviso"
                    placeholder="Horário (opcional)"
                    onBlur={(e) => e.target.value.trim() !== (a.horario ?? "") && salvar(a, { horario: e.target.value })}
                    className={cn(CAMPO, "w-40")}
                  />
                </div>
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-texto-suave">
                  <span>De</span>
                  <input
                    type="datetime-local"
                    key={`d${a.mostrar_de ?? ""}`}
                    defaultValue={a.mostrar_de ?? ""}
                    aria-label="Mostrar a partir de"
                    onBlur={(e) => e.target.value !== (a.mostrar_de ?? "") && salvar(a, { mostrar_de: e.target.value })}
                    className={cn(CAMPO, "w-48")}
                  />
                  <span>até</span>
                  <input
                    type="datetime-local"
                    key={`a${a.mostrar_ate ?? ""}`}
                    defaultValue={a.mostrar_ate ?? ""}
                    aria-label="Mostrar até"
                    onBlur={(e) => e.target.value !== (a.mostrar_ate ?? "") && salvar(a, { mostrar_ate: e.target.value })}
                    className={cn(CAMPO, "w-48")}
                  />
                  <SeloSituacao a={a} />
                </div>
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
