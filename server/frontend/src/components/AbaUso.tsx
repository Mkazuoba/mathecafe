import { useEffect, useMemo, useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo } from "@/lib/tempo"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, INICIO_RELATORIOS, InputData, Select, hojeIso } from "@/components/ui/campos"
import { Vazio } from "@/components/ui/status"

// Resposta de GET /api/relatorios/uso
interface Uso {
  periodo: { de: string; ate: string }
  resumo: { sessoes: number; segundos: number; clientes: number; media_segundos: number }
  por_dia: { dia: string; sessoes: number; segundos: number; clientes: number }[]
  pico: { dia_semana: number; hora: number; segundos: number }[]
  estacoes: { estacao: string; sessoes: number; segundos: number }[]
}

export interface FiltrosUso {
  de: string
  ate: string
  piso_id: string
}

const DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
const DIAS_SEMANA_LONGO = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
// mapa de calor: uma cor só (a de destaque), do mais claro ao mais escuro
const TONS = [28, 46, 64, 82, 100]

const isoLocal = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const deIso = (s: string) => {
  const [a, m, d] = s.split("-").map(Number)
  return new Date(a, m - 1, d)
}
const curto = (s: string) => deIso(s).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
/** Dica que acompanha o mouse (valores ao passar sobre barras e células). */
function useDica() {
  const [dica, setDica] = useState<{ x: number; y: number; texto: string[] } | null>(null)
  const mostrar = (ev: React.MouseEvent, texto: string[]) => setDica({ x: ev.clientX, y: ev.clientY, texto })
  const elemento = dica && (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-[1100] rounded-md border border-borda bg-superficie px-2.5 py-1.5 text-xs shadow-lg"
      style={{ left: dica.x + 12, top: dica.y + 12 }}
    >
      {dica.texto.map((t, i) => (
        <div key={i} className={i === 0 ? "font-semibold text-texto" : "text-texto-suave"}>
          {t}
        </div>
      ))}
    </div>
  )
  return { mostrar, esconder: () => setDica(null), elemento }
}

/**
 * Históricos → Uso (só admin): quanto os computadores foram usados no período,
 * por dia, em que horários e em quais estações. Só sessões já encerradas.
 */
export function AbaUso({ filtros, mudar }: { filtros: FiltrosUso; mudar: (novos: Partial<FiltrosUso>) => void }) {
  const avisar = useAvisos()
  const { pisos } = useDados()
  const [uso, setUso] = useState<Uso | null>(null)
  const [tabela, setTabela] = useState(false)
  const dica = useDica()

  const consulta = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v) as [string, string][]).toString()

  useEffect(() => {
    let cancelado = false
    setUso(null)
    Api.get<Uso>(`/api/relatorios/uso${consulta ? "?" + consulta : ""}`)
      .then((u) => !cancelado && setUso(u))
      .catch((e) => !cancelado && avisar((e as Error).message, "erro"))
    return () => {
      cancelado = true
    }
  }, [consulta, avisar])

  function ultimosDias(n: number) {
    const fim = new Date()
    const inicio = new Date()
    inicio.setDate(fim.getDate() - (n - 1))
    mudar({ de: isoLocal(inicio), ate: isoLocal(fim) })
  }
  function esteMes() {
    const hoje = new Date()
    mudar({ de: isoLocal(new Date(hoje.getFullYear(), hoje.getMonth(), 1)), ate: isoLocal(hoje) })
  }

  // todos os dias do período, inclusive os sem uso (a barra fica vazia)
  const dias = useMemo(() => {
    if (!uso) return []
    const mapa = new Map(uso.por_dia.map((d) => [d.dia, d]))
    const lista = []
    for (let d = deIso(uso.periodo.de); d <= deIso(uso.periodo.ate); d.setDate(d.getDate() + 1)) {
      const k = isoLocal(d)
      lista.push(mapa.get(k) ?? { dia: k, sessoes: 0, segundos: 0, clientes: 0 })
    }
    return lista
  }, [uso])

  return (
    <div>
      {/* filtros numa linha, acima dos gráficos */}
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <Campo rotulo="De" id="uso-de">
          <InputData id="uso-de" min={INICIO_RELATORIOS} max={filtros.ate || hojeIso()} value={filtros.de} onChange={(v) => mudar({ de: v })} />
        </Campo>
        <Campo rotulo="Até" id="uso-ate">
          <InputData id="uso-ate" min={filtros.de || INICIO_RELATORIOS} max={hojeIso()} value={filtros.ate} onChange={(v) => mudar({ ate: v })} />
        </Campo>
        <div className="flex gap-1.5 pb-0.5">
          <Button type="button" size="sm" variant="outline" onClick={() => ultimosDias(7)}>
            7 dias
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => ultimosDias(30)}>
            30 dias
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={esteMes}>
            Este mês
          </Button>
        </div>
        <Campo rotulo="Piso" id="uso-piso">
          <Select id="uso-piso" value={filtros.piso_id} onChange={(e) => mudar({ piso_id: e.target.value })}>
            <option value="">Todos os pisos</option>
            {pisos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </Select>
        </Campo>
      </div>

      {!uso ? (
        <Vazio>Carregando...</Vazio>
      ) : (
        <>
          <p className="mb-3 text-sm text-texto-suave">
            De {deIso(uso.periodo.de).toLocaleDateString("pt-BR")} a{" "}
            {deIso(uso.periodo.ate).toLocaleDateString("pt-BR")}
            {" · "}só sessões já encerradas
          </p>

          {/* números em destaque */}
          <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Sessões", uso.resumo.sessoes.toLocaleString("pt-BR")],
              ["Tempo de uso", formatarTempo(uso.resumo.segundos)],
              ["Clientes diferentes", uso.resumo.clientes.toLocaleString("pt-BR")],
              ["Média por sessão", formatarTempo(uso.resumo.media_segundos)],
            ].map(([rotulo, valor]) => (
              <div key={rotulo} className="rounded-lg border border-borda bg-superficie-2 px-4 py-3">
                <div className="text-xs text-texto-fraco">{rotulo}</div>
                <div className="text-2xl font-semibold tabular-nums">{valor}</div>
              </div>
            ))}
          </div>

          {uso.resumo.sessoes === 0 ? (
            <Vazio>Nenhuma sessão encerrada nesse período.</Vazio>
          ) : (
            <div className="flex flex-col gap-8">
              <section>
                <div className="mb-2 flex items-center gap-3">
                  <h3 className="font-semibold">Horas de uso por dia</h3>
                  <span className="text-xs text-texto-fraco">
                    passe o mouse sobre a barra para ver sessões e clientes
                  </span>
                  <div className="flex-1" />
                  <Button type="button" size="xs" variant="ghost" onClick={() => setTabela((v) => !v)}>
                    {tabela ? "Ver gráfico" : "Ver tabela"}
                  </Button>
                </div>
                {tabela ? <TabelaDias dias={uso.por_dia} /> : <GraficoDias dias={dias} dica={dica} />}
              </section>

              <section>
                <h3 className="mb-2 font-semibold">Horários de pico</h3>
                <MapaDeCalor pico={uso.pico} dica={dica} />
              </section>

              <section>
                <h3 className="mb-2 font-semibold">Estações mais usadas</h3>
                <RankingEstacoes estacoes={uso.estacoes} dica={dica} />
              </section>
            </div>
          )}
        </>
      )}
      {dica.elemento}
    </div>
  )
}

