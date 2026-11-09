import { useCallback, useEffect, useMemo, useState } from "react"
import { IconCheck, IconChevronLeft, IconChevronRight, IconPlus, IconSearch, IconX } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { AbasPiso } from "@/lib/piso"
import type { AppPermitido, Piso } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, Input, Interruptor, MensagemErro, Select } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { Vazio } from "@/components/ui/status"

type Status = "todos" | "ligados" | "desligados"
type Ordem = "nome" | "novos"
type AcaoMassa = "" | "ligar" | "desligar" | "excluir"

const POR_PAGINA = 23 // + o cartão de adicionar = 4 linhas de 6

/**
 * Configurações → Apps permitidos, por piso: a tela segue o piso do topo (as
 * abas são o mesmo seletor) e o interruptor de cada cartão liga ou desliga o
 * app só nesse piso. Grade de cartões com capa, filtros, busca e ações em massa.
 */
export function SecaoApps() {
  const avisar = useAvisos()
  const { pisos, piso, trocarPiso } = useDados()
  const [apps, setApps] = useState<AppPermitido[] | null>(null)
  const [busca, setBusca] = useState("")
  const [status, setStatus] = useState<Status>("todos")
  const [ordem, setOrdem] = useState<Ordem>("nome")
  const [pagina, setPagina] = useState(0)
  const [emMassa, setEmMassa] = useState(false)
  const [marcados, setMarcados] = useState<Set<number>>(() => new Set())
  const [acao, setAcao] = useState<AcaoMassa>("")
  const [aplicando, setAplicando] = useState(false)
  // null: fechado; "novo": cadastro; app: edição
  const [editando, setEditando] = useState<AppPermitido | "novo" | null>(null)

  const carregar = useCallback(async () => {
    setApps(await Api.get<AppPermitido[]>("/api/apps/"))
  }, [])
  useEffect(() => {
    carregar().catch((e) => avisar((e as Error).message, "erro"))
  }, [carregar, avisar])

  // pisos ausente: servidor ainda sem apps por piso (antes do reinício)
  const ligado = useCallback((a: AppPermitido) => !!piso && (a.pisos ?? []).includes(piso.id), [piso])

  const filtrados = useMemo(() => {
    const termo = busca.trim().toLowerCase()
    const lista = (apps ?? []).filter(
      (a) =>
        (!termo || a.nome.toLowerCase().includes(termo) || a.processo.toLowerCase().includes(termo)) &&
        (status === "todos" || (status === "ligados") === ligado(a)),
    )
    return ordem === "nome"
      ? lista.sort((x, y) => x.nome.localeCompare(y.nome, "pt-BR", { sensitivity: "base" }))
      : lista.sort((x, y) => y.id - x.id)
  }, [apps, busca, status, ordem, ligado])

  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA))
  const paginaAtual = Math.min(pagina, paginas - 1)
  const visiveis = filtrados.slice(paginaAtual * POR_PAGINA, (paginaAtual + 1) * POR_PAGINA)
  const filtrosLigados = busca.trim() !== "" || status !== "todos"
  const ligadosNoPiso = (apps ?? []).filter(ligado).length

  function limparFiltros() {
    setBusca("")
    setStatus("todos")
    setPagina(0)
  }

  async function ligarNoPiso(a: AppPermitido, sim: boolean) {
    if (!piso) return
    // muda na hora na tela; desfaz se o servidor recusar
    setApps(
      (lista) =>
        lista &&
        lista.map((x) =>
          x.id === a.id
            ? { ...x, pisos: sim ? [...(x.pisos ?? []), piso.id] : (x.pisos ?? []).filter((p) => p !== piso.id) }
            : x,
        ),
    )
    try {
      await Api.put(`/api/apps/${a.id}/pisos/${piso.id}`, { ligado: sim })
    } catch (e) {
      avisar((e as Error).message, "erro")
      await carregar()
    }
  }

  function marcar(id: number) {
    setMarcados((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  function ligarMassa(sim: boolean) {
    setEmMassa(sim)
    setMarcados(new Set())
    setAcao("")
  }

  async function aplicarMassa() {
    const ids = [...marcados]
    if (!ids.length || !acao || !piso) return
    const n = ids.length === 1 ? "1 app" : `${ids.length} apps`
    if (acao === "excluir" && !window.confirm(`Excluir ${n} dos apps permitidos (de todos os pisos)?`)) return
    setAplicando(true)
    let falhas = 0
    for (const id of ids) {
      try {
        if (acao === "excluir") await Api.del(`/api/apps/${id}`)
        else await Api.put(`/api/apps/${id}/pisos/${piso.id}`, { ligado: acao === "ligar" })
      } catch {
        falhas++
      }
    }
    setAplicando(false)
    avisar(
      falhas ? `${ids.length - falhas} de ${ids.length} feitos (${falhas} com erro)` : `Feito em ${n}`,
      falhas ? "erro" : undefined,
    )
    setMarcados(new Set())
    await carregar()
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Apps permitidos</h2>
      <p className="mb-4 text-sm text-texto-fraco">
        Cada piso tem os seus apps: o interruptor do cartão liga o app só no piso escolhido. Desligado, o app some do
        menu das estações daquele piso e é fechado se alguém o abrir. Um piso sem nenhum app ligado não bloqueia
        programas.
      </p>

      {/* abas por piso: o mesmo seletor do topo */}
      <div className="mb-4 border-b border-borda">
        <AbasPiso pisos={pisos} piso={piso} aoTrocar={trocarPiso} rotulo="Apps" />
      </div>
      {piso && (
        <p className="mb-3 text-sm text-texto-suave">
          {ligadosNoPiso} de {apps?.length ?? 0} {apps?.length === 1 ? "app ligado" : "apps ligados"} no piso{" "}
          {piso.nome}.
        </p>
      )}

      {/* filtros numa linha */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative">
          <IconSearch
            size={14}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-texto-fraco"
          />
          <Input
            type="search"
            aria-label="Buscar app pelo nome"
            placeholder="Buscar pelo nome"
            value={busca}
            onChange={(e) => {
              setBusca(e.target.value)
              setPagina(0)
            }}
            className="h-9 w-52 pl-8"
          />
        </div>
        <div
          role="radiogroup"
          aria-label="Situação no piso"
          className="flex rounded-lg border border-borda bg-superficie-2 p-0.5 text-sm"
        >
          {(
            [
              ["todos", "Todos"],
              ["ligados", "Ligados"],
              ["desligados", "Desligados"],
            ] as const
          ).map(([v, rotulo]) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={status === v}
              onClick={() => {
                setStatus(v)
                setPagina(0)
              }}
              className={cn(
                "rounded-md px-3 py-1",
                status === v ? "bg-destaque text-white" : "text-texto-suave hover:text-texto",
              )}
            >
              {rotulo}
            </button>
          ))}
        </div>
        {filtrosLigados && (
          <button
            type="button"
            onClick={limparFiltros}
            className="inline-flex items-center gap-0.5 text-xs font-medium text-perigo"
          >
            Limpar <IconX size={12} />
          </button>
        )}
        <div className="flex-1" />
        <label className="flex cursor-pointer items-center gap-2 text-xs text-texto-suave">
          <span className="text-right leading-tight">
            Ações em massa
            <span className="block text-[0.66rem] text-texto-fraco">marque vários cartões</span>
          </span>
          <Interruptor id="apps-massa" rotulo="Ações em massa" ligado={emMassa} aoMudar={ligarMassa} />
        </label>
        <Select
          aria-label="Ordenar"
          value={ordem}
          onChange={(e) => setOrdem(e.target.value as Ordem)}
          className="h-9 w-40"
        >
          <option value="nome">Nome (A a Z)</option>
          <option value="novos">Mais novos primeiro</option>
        </Select>
      </div>

      {emMassa && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-borda bg-superficie-2 px-3 py-2 text-sm">
          <span className="font-medium">
            {marcados.size ? `${marcados.size} marcado(s)` : "Clique nos cartões para marcar"}
          </span>
          <button
            type="button"
            className="text-xs text-texto-suave hover:text-texto"
            onClick={() => setMarcados(new Set(visiveis.map((a) => a.id)))}
          >
            Marcar todos da página
          </button>
          <div className="flex-1" />
          <Select
            aria-label="Ação"
            value={acao}
            onChange={(e) => setAcao(e.target.value as AcaoMassa)}
            className="h-8 w-52 py-0"
          >
            <option value="">Escolha a ação...</option>
            <option value="ligar">Ligar no piso {piso?.nome}</option>
            <option value="desligar">Desligar no piso {piso?.nome}</option>
            <option value="excluir">Excluir (de todos os pisos)</option>
          </Select>
          <Button
            size="sm"
            disabled={!marcados.size || !acao || aplicando}
            onClick={aplicarMassa}
            variant={acao === "excluir" ? "perigo" : "default"}
          >
            {aplicando ? "..." : "Aplicar"}
          </Button>
        </div>
      )}

      {apps === null ? (
        <Vazio>Carregando...</Vazio>
      ) : (
        <>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
            {paginaAtual === 0 && (
              <button
                type="button"
                onClick={() => setEditando("novo")}
                className="flex aspect-[3/4] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-borda-forte bg-superficie-2 p-4 text-center text-sm text-texto-suave hover:border-destaque hover:text-texto"
              >
                <IconPlus size={26} />
                <span className="font-medium">Adicionar app</span>
                <span className="text-xs text-texto-fraco">
                  Entra ligado no piso {piso?.nome}; nos outros, ligue pelo interruptor
                </span>
              </button>
            )}
            {visiveis.map((a) => (
              <CartaoApp
                key={a.id}
                app={a}
                ligado={ligado(a)}
                outrosPisos={pisos.filter((p) => p.id !== piso?.id && (a.pisos ?? []).includes(p.id))}
                emMassa={emMassa}
                marcado={marcados.has(a.id)}
                aoClicar={() => (emMassa ? marcar(a.id) : setEditando(a))}
                aoAlternar={() => ligarNoPiso(a, !ligado(a))}
              />
            ))}
          </div>
          {!filtrados.length && (
            <p className="mt-4 text-sm text-texto-fraco">
              {apps.length ? "Nenhum app com esses filtros." : "Nenhum app cadastrado ainda."}
            </p>
          )}
          {paginas > 1 && (
            <nav aria-label="Páginas" className="mt-5 flex items-center justify-center gap-1">
              <button
                type="button"
                aria-label="Página anterior"
                disabled={paginaAtual === 0}
                onClick={() => setPagina(paginaAtual - 1)}
                className="rounded-md p-1.5 text-texto-suave hover:text-texto disabled:opacity-30"
              >
                <IconChevronLeft size={16} />
              </button>
              {Array.from({ length: paginas }, (_, i) => (
                <button
                  key={i}
                  type="button"
                  aria-current={i === paginaAtual ? "page" : undefined}
                  onClick={() => setPagina(i)}
                  className={cn(
                    "size-8 rounded-full text-sm",
                    i === paginaAtual ? "bg-destaque text-white" : "text-texto-suave hover:text-texto",
                  )}
                >
                  {i + 1}
                </button>
              ))}
              <button
                type="button"
                aria-label="Próxima página"
                disabled={paginaAtual === paginas - 1}
                onClick={() => setPagina(paginaAtual + 1)}
                className="rounded-md p-1.5 text-texto-suave hover:text-texto disabled:opacity-30"
              >
                <IconChevronRight size={16} />
              </button>
            </nav>
          )}
        </>
      )}
      <ModalApp app={editando} piso={piso} aoFechar={() => setEditando(null)} aoSalvar={carregar} />
    </div>
  )
}

/** Cartão em pé: a capa cobre o cartão, o nome embaixo, o interruptor (do piso) em cima. */
function CartaoApp({
  app: a,
  ligado,
  outrosPisos,
  emMassa,
  marcado,
  aoClicar,
  aoAlternar,
}: {
  app: AppPermitido
  ligado: boolean
  outrosPisos: Piso[]
  emMassa: boolean
  marcado: boolean
  aoClicar: () => void
  aoAlternar: () => void
}) {
  const [semCapa, setSemCapa] = useState(false)
  const capa = a.imagem_url && !semCapa ? a.imagem_url : null
  return (
    <div
      role="button"
      tabIndex={0}
      title={emMassa ? "Marcar" : `Editar ${a.nome}`}
      onClick={aoClicar}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          aoClicar()
        }
      }}
      className={cn(
        "group relative aspect-[3/4] cursor-pointer overflow-hidden rounded-xl border bg-superficie-3 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-destaque",
        marcado ? "border-destaque ring-2 ring-destaque" : "border-borda",
      )}
    >
      {capa ? (
        <img
          src={capa}
          alt=""
          onError={() => setSemCapa(true)}
          className={cn(
            "absolute inset-0 size-full object-cover transition-[filter,opacity]",
            !ligado && "opacity-40 grayscale",
          )}
        />
      ) : (
        <div
          className={cn(
            "absolute inset-0 flex items-center justify-center bg-gradient-to-br from-superficie-3 to-superficie-2 text-5xl font-bold text-texto-fraco",
            !ligado && "opacity-40",
          )}
        >
          {a.nome.slice(0, 1).toUpperCase()}
        </div>
      )}
      {/* degradê para o nome ler em cima de qualquer capa */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 to-transparent" />

      <div className="absolute inset-x-2 top-2 flex items-start justify-between gap-1">
        {/* em que outros pisos o app também está ligado */}
        <div className="flex min-w-0 flex-wrap gap-1">
          {outrosPisos.map((p) => (
            <span
              key={p.id}
              title={`Ligado também no piso ${p.nome}`}
              className="inline-flex max-w-full items-center gap-1 truncate rounded bg-black/55 px-1.5 py-0.5 text-[0.62rem] font-medium text-white"
            >
              <span className="size-1.5 shrink-0 rounded-full" style={{ background: p.cor }} />
              {p.nome}
            </span>
          ))}
        </div>
        {emMassa ? (
          <span
            className={cn(
              "flex size-5 shrink-0 items-center justify-center rounded border-2",
              marcado ? "border-destaque bg-destaque text-white" : "border-white/80 bg-black/40",
            )}
          >
            {marcado && <IconCheck size={13} />}
          </span>
        ) : (
          // o interruptor liga e desliga no piso, sem abrir a edição
          <button
            type="button"
            role="switch"
            aria-checked={ligado}
            aria-label={`${ligado ? "Desligar" : "Ligar"} ${a.nome} neste piso`}
            onClick={(e) => {
              e.stopPropagation()
              aoAlternar()
            }}
            className={cn(
              "relative h-5 w-9 shrink-0 rounded-full border border-white/30 transition-colors",
              ligado ? "bg-livre" : "bg-black/55",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 size-3.5 rounded-full bg-white shadow transition-[left]",
                ligado ? "left-[1.1rem]" : "left-0.5",
              )}
            />
          </button>
        )}
      </div>

      <div className="absolute inset-x-2 bottom-2.5 text-center">
        <div className="line-clamp-2 text-sm font-bold tracking-wide text-white uppercase drop-shadow">{a.nome}</div>
        {!a.caminho && <div className="mt-0.5 text-[0.62rem] text-manutencao">sem caminho: não aparece no menu</div>}
        {!ligado && <div className="mt-0.5 text-[0.62rem] text-white/70">desligado neste piso</div>}
      </div>
    </div>
  )
}

