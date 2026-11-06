import { useEffect, useState } from "react"
import { IconDownload } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { dataDoServidor } from "@/lib/tempo"
import type { Operador } from "@/lib/tipos"
import { Button } from "@/components/ui/button"
import { Campo, Input, Select } from "@/components/ui/campos"
import { Vazio } from "@/components/ui/status"

interface Acao {
  id: number
  quando: string
  operador: string
  acao: string
  rotulo: string
  cliente_login: string | null
  cliente_nome: string | null
  estacao: string | null
  detalhe: string | null
}

export interface FiltrosAcoes {
  operador_id: string
  acao: string
  cliente: string
  estacao: string
  de: string
  ate: string
}

const LIMITE = 500

/**
 * Históricos → Ações dos operadores (só admin): quem liberou, deu tempo extra,
 * encerrou, desligou... do mais recente para o mais antigo, com filtros e CSV.
 * Os filtros ficam no endereço (como nas outras abas).
 */
export function AbaAcoesOperadores({
  filtros,
  mudar,
}: {
  filtros: FiltrosAcoes
  mudar: (novos: Partial<FiltrosAcoes>) => void
}) {
  const avisar = useAvisos()
  const [operadores, setOperadores] = useState<Operador[]>([])
  const [tipos, setTipos] = useState<{ acao: string; rotulo: string }[]>([])
  const [acoes, setAcoes] = useState<Acao[] | null>(null)
  // o texto do cliente e da estação só vira filtro ao parar de digitar
  const [cliente, setCliente] = useState(filtros.cliente)
  const [estacao, setEstacao] = useState(filtros.estacao)

  useEffect(() => {
    Api.get<Operador[]>("/api/operadores/")
      .then(setOperadores)
      .catch(() => {})
    Api.get<{ acao: string; rotulo: string }[]>("/api/relatorios/acoes/tipos")
      .then(setTipos)
      .catch(() => {})
  }, [])

  useEffect(() => {
    const t = setTimeout(() => {
      if (cliente !== filtros.cliente || estacao !== filtros.estacao) mudar({ cliente, estacao })
    }, 400)
    return () => clearTimeout(t)
  }, [cliente, estacao, filtros.cliente, filtros.estacao, mudar])

  const consulta = new URLSearchParams(
    Object.entries(filtros).filter(([, v]) => v.trim()) as [string, string][],
  ).toString()

  useEffect(() => {
    let cancelado = false
    setAcoes(null)
    Api.get<Acao[]>(`/api/relatorios/acoes?limite=${LIMITE}${consulta ? "&" + consulta : ""}`)
      .then((r) => !cancelado && setAcoes(r))
      .catch((e) => {
        if (!cancelado) {
          setAcoes([])
          avisar((e as Error).message, "erro")
        }
      })
    return () => {
      cancelado = true
    }
  }, [consulta, avisar])

  async function exportar() {
    try {
      await Api.baixar(`/api/relatorios/acoes.csv${consulta ? "?" + consulta : ""}`, "acoes_operadores.csv")
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div>
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Campo rotulo="Operador" id="acoes-operador">
          <Select
            id="acoes-operador"
            value={filtros.operador_id}
            onChange={(e) => mudar({ operador_id: e.target.value })}
          >
            <option value="">Todos</option>
            {operadores.map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </Select>
        </Campo>
        <Campo rotulo="Ação" id="acoes-tipo">
          <Select id="acoes-tipo" value={filtros.acao} onChange={(e) => mudar({ acao: e.target.value })}>
            <option value="">Todas</option>
            {tipos.map((t) => (
              <option key={t.acao} value={t.acao}>
                {t.rotulo}
              </option>
            ))}
          </Select>
        </Campo>
        <Campo rotulo="Cliente (nome ou login)" id="acoes-cliente">
          <Input id="acoes-cliente" value={cliente} onChange={(e) => setCliente(e.target.value)} />
        </Campo>
        <Campo rotulo="Estação" id="acoes-estacao">
          <Input
            id="acoes-estacao"
            value={estacao}
            onChange={(e) => setEstacao(e.target.value)}
            placeholder="ex.: PC-01"
          />
        </Campo>
        <Campo rotulo="De" id="acoes-de">
          <Input id="acoes-de" type="date" value={filtros.de} onChange={(e) => mudar({ de: e.target.value })} />
        </Campo>
        <Campo rotulo="Até" id="acoes-ate">
          <Input id="acoes-ate" type="date" value={filtros.ate} onChange={(e) => mudar({ ate: e.target.value })} />
        </Campo>
      </div>

      <div className="mb-3 flex items-center gap-3">
        <span className="text-sm text-texto-suave">
          {acoes == null
            ? "Carregando..."
            : acoes.length >= LIMITE
              ? `As ${LIMITE} mais recentes (refine os filtros ou exporte o CSV para ver todas)`
              : `${acoes.length} ${acoes.length === 1 ? "ação" : "ações"}`}
        </span>
        <div className="flex-1" />
        <Button variant="outline" size="sm" className="gap-1.5" onClick={exportar}>
          <IconDownload size={14} /> Exportar CSV
        </Button>
      </div>

      {acoes && acoes.length === 0 ? (
        <Vazio>Nenhuma ação com esses filtros.</Vazio>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs tracking-wide text-texto-fraco uppercase">
              {["Quando", "Operador", "Ação", "Cliente", "Estação", "Detalhe"].map((t) => (
                <th key={t} className="border-b border-borda px-2.5 py-2 font-medium">
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(acoes ?? []).map((a) => (
              <tr key={a.id} className="border-b border-borda/60 align-top">
                <td className="px-2.5 py-2 whitespace-nowrap text-texto-suave tabular-nums">
                  {dataDoServidor(a.quando).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" })}
                </td>
                <td className="px-2.5 py-2 whitespace-nowrap">{a.operador}</td>
                <td className="px-2.5 py-2 font-medium whitespace-nowrap">{a.rotulo}</td>
                <td className="px-2.5 py-2">
                  {a.cliente_login ? (
                    <>
                      <div>{a.cliente_nome}</div>
                      <div className="text-xs text-texto-fraco">{a.cliente_login}</div>
                    </>
                  ) : (
                    <span className="text-texto-fraco">—</span>
                  )}
                </td>
                <td className="px-2.5 py-2 whitespace-nowrap">
                  {a.estacao ?? <span className="text-texto-fraco">—</span>}
                </td>
                <td className="px-2.5 py-2 text-texto-suave">{a.detalhe}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
