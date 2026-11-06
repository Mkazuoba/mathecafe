import { useEffect, useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Interruptor } from "@/components/ui/campos"

interface Dia {
  aberto: boolean
  abre: string
  fecha: string
}

interface Horario {
  ativo: boolean
  /** 0 = segunda ... 6 = domingo */
  dias: Dia[]
}

const NOMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
const ATALHOS: { rotulo: string; dias: number[] }[] = [
  { rotulo: "Seg a sex", dias: [0, 1, 2, 3, 4] },
  { rotulo: "Fim de semana", dias: [5, 6] },
  { rotulo: "Todos", dias: [0, 1, 2, 3, 4, 5, 6] },
]

const campoHora =
  "h-8 rounded-md border border-borda bg-superficie px-2 text-sm tabular-nums outline-none focus:border-destaque disabled:opacity-40"

/**
 * Configurações → Horário: dias de funcionamento e horário de cada um (app/horario.py).
 * Ligado, os clientes são avisados 10 e 5 minutos antes de fechar, as sessões
 * encerram no horário (o tempo que sobrou volta) e fora dele ninguém entra.
 */
export function SecaoHorario() {
  const avisar = useAvisos()
  const [salvo, setSalvo] = useState<Horario | null>(null)
  const [horario, setHorario] = useState<Horario | null>(null)
  const [marcados, setMarcados] = useState<Set<number>>(() => new Set())
  const [abreMassa, setAbreMassa] = useState("08:00")
  const [fechaMassa, setFechaMassa] = useState("20:00")
  const [salvando, setSalvando] = useState(false)

  useEffect(() => {
    Api.get<Horario>("/api/config/horario")
      .then((h) => {
        setSalvo(h)
        setHorario(h)
      })
      .catch((e) => avisar((e as Error).message, "erro"))
  }, [avisar])

  if (!horario) return <p className="text-sm text-texto-fraco">Carregando...</p>

  const alterado = JSON.stringify(horario) !== JSON.stringify(salvo)
  const invalidos = horario.dias.map((d) => d.aberto && d.fecha <= d.abre)

  function mudarDia(i: number, mudanca: Partial<Dia>) {
    setHorario((h) => h && { ...h, dias: h.dias.map((d, j) => (j === i ? { ...d, ...mudanca } : d)) })
  }

  function aplicarNosMarcados(mudanca: Partial<Dia>) {
    if (!marcados.size) return avisar("Marque os dias primeiro", "erro")
    setHorario((h) => h && { ...h, dias: h.dias.map((d, j) => (marcados.has(j) ? { ...d, ...mudanca } : d)) })
  }

  function marcar(i: number, sim: boolean) {
    setMarcados((prev) => {
      const n = new Set(prev)
      if (sim) n.add(i)
      else n.delete(i)
      return n
    })
  }

  async function salvar() {
    if (!horario) return
    if (invalidos.some(Boolean)) return avisar("Em algum dia o horário de fechar está antes do de abrir", "erro")
    setSalvando(true)
    try {
      const h = await Api.put<Horario>("/api/config/horario", horario)
      setSalvo(h)
      setHorario(h)
      avisar("Horário salvo")
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Horário de funcionamento</h2>
      <p className="mb-4 text-sm text-texto-fraco">
        Com o horário ligado, os clientes recebem um aviso na tela 10 e 5 minutos antes de fechar, as sessões são
        encerradas no horário (o tempo que sobrou volta para cada cliente) e, fora do horário, ninguém consegue entrar
        nos computadores.
      </p>
      <div className="mb-5">
        <Interruptor
          id="horario-ativo"
          rotulo="Usar o horário de funcionamento"
          ligado={horario.ativo}
          aoMudar={(v) => setHorario({ ...horario, ativo: v })}
        />
      </div>

      {/* Vários dias de uma vez */}
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-borda bg-superficie-2 px-3 py-2.5 text-sm">
        <span className="text-texto-suave">Marcar:</span>
        {ATALHOS.map((a) => (
          <Button key={a.rotulo} type="button" size="xs" variant="outline" onClick={() => setMarcados(new Set(a.dias))}>
            {a.rotulo}
          </Button>
        ))}
        <span className="mx-1 h-5 w-px bg-borda" />
        <span className="text-texto-suave">Nos marcados:</span>
        <input
          type="time"
          aria-label="Abre (dias marcados)"
          value={abreMassa}
          onChange={(e) => setAbreMassa(e.target.value)}
          className={campoHora}
        />
        <span className="text-texto-fraco">às</span>
        <input
          type="time"
          aria-label="Fecha (dias marcados)"
          value={fechaMassa}
          onChange={(e) => setFechaMassa(e.target.value)}
          className={campoHora}
        />
        <Button
          type="button"
          size="xs"
          onClick={() => aplicarNosMarcados({ aberto: true, abre: abreMassa, fecha: fechaMassa })}
        >
          Aplicar
        </Button>
        <Button type="button" size="xs" variant="outline" onClick={() => aplicarNosMarcados({ aberto: false })}>
          Fechado
        </Button>
      </div>

      <table className="mb-5 w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs tracking-wide text-texto-fraco uppercase">
            <th className="w-8 border-b border-borda py-2 pl-2">
              <input
                type="checkbox"
                aria-label="Marcar todos os dias"
                checked={marcados.size === 7}
                onChange={(e) => setMarcados(e.target.checked ? new Set([0, 1, 2, 3, 4, 5, 6]) : new Set())}
                className="size-4 cursor-pointer"
              />
            </th>
            <th className="border-b border-borda px-2 py-2 font-medium">Dia</th>
            <th className="border-b border-borda px-2 py-2 font-medium">Funciona</th>
            <th className="border-b border-borda px-2 py-2 font-medium">Abre</th>
            <th className="border-b border-borda px-2 py-2 font-medium">Fecha</th>
          </tr>
        </thead>
        <tbody>
          {horario.dias.map((d, i) => (
            <tr key={NOMES[i]} className={cn("border-b border-borda/60", marcados.has(i) && "bg-superficie-2")}>
              <td className="py-2 pl-2">
                <input
                  type="checkbox"
                  aria-label={`Marcar ${NOMES[i]}`}
                  checked={marcados.has(i)}
                  onChange={(e) => marcar(i, e.target.checked)}
                  className="size-4 cursor-pointer"
                />
              </td>
              <td className="px-2 py-2 font-medium">{NOMES[i]}</td>
              <td className="px-2 py-2">
                <label className="inline-flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={d.aberto}
                    onChange={(e) => mudarDia(i, { aberto: e.target.checked })}
                    className="size-4 cursor-pointer"
                  />
                  <span className={d.aberto ? "text-livre" : "text-texto-fraco"}>{d.aberto ? "Aberto" : "Fechado"}</span>
                </label>
              </td>
              <td className="px-2 py-2">
                <input
                  type="time"
                  aria-label={`${NOMES[i]}: abre`}
                  value={d.abre}
                  disabled={!d.aberto}
                  onChange={(e) => mudarDia(i, { abre: e.target.value })}
                  className={campoHora}
                />
              </td>
              <td className="px-2 py-2">
                <input
                  type="time"
                  aria-label={`${NOMES[i]}: fecha`}
                  value={d.fecha}
                  disabled={!d.aberto}
                  onChange={(e) => mudarDia(i, { fecha: e.target.value })}
                  className={cn(campoHora, invalidos[i] && "border-perigo text-perigo")}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Button type="button" disabled={!alterado || salvando} onClick={salvar}>
        {salvando ? "Salvando..." : "Salvar horário"}
      </Button>
    </div>
  )
}