/** Cadastro (app = "novo", entra ligado no piso do topo) e edição de um app. */
function ModalApp({
  app,
  piso,
  aoFechar,
  aoSalvar,
}: {
  app: AppPermitido | "novo" | null
  piso: Piso | null
  aoFechar: () => void
  aoSalvar: () => Promise<void>
}) {
  const avisar = useAvisos()
  const novo = app === "novo"
  const atual = app && app !== "novo" ? app : null
  const [nome, setNome] = useState("")
  const [processo, setProcesso] = useState("")
  const [caminho, setCaminho] = useState("")
  const [imagem, setImagem] = useState("")
  const [erro, setErro] = useState("")
  const [aberto, setAberto] = useState<AppPermitido | "novo" | null>(null)

  if (app !== aberto) {
    setAberto(app)
    setNome(atual?.nome ?? "")
    setProcesso(atual?.processo ?? "")
    setCaminho(atual?.caminho ?? "")
    setImagem(atual?.imagem_url ?? "")
    setErro("")
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim() || !processo.trim()) return setErro("Preencha nome e processo (.exe)")
    const dados = {
      nome: nome.trim(),
      processo: processo.trim(),
      caminho: caminho.trim() || null,
      imagem_url: imagem.trim() || null,
    }
    try {
      if (novo) await Api.post("/api/apps/", { ...dados, piso_id: piso?.id })
      else if (atual) await Api.put(`/api/apps/${atual.id}`, dados)
      avisar(novo ? "App adicionado" : "App atualizado")
      aoFechar()
      await aoSalvar()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  async function excluir() {
    if (!atual || !window.confirm(`Excluir ${atual.nome} dos apps permitidos (de todos os pisos)?`)) return
    try {
      await Api.del(`/api/apps/${atual.id}`)
      avisar("App excluído")
      aoFechar()
      await aoSalvar()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo={novo ? "Adicionar app" : "Editar app"} aberto={!!app} aoFechar={aoFechar} className="max-w-lg">
      <form onSubmit={salvar} className="flex gap-5">
        {/* prévia do cartão */}
        <div className="hidden w-32 shrink-0 sm:block">
          <div className="relative aspect-[3/4] overflow-hidden rounded-xl border border-borda bg-superficie-3">
            {imagem.trim() ? (
              <img
                src={imagem.trim()}
                alt=""
                className="absolute inset-0 size-full object-cover"
                onError={(e) => (e.currentTarget.style.display = "none")}
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-4xl font-bold text-texto-fraco">
                {(nome.trim() || "?").slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 to-transparent" />
            <div className="absolute inset-x-1.5 bottom-2 line-clamp-2 text-center text-xs font-bold text-white uppercase">
              {nome.trim() || "Nome do app"}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-3.5">
          <Campo rotulo="Nome" id="app-nome">
            <Input
              id="app-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="ex.: Google Chrome"
            />
          </Campo>
          <Campo rotulo="Processo (.exe)" id="app-proc">
            <Input
              id="app-proc"
              value={processo}
              onChange={(e) => setProcesso(e.target.value)}
              placeholder="chrome.exe"
            />
          </Campo>
          <Campo rotulo="Caminho do .exe" id="app-cam">
            <Input
              id="app-cam"
              value={caminho}
              onChange={(e) => setCaminho(e.target.value)}
              placeholder="C:\...\app.exe"
            />
          </Campo>
          <Campo rotulo="Imagem de capa (URL)" id="app-img">
            <Input id="app-img" value={imagem} onChange={(e) => setImagem(e.target.value)} placeholder="https://..." />
          </Campo>
          {novo && piso && (
            <p className="text-xs text-texto-fraco">
              Entra ligado no piso {piso.nome}. Nos outros pisos, ligue pelo interruptor do cartão.
            </p>
          )}
          <MensagemErro>{erro}</MensagemErro>
          <div className="flex gap-2">
            {!novo && (
              <Button type="button" variant="perigo" onClick={excluir}>
                Excluir
              </Button>
            )}
            <div className="flex-1" />
            <Button type="button" variant="outline" onClick={aoFechar}>
              Cancelar
            </Button>
            <Button type="submit">{novo ? "Adicionar" : "Salvar"}</Button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
