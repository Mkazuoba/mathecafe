import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { IconChevronDown, IconChevronUp, IconDownload, IconSelector } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useDados } from "@/lib/dados"
import { dataDoServidor, formatarTempo } from "@/lib/tempo"
import { cn } from "@/lib/utils"
import { CabecalhoTela } from "@/components/Layout"
import { SeletorCliente, type ClienteResumo } from "@/components/SeletorCliente"
import { AvatarCliente } from "@/components/AvatarCliente"
import { AbaAcoesOperadores, type FiltrosAcoes } from "@/components/AbaAcoesOperadores"
import { AbaUso, type FiltrosUso } from "@/components/AbaUso"
import { Button } from "@/components/ui/button"
import { Campo, INICIO_RELATORIOS, InputData, MensagemErro, Select, hojeIso } from "@/components/ui/campos"
import { Vazio } from "@/components/ui/status"

// Respostas de GET /api/relatorios/cliente/{id} e /estacao/{nome}
interface Resumo {
  sessoes: number
  tempo_segundos: number
  primeira_vez: string | null
  ultima_vez: string | null
}
interface ItemUso {
  /** tem uma sessão em andamento agora (o tempo dela entra quando acaba) */
  em_uso?: boolean
  sessoes: number
  tempo_segundos: number
  primeira_vez: string | null
  ultima_vez: string | null
}
interface HistoricoCliente extends Resumo {
  cliente: ClienteResumo & { tem_foto: boolean; foto_em: string | null }
  /** estação em que o cliente está logado agora */
  em_uso: string | null
  itens: (ItemUso & { estacao: string; estacao_id?: number; piso_id?: number | null })[]
}
interface HistoricoEstacao extends Resumo {
  estacao: { id: number; nome: string; grupo: string | null }
  clientes: number
  itens: (ItemUso & { cliente_id: number; login: string; nome: string })[]
}

type Aba = "cliente" | "estacao" | "acoes" | "uso"
type Coluna = "nome" | "sessoes" | "tempo" | "ultima"

/** Uma linha da tabela, igual nas duas abas. */
interface Linha extends ItemUso {
  chave: string
  titulo: string
  subtitulo?: string
  aoAbrir: () => void
}