type Dica = ReturnType<typeof useDica>

function GraficoDias({ dias, dica }: { dias: Uso["por_dia"]; dica: Dica }) {
  const ALTURA = 180
  const maximo = Math.max(...dias.map((d) => d.segundos), 1)
  // linhas de grade em horas "redondas"
  const passoHoras = [1, 2, 5, 10, 20, 50, 100].find((p) => maximo / 3600 / p <= 4) ?? 200
  const linhas: number[] = []
  for (let h = passoHoras; h * 3600 <= maximo; h += passoHoras) linhas.push(h)
  const topo = Math.max(maximo, (linhas[linhas.length - 1] ?? 0) * 3600)
  const marcaCada = Math.ceil(dias.length / 12) // no máximo ~12 datas embaixo

  return (
    <div className="flex gap-2">
      <div className="relative w-8 shrink-0 text-right text-[11px] text-texto-fraco" style={{ height: ALTURA }}>
        {linhas.map((h) => (
          <span key={h} className="absolute right-0 -translate-y-1/2" style={{ bottom: ((h * 3600) / topo) * ALTURA }}>
            {h}h
          </span>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <div className="relative flex items-end gap-0.5 border-b border-borda-forte" style={{ height: ALTURA }}>
          {linhas.map((h) => (
            <div
              key={h}
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 border-t border-borda/50"
              style={{ bottom: ((h * 3600) / topo) * ALTURA }}
            />
          ))}
          {dias.map((d) => {
            const sem = DIAS_SEMANA_LONGO[(deIso(d.dia).getDay() + 6) % 7]
            const texto = [
              `${curto(d.dia)} (${sem})`,
              `${formatarTempo(d.segundos)} de uso`,
              `${d.sessoes} ${d.sessoes === 1 ? "sessão" : "sessões"} · ${d.clientes} ${d.clientes === 1 ? "cliente" : "clientes"}`,
            ]
            return (
              // a área de toque é a coluna inteira, maior que a barra
              <div
                key={d.dia}
                className="group relative flex h-full flex-1 items-end"
                onMouseMove={(ev) => dica.mostrar(ev, texto)}
                onMouseLeave={dica.esconder}
              >
                <div
                  className="w-full rounded-t-[4px] bg-destaque transition-opacity group-hover:opacity-80"
                  style={{ height: d.segundos ? Math.max(2, (d.segundos / topo) * ALTURA) : 0 }}
                />
              </div>
            )
          })}
        </div>
        <div className="mt-1 flex gap-0.5 text-[11px] text-texto-fraco">
          {dias.map((d, i) => (
            <span key={d.dia} className="flex-1 text-center whitespace-nowrap">
              {i % marcaCada === 0 ? curto(d.dia) : ""}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function TabelaDias({ dias }: { dias: Uso["por_dia"] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="text-left text-xs tracking-wide text-texto-fraco uppercase">
          {["Dia", "Sessões", "Tempo de uso", "Clientes"].map((t) => (
            <th key={t} className="border-b border-borda px-2.5 py-2 font-medium">
              {t}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {dias.map((d) => (
          <tr key={d.dia} className="border-b border-borda/60 tabular-nums">
            <td className="px-2.5 py-1.5">
              {deIso(d.dia).toLocaleDateString("pt-BR")} ({DIAS_SEMANA_LONGO[(deIso(d.dia).getDay() + 6) % 7]})
            </td>
            <td className="px-2.5 py-1.5">{d.sessoes}</td>
            <td className="px-2.5 py-1.5">{formatarTempo(d.segundos)}</td>
            <td className="px-2.5 py-1.5">{d.clientes}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function MapaDeCalor({ pico, dica }: { pico: Uso["pico"]; dica: Dica }) {
  const valores = new Map(pico.map((p) => [`${p.dia_semana}-${p.hora}`, p.segundos]))
  const maximo = Math.max(...pico.map((p) => p.segundos), 1)
  // só as horas com algum uso, de ponta a ponta (a biblioteca não abre de madrugada)
  const horasComUso = pico.map((p) => p.hora)
  const primeira = Math.min(...horasComUso)
  const ultima = Math.max(...horasComUso)
  const horasMostradas = Array.from({ length: ultima - primeira + 1 }, (_, i) => primeira + i)

  const tom = (seg: number) =>
    seg <= 0 ? null : TONS[Math.min(TONS.length - 1, Math.floor((seg / maximo) * TONS.length - 1e-9))]

  return (
    <div className="overflow-x-auto">
      <div
        className="grid gap-[2px] text-[11px]"
        style={{ gridTemplateColumns: `2.5rem repeat(${horasMostradas.length}, minmax(1.6rem, 1fr))` }}
      >
        <span />
        {horasMostradas.map((h) => (
          <span key={h} className="text-center text-texto-fraco">
            {h}h
          </span>
        ))}
        {DIAS_SEMANA.map((nome, dia) => (
          <div key={nome} className="contents">
            <span className="self-center text-texto-suave">{nome}</span>
            {horasMostradas.map((h) => {
              const seg = valores.get(`${dia}-${h}`) ?? 0
              const t = tom(seg)
              return (
                <div
                  key={h}
                  className={cn("h-7 rounded-[3px]", t == null && "bg-superficie-2")}
                  style={
                    t == null
                      ? undefined
                      : { background: `color-mix(in srgb, var(--color-destaque) ${t}%, var(--color-superficie))` }
                  }
                  onMouseMove={(ev) =>
                    dica.mostrar(ev, [
                      `${DIAS_SEMANA_LONGO[dia]}, ${h}h às ${h + 1}h`,
                      seg ? `${formatarTempo(seg)} de uso no período` : "sem uso",
                    ])
                  }
                  onMouseLeave={dica.esconder}
                />
              )
            })}
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-texto-fraco">
        Menos
        {TONS.map((t) => (
          <span
            key={t}
            className="size-3 rounded-[3px]"
            style={{ background: `color-mix(in srgb, var(--color-destaque) ${t}%, var(--color-superficie))` }}
          />
        ))}
        Mais uso (soma das horas de uso naquele dia da semana e hora)
      </div>
    </div>
  )
}

function RankingEstacoes({ estacoes, dica }: { estacoes: Uso["estacoes"]; dica: Dica }) {
  const maximo = Math.max(...estacoes.map((e) => e.segundos), 1)
  const mostradas = estacoes.slice(0, 15)
  return (
    <div className="flex flex-col gap-1.5">
      {mostradas.map((e) => (
        <div
          key={e.estacao}
          className="grid grid-cols-[6rem_1fr_6rem] items-center gap-3 text-sm"
          onMouseMove={(ev) =>
            dica.mostrar(ev, [e.estacao, `${formatarTempo(e.segundos)} de uso`, `${e.sessoes} sessões`])
          }
          onMouseLeave={dica.esconder}
        >
          <span className="truncate">{e.estacao}</span>
          <div className="h-3.5 rounded-r-[4px] bg-superficie-2">
            <div className="h-full rounded-r-[4px] bg-destaque" style={{ width: `${(e.segundos / maximo) * 100}%` }} />
          </div>
          <span className="text-right text-texto-suave tabular-nums">{formatarTempo(e.segundos)}</span>
        </div>
      ))}
      {estacoes.length > mostradas.length && (
        <p className="text-xs text-texto-fraco">e mais {estacoes.length - mostradas.length} estações</p>
      )}
    </div>
  )
}
