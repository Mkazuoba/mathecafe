import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { IconChevronDown, IconChevronUp, IconId, IconMessageCircle, IconPencil, IconSelector } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { FILTROS_PADRAO, gravarFiltros, lerFiltros, useBuscaClientes, type FiltrosClientes } from "@/lib/buscaClientes"
import { dataDoServidor, formatarTempo } from "@/lib/tempo"
import type { Cliente } from "@/lib/tipos"
import { CabecalhoTela } from "@/components/Layout"
import { FichaCliente } from "@/components/FichaCliente"
import { FiltrosBusca } from "@/components/FiltrosBusca"
import { ModalNovoCliente } from "@/components/ModalNovoCliente"
import { ModalSaldo } from "@/components/ModalSaldo"
import { Button } from "@/components/ui/button"
import { Input, Select } from "@/components/ui/campos"
import { SeloAtivo, Vazio } from "@/components/ui/status"

// Até quantos clientes a tabela mostra (são ~43k): passou disso, refinar a busca
const LIMITE = 200
const COLUNAS: { titulo: string; ordem?: FiltrosClientes["ordem"] }[] = [
  { titulo: "Login", ordem: "login" },
  { titulo: "Nome", ordem: "nome" },
  { titulo: "Tempo de hoje", ordem: "saldo" },
  { titulo: "Status" },
  { titulo: "Criado em", ordem: "criado" },
  { titulo: "" },
]

export default function Clientes() {
  const navigate = useNavigate()
  const admin = Api.ehAdmin()
  const [busca, setBusca] = useState("")
  const [filtros, setFiltros] = useState(() => lerFiltros("clientes.busca", FILTROS_PADRAO))
  const [novo, setNovo] = useState(false)
  const [ficha, setFicha] = useState<number | null>(null)
  const [editandoSaldo, setEditandoSaldo] = useState<Cliente | null>(null)

  const { clientes: lista, carregando } = useBuscaClientes(busca, filtros, { tudo: true, limite: LIMITE })

  function mudarFiltros(f: FiltrosClientes) {
    setFiltros(f)
    gravarFiltros("clientes.busca", f)
  }
  function ordenar(ordem: FiltrosClientes["ordem"]) {
    mudarFiltros({ ...filtros, ordem, desc: filtros.ordem === ordem ? !filtros.desc : false })
  }
  const dica = filtros.campo === "login" ? "Buscar por login..." : filtros.campo === "nome" ? "Buscar por nome..." : "Buscar por nome ou login..."

  return (
    <>
      <CabecalhoTela titulo="Clientes">
        <Input
          type="search"
          aria-label="Buscar cliente"
          placeholder={dica}
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          className="h-9 w-64"
        />
        <Select
          aria-label="Filtrar por status"
          value={filtros.status}
          onChange={(e) => mudarFiltros({ ...filtros, status: e.target.value as FiltrosClientes["status"] })}
          className="h-9 w-32"
        >
          <option value="todos">Todos</option>
          <option value="ativos">Ativos</option>
          <option value="inativos">Inativos</option>
        </Select>
        <FiltrosBusca
          className="h-9"
          valor={filtros}
          padrao={FILTROS_PADRAO}
          campos={["campo", "modo", "saldo", "ordem"]}
          aoMudar={mudarFiltros}
        />
        <div className="flex-1" />
        {admin && (
          <Button variant="outline" size="sm" onClick={() => navigate("/configuracoes?secao=relatorios")}>
            Exportar CSV
          </Button>
        )}
        <Button size="sm" onClick={() => setNovo(true)}>
          + Novo cliente
        </Button>
      </CabecalhoTela>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs tracking-wide text-texto-fraco uppercase">
              {COLUNAS.map(({ titulo, ordem }) => {
                const ativa = ordem && filtros.ordem === ordem
                return (
                  <th
                    key={titulo || "ficha"}
                    aria-sort={ativa ? (filtros.desc ? "descending" : "ascending") : undefined}
                    className="border-b border-borda px-2.5 py-2 font-medium"
                  >
                    {ordem ? (
                      <button
                        type="button"
                        title="Ordenar"
                        onClick={() => ordenar(ordem)}
                        className={"inline-flex items-center gap-0.5 uppercase hover:text-texto " + (ativa ? "text-texto" : "")}
                      >
                        {titulo}
                        {ativa ? (
                          filtros.desc ? <IconChevronDown size={13} /> : <IconChevronUp size={13} />
                        ) : (
                          <IconSelector size={13} className="opacity-40" />
                        )}
                      </button>
                    ) : (
                      titulo
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr
                key={c.id}
                tabIndex={0}
                title="Abrir a ficha do cliente"
                onClick={() => setFicha(c.id)}
                onKeyDown={(e) => e.key === "Enter" && e.target === e.currentTarget && setFicha(c.id)}
                className="cursor-pointer hover:bg-superficie-2 focus-visible:bg-superficie-2 focus-visible:outline-none"
              >
                <td className="border-b border-borda px-2.5 py-2.5">{c.login}</td>
                <td className="border-b border-borda px-2.5 py-2.5">
                  <div>{c.nome}</div>
                  {c.observacao && (
                    <div className="mt-0.5 flex items-center gap-1 text-xs text-texto-fraco">
                      <IconMessageCircle size={11} /> {c.observacao}
                    </div>
                  )}
                </td>
                <td className="border-b border-borda px-2.5 py-2.5">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditandoSaldo(c)
                    }}
                    title="Dar tempo extra"
                    className={
                      "inline-flex cursor-pointer items-center gap-1.5 tabular-nums " +
                      (c.saldo_segundos > 0 ? "font-semibold text-livre" : "text-texto-fraco")
                    }
                  >
                    {formatarTempo(c.saldo_segundos)}
                    <IconPencil size={13} className="text-texto-fraco" />
                  </button>
                </td>
                <td className="border-b border-borda px-2.5 py-2.5">
                  <SeloAtivo ativo={c.ativo} />
                </td>
                <td className="border-b border-borda px-2.5 py-2.5 text-texto-suave">
                  {c.criado_em ? dataDoServidor(c.criado_em).toLocaleDateString("pt-BR") : "—"}
                </td>
                <td className="border-b border-borda px-2.5 py-2.5 text-right">
                  <Button
                    variant="outline"
                    size="xs"
                    className="gap-1"
                    onClick={(e) => {
                      e.stopPropagation()
                      setFicha(c.id)
                    }}
                  >
                    <IconId size={14} /> Ficha
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!lista.length ? (
          <Vazio>{carregando ? "Buscando..." : "Nenhum cliente encontrado"}</Vazio>
        ) : (
          <div className="py-3 text-center text-xs text-texto-fraco">
            {lista.length >= LIMITE
              ? `Mostrando os primeiros ${LIMITE} clientes. Refine a busca ou os filtros para achar os outros.`
              : `${lista.length} cliente${lista.length > 1 ? "s" : ""}`}
          </div>
        )}
      </div>

      <ModalNovoCliente
        aberto={novo}
        aoFechar={() => setNovo(false)}
        aoCriar={(c) => {
          setNovo(false)
          setFicha(c.id) // já abre a ficha para pôr a foto
        }}
      />
      <FichaCliente clienteId={ficha} aoFechar={() => setFicha(null)} />
      <ModalSaldo cliente={editandoSaldo} aoFechar={() => setEditandoSaldo(null)} />
    </>
  )
}