const dataHora = (iso: string | null) =>
  iso ? dataDoServidor(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—"

const compararNome = (a: string, b: string) => a.localeCompare(b, "pt-BR", { numeric: true, sensitivity: "base" })

/** CSV para o Excel em português: ponto e vírgula e BOM para os acentos. */
function baixarCsv(nomeArquivo: string, cabecalho: string[], linhas: (string | number)[][]) {
  const campo = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
  const texto = [cabecalho, ...linhas].map((l) => l.map(campo).join(";")).join("\r\n")
  const url = URL.createObjectURL(new Blob(["﻿" + texto], { type: "text/csv;charset=utf-8" }))
  const a = document.createElement("a")
  a.href = url
  a.download = nomeArquivo
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function Historicos() {
  const [params, setParams] = useSearchParams()
  const admin = Api.ehAdmin()
  const pedida = params.get("aba")
  // o registro dos operadores é só do admin
  const aba: Aba =
    pedida === "estacao" ? "estacao" : (pedida === "acoes" || pedida === "uso") && admin ? pedida : "cliente"
  const clienteId = params.get("cliente")
  const estacaoNome = params.get("estacao") ?? ""
  const de = params.get("de") ?? ""
  const ate = params.get("ate") ?? ""

  // O endereço guarda a escolha: dá para voltar, recarregar e mandar o link
  const mudar = useCallback(
    (novos: Record<string, string | null | undefined>) => {
      setParams(
        (atual) => {
          const p = new URLSearchParams(atual)
          for (const [k, v] of Object.entries(novos)) {
            if (v) p.set(k, v)
            else p.delete(k)
          }
          return p
        },
        { replace: true },
      )
    },
    [setParams],
  )
  const filtrosAcoes: FiltrosAcoes = {
    operador_id: params.get("operador_id") ?? "",
    acao: params.get("acao") ?? "",
    cliente: params.get("cliente_texto") ?? "",
    estacao: params.get("estacao_texto") ?? "",
    de,
    ate,
  }
  const filtrosUso: FiltrosUso = { de, ate, piso_id: params.get("piso_id") ?? "" }
  const mudarAcoes = useCallback(
    (novos: Partial<FiltrosAcoes>) => {
      const { cliente, estacao, ...resto } = novos
      mudar({
        ...resto,
        ...(cliente !== undefined ? { cliente_texto: cliente } : {}),
        ...(estacao !== undefined ? { estacao_texto: estacao } : {}),
      })
    },
    [mudar],
  )

  return (
    <>
      <CabecalhoTela titulo="Históricos">
        <div className="flex rounded-md border border-borda bg-superficie-2 p-0.5 text-sm" role="tablist">
          {(
            [
              ["cliente", "Por cliente"],
              ["estacao", "Por estação"],
              ...(admin
                ? ([
                    ["uso", "Uso"],
                    ["acoes", "Ações dos operadores"],
                  ] as const)
                : []),
            ] as const
          ).map(([id, rotulo]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={aba === id}
              onClick={() => mudar({ aba: id })}
              className={cn(
                "rounded px-3 py-1 font-medium",
                aba === id ? "bg-destaque text-zinc-100" : "text-texto-suave hover:text-texto",
              )}
            >
              {rotulo}
            </button>
          ))}
        </div>
      </CabecalhoTela>
      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        {aba === "uso" ? (
          <AbaUso filtros={filtrosUso} mudar={mudar} />
        ) : aba === "acoes" ? (
          <AbaAcoesOperadores filtros={filtrosAcoes} mudar={mudarAcoes} />
        ) : aba === "cliente" ? (
          <AbaCliente
            clienteId={clienteId}
            de={de}
            ate={ate}
            mudar={mudar}
            abrirEstacao={(nome, pisoId) => mudar({ aba: "estacao", estacao: nome, piso: pisoId ? String(pisoId) : null })}
          />
        ) : (
          <AbaEstacao
            estacaoNome={estacaoNome}
            de={de}
            ate={ate}
            mudar={mudar}
            abrirCliente={(id) => mudar({ aba: "cliente", cliente: String(id) })}
          />
        )}
      </div>
    </>
  )
}

/**
 * Carrega o histórico quando a escolha ou o período mudam, e de novo quando
 * uma sessão abre ou fecha (as sessões chegam pelo WebSocket): quem loga já
 * aparece, sem esperar sair.
 */
function useHistorico<T>(caminho: string | null, de: string, ate: string) {
  const [dados, setDados] = useState<T | null>(null)
  const [erro, setErro] = useState("")
  const [carregando, setCarregando] = useState(false)
  const { sessoes } = useDados()
  const sessoesAbertas = sessoes.map((s) => s.id).join(",")
  const consulta = `${caminho}|${de}|${ate}`
  const ultima = useRef("")

  useEffect(() => {
    // só limpa a tela quando a escolha muda; ao vivo, troca os dados no lugar
    if (ultima.current !== consulta) setDados(null)
    ultima.current = consulta
    setErro("")
    if (!caminho) return
    let cancelado = false
    const p = new URLSearchParams()
    if (de) p.set("de", de)
    if (ate) p.set("ate", ate)
    setCarregando(true)
    Api.get<T>(`${caminho}?${p}`)
      .then((d) => !cancelado && setDados(d))
      .catch((e) => !cancelado && setErro((e as Error).message))
      .finally(() => !cancelado && setCarregando(false))
    return () => {
      cancelado = true
    }
  }, [caminho, de, ate, consulta, sessoesAbertas])

  return { dados, erro, carregando }
}

function Periodo({ de, ate, mudar }: { de: string; ate: string; mudar: (n: Record<string, string | null>) => void }) {
  return (
    <>
      <Campo rotulo="De" id="hist-de">
        <InputData id="hist-de" min={INICIO_RELATORIOS} max={ate || hojeIso()} value={de} onChange={(v) => mudar({ de: v || null })} className="w-40" />
      </Campo>
      <Campo rotulo="Até" id="hist-ate">
        <InputData id="hist-ate" min={de || INICIO_RELATORIOS} max={hojeIso()} value={ate} onChange={(v) => mudar({ ate: v || null })} className="w-40" />
      </Campo>
    </>
  )
}

function AbaCliente({ clienteId, de, ate, mudar, abrirEstacao }: {
  clienteId: string | null
  de: string
  ate: string
  mudar: (n: Record<string, string | null>) => void
  abrirEstacao: (nome: string, pisoId?: number | null) => void
}) {
  const { dados, erro, carregando } = useHistorico<HistoricoCliente>(
    clienteId ? `/api/relatorios/cliente/${clienteId}` : null, de, ate,
  )

  const { pisos } = useDados()
  const linhas: Linha[] = (dados?.itens ?? []).map((i) => ({
    ...i,
    chave: String(i.estacao_id ?? i.estacao),
    titulo: i.estacao,
    // o mesmo nome pode estar nos dois pisos (6.18)
    subtitulo: pisos.length > 1 ? pisos.find((p) => p.id === i.piso_id)?.nome : undefined,
    aoAbrir: () => abrirEstacao(i.estacao, i.piso_id),
  }))

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="w-80 max-w-full">
          <Campo rotulo="Cliente" id="hist-cliente">
            <SeletorCliente
              todosOsPisos
              id="hist-cliente"
              placeholder="Digite o nome ou login..."
              valor={dados?.cliente ?? null}
              aoMudar={(c) => mudar({ cliente: c ? String(c.id) : null })}
            />
          </Campo>
        </div>
        <Periodo de={de} ate={ate} mudar={mudar} />
      </div>
      <MensagemErro>{erro}</MensagemErro>
      {!clienteId ? (
        <Vazio>Escolha um cliente para ver quais estações ele já usou.</Vazio>
      ) : carregando && !dados ? (
        <Vazio>Carregando...</Vazio>
      ) : dados ? (
        <>
          <div className="mb-4 flex items-center gap-3.5">
            <AvatarCliente cliente={dados.cliente} className="size-14 text-base" />
            <div className="min-w-0">
              <div className="truncate text-base font-semibold">{dados.cliente.nome}</div>
              <div className="text-sm text-texto-fraco">{dados.cliente.login}</div>
            </div>
            {dados.em_uso && (
              <span className="ml-1 inline-flex items-center gap-1.5 rounded-full border border-livre-borda bg-livre-fundo px-2.5 py-0.5 text-xs font-medium text-livre">
                <span className="size-1.5 rounded-full bg-current" />
                Usando agora · {dados.em_uso}
              </span>
            )}
          </div>
          <Totais
            itens={[
              ["Sessões", String(dados.sessoes)],
              ["Estações diferentes", String(dados.itens.length)],
              ["Tempo total", formatarTempo(dados.tempo_segundos)],
              ["Primeira vez", dataHora(dados.primeira_vez)],
              ["Última vez", dataHora(dados.ultima_vez)],
            ]}
          />
          <TabelaUso
            rotuloNome="Estação"
            linhas={linhas}
            vazio="Nenhuma sessão neste período."
            aoExportar={() =>
              baixarCsv(
                `historico_${dados.cliente.login}.csv`,
                ["Estação", "Sessões", "Tempo total", "Primeira vez", "Última vez"],
                linhas.map((l) => [l.titulo, l.sessoes, formatarTempo(l.tempo_segundos), dataHora(l.primeira_vez), dataHora(l.ultima_vez)]),
              )
            }
          />
        </>
      ) : null}
    </>
  )
}

function AbaEstacao({ estacaoNome, de, ate, mudar, abrirCliente }: {
  estacaoNome: string
  de: string
  ate: string
  mudar: (n: Record<string, string | null>) => void
  abrirCliente: (id: number) => void
}) {
  const { todasEstacoes, pisos, piso: pisoDoTopo } = useDados()
  // o filtro de piso desta aba (?piso=); começa no piso usado por último no Painel
  const [params] = useSearchParams()
  const pisoId = Number(params.get("piso")) || pisoDoTopo?.id || pisos[0]?.id
  const ordenadas = useMemo(
    () => todasEstacoes.filter((e) => e.piso_id === pisoId).sort((a, b) => compararNome(a.nome, b.nome)),
    [todasEstacoes, pisoId],
  )
  const { dados, erro, carregando } = useHistorico<HistoricoEstacao>(
    // o nome pode estar nos dois pisos (6.18): vale o piso escolhido aqui
    estacaoNome && pisoId ? `/api/relatorios/estacao/${encodeURIComponent(estacaoNome)}?piso_id=${pisoId}` : null, de, ate,
  )

  const linhas: Linha[] = (dados?.itens ?? []).map((i) => ({
    ...i,
    chave: String(i.cliente_id),
    titulo: i.nome,
    subtitulo: i.login,
    aoAbrir: () => abrirCliente(i.cliente_id),
  }))

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        {pisos.length > 1 && (
          <Campo rotulo="Piso" id="hist-piso">
            <Select
              id="hist-piso"
              value={pisoId ?? ""}
              onChange={(e) => mudar({ piso: e.target.value, estacao: null })}
              className="w-40"
            >
              {pisos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </Select>
          </Campo>
        )}
        <Campo rotulo="Estação" id="hist-estacao">
          <Select id="hist-estacao" value={estacaoNome} onChange={(e) => mudar({ estacao: e.target.value || null })} className="w-56">
            <option value="">Escolha a estação</option>
            {ordenadas.map((e) => (
              <option key={e.id} value={e.nome}>
                {e.nome}
                {e.grupo_nome ? ` — ${e.grupo_nome}` : ""}
              </option>
            ))}
          </Select>
        </Campo>
        <Periodo de={de} ate={ate} mudar={mudar} />
      </div>
      <MensagemErro>{erro}</MensagemErro>
      {!estacaoNome ? (
        <Vazio>Escolha uma estação para ver quais clientes já passaram por ela.</Vazio>
      ) : carregando && !dados ? (
        <Vazio>Carregando...</Vazio>
      ) : dados ? (
        <>
          <Totais
            itens={[
              ["Sessões", String(dados.sessoes)],
              ["Clientes diferentes", String(dados.clientes)],
              ["Tempo total", formatarTempo(dados.tempo_segundos)],
              ["Primeira vez", dataHora(dados.primeira_vez)],
              ["Última vez", dataHora(dados.ultima_vez)],
            ]}
          />
          <TabelaUso
            rotuloNome="Cliente"
            linhas={linhas}
            vazio="Nenhuma sessão neste período."
            aoExportar={() =>
              baixarCsv(
                `historico_${dados.estacao.nome}.csv`,
                ["Login", "Cliente", "Sessões", "Tempo total", "Primeira vez", "Última vez"],
                linhas.map((l) => [l.subtitulo ?? "", l.titulo, l.sessoes, formatarTempo(l.tempo_segundos), dataHora(l.primeira_vez), dataHora(l.ultima_vez)]),
              )
            }
          />
        </>
      ) : null}
    </>
  )
}

function Totais({ itens }: { itens: [string, string][] }) {
  return (
    <dl className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {itens.map(([rotulo, valor]) => (
        <div key={rotulo} className="rounded-lg border border-borda bg-superficie-2 px-3.5 py-2.5">
          <dt className="text-xs text-texto-fraco">{rotulo}</dt>
          <dd className="mt-0.5 text-base font-semibold tabular-nums">{valor}</dd>
        </div>
      ))}
    </dl>
  )
}

function TabelaUso({ rotuloNome, linhas, vazio, aoExportar }: {
  rotuloNome: string
  linhas: Linha[]
  vazio: string
  aoExportar: () => void
}) {
  const [ordem, setOrdem] = useState<{ coluna: Coluna; desc: boolean }>({ coluna: "ultima", desc: true })

  const ordenadas = useMemo(() => {
    const valor = (l: Linha) =>
      ordem.coluna === "sessoes" ? l.sessoes : ordem.coluna === "tempo" ? l.tempo_segundos : (l.ultima_vez ?? "")
    const sinal = ordem.desc ? -1 : 1
    return [...linhas].sort((a, b) => {
      if (ordem.coluna === "nome") return sinal * compararNome(a.titulo, b.titulo)
      const va = valor(a)
      const vb = valor(b)
      return sinal * (va < vb ? -1 : va > vb ? 1 : 0) || compararNome(a.titulo, b.titulo)
    })
  }, [linhas, ordem])

  function ordenar(coluna: Coluna) {
    // números e datas começam do maior; nomes, de A a Z
    setOrdem((o) => ({ coluna, desc: o.coluna === coluna ? !o.desc : coluna !== "nome" }))
  }

  if (!linhas.length) return <Vazio>{vazio}</Vazio>

  const colunas: [Coluna, string, string?][] = [
    ["nome", rotuloNome],
    ["sessoes", "Sessões", "text-right"],
    ["tempo", "Tempo total", "text-right"],
    ["ultima", "Última vez"],
  ]
  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-texto-fraco">Clique numa linha para ver o outro lado do histórico.</span>
        <Button variant="outline" size="sm" onClick={aoExportar} className="gap-1.5">
          <IconDownload size={14} /> Exportar CSV
        </Button>
      </div>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs tracking-wide text-texto-fraco uppercase">
            {colunas.map(([c, rotulo, classe]) => {
              const ativa = ordem.coluna === c
              return (
                <th
                  key={c}
                  aria-sort={ativa ? (ordem.desc ? "descending" : "ascending") : "none"}
                  className={cn("border-b border-borda px-2.5 py-2 font-medium", classe)}
                >
                  <button
                    type="button"
                    title="Ordenar"
                    onClick={() => ordenar(c)}
                    className={cn("inline-flex items-center gap-0.5 uppercase hover:text-texto", ativa && "text-texto")}
                  >
                    {rotulo}
                    {ativa ? (
                      ordem.desc ? <IconChevronDown size={13} /> : <IconChevronUp size={13} />
                    ) : (
                      <IconSelector size={13} className="opacity-40" />
                    )}
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {ordenadas.map((l) => (
            <tr
              key={l.chave}
              tabIndex={0}
              onClick={l.aoAbrir}
              onKeyDown={(e) => e.key === "Enter" && l.aoAbrir()}
              className="cursor-pointer transition-all duration-200 ease-in-out hover:bg-texto/5 focus-visible:bg-texto/5 focus-visible:outline-none"
            >
              <td className="border-b border-borda px-2.5 py-2">
                {l.titulo}
                {l.subtitulo && <span className="ml-1.5 text-xs text-texto-fraco">{l.subtitulo}</span>}
                {l.em_uso && (
                  <span
                    title="Sessão em andamento: o tempo dela entra no total quando acabar"
                    className="ml-2 inline-flex items-center gap-1 rounded-full border border-livre-borda bg-livre-fundo px-1.5 text-[11px] font-medium text-livre"
                  >
                    <span className="size-1.5 rounded-full bg-current" />
                    agora
                  </span>
                )}
              </td>
              <td className="border-b border-borda px-2.5 py-2 text-right tabular-nums">{l.sessoes}</td>
              <td className="border-b border-borda px-2.5 py-2 text-right tabular-nums">{formatarTempo(l.tempo_segundos)}</td>
              <td className="border-b border-borda px-2.5 py-2 text-texto-suave">{dataHora(l.ultima_vez)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
