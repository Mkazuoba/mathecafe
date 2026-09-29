import { useEffect, useMemo, useRef, useState } from "react"
import { IconX } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAcoes } from "@/lib/acoes"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { formatarTempo, restanteDaSessao } from "@/lib/tempo"
import type { Estacao, StatusEstacao } from "@/lib/tipos"
import { cn } from "@/lib/utils"
import { CabecalhoTela } from "@/components/Layout"
import { Button } from "@/components/ui/button"
import { Campo, Input, MensagemErro, Select } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"
import { SeloStatus, Vazio } from "@/components/ui/status"

const SEM_GRUPO = -1
const TAMANHO_PINO = 80

const BORDA_PINO: Record<StatusEstacao, string> = {
  livre: "border-b-livre",
  ocupada: "border-b-ocupada bg-superficie-3",
  desligada: "border-b-desligada opacity-60",
  manutencao: "border-b-manutencao opacity-85",
}

export default function Mapa() {
  const { estacoes, grupos, recarregarEstacoes } = useDados()
  const avisar = useAvisos()
  const admin = Api.ehAdmin()
  const [grupoAtivo, setGrupoAtivo] = useState<number | null>(null)
  const [modoConfig, setModoConfig] = useState(false)
  const [selecionada, setSelecionada] = useState<number | null>(null)
  const [criando, setCriando] = useState(false)

  const temSemGrupo = estacoes.some((e) => e.grupo_id === null)
  const abas = useMemo(
    () => [...grupos.map((g) => ({ id: g.id, nome: g.nome })), ...(temSemGrupo ? [{ id: SEM_GRUPO, nome: "Sem grupo" }] : [])],
    [grupos, temSemGrupo],
  )
  // A aba escolhida pode sumir (ex.: "Sem grupo" quando a última estação muda de grupo)
  const grupo = abas.some((a) => a.id === grupoAtivo) ? grupoAtivo : (abas[0]?.id ?? null)
  const doGrupo = estacoes.filter((e) => (grupo === SEM_GRUPO ? e.grupo_id === null : e.grupo_id === grupo))
  const ocupadas = doGrupo.filter((e) => e.status === "ocupada").length
  const estacaoSelecionada = estacoes.find((e) => e.id === selecionada)

  async function excluir(e: Estacao) {
    if (!window.confirm(`Excluir a estação ${e.nome}?`)) return
    try {
      const r = await Api.del<{ desativada?: boolean }>(`/api/estacoes/${e.id}`)
      avisar(r.desativada ? "Estação removida do painel (o histórico de uso foi mantido)" : "Estação excluída")
      await recarregarEstacoes()
    } catch (err) {
      avisar((err as Error).message, "erro")
    }
  }

  return (
    <>
      <CabecalhoTela titulo="Mapa">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Grupos de estações">
          {abas.map((a) => (
            <button
              key={a.id}
              type="button"
              role="tab"
              aria-selected={a.id === grupo}
              onClick={() => setGrupoAtivo(a.id)}
              className={cn(
                "cursor-pointer rounded-md border px-3.5 py-1.5 text-sm",
                a.id === grupo
                  ? "border-destaque bg-destaque text-white"
                  : "border-borda bg-superficie-2 text-texto-suave hover:text-texto",
              )}
            >
              {a.nome}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <span className="text-sm text-texto-suave">
          {ocupadas}/{doGrupo.length} ocupadas
        </span>
        {admin && (
          <Button
            variant={modoConfig ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setModoConfig((v) => !v)
              setSelecionada(null)
            }}
          >
            {modoConfig ? "Concluir configuração" : "Modo configuração"}
          </Button>
        )}
      </CabecalhoTela>

      <div className="fundo-pontilhado relative min-h-0 flex-1 overflow-auto">
        <div className="relative min-h-[700px] min-w-[1000px]">
          {modoConfig && (
            <Button size="sm" variant="outline" className="absolute top-3 left-3 z-10" onClick={() => setCriando(true)}>
              + Adicionar estação
            </Button>
          )}
          {doGrupo.length ? (
            doGrupo.map((e) => (
              <Pino
                key={e.id}
                estacao={e}
                modoConfig={modoConfig}
                aoClicar={() => setSelecionada(e.id)}
                aoExcluir={() => excluir(e)}
              />
            ))
          ) : (
            <div className="pt-16">
              <Vazio>
                Nenhuma estação neste grupo.
                {admin && !modoConfig && " Use o Modo configuração para cadastrar."}
              </Vazio>
            </div>
          )}
        </div>
      </div>

      {estacaoSelecionada && !modoConfig && (
        <PainelDetalhe estacao={estacaoSelecionada} aoFechar={() => setSelecionada(null)} />
      )}
      <ModalNovaEstacao
        aberto={criando}
        grupoInicial={grupo !== SEM_GRUPO ? grupo : null}
        aoFechar={() => setCriando(false)}
      />
    </>
  )
}

function Pino({
  estacao: e,
  modoConfig,
  aoClicar,
  aoExcluir,
}: {
  estacao: Estacao
  modoConfig: boolean
  aoClicar: () => void
  aoExcluir: () => void
}) {
  const { sessaoDaEstacao, agora, recarregarEstacoes } = useDados()
  const avisar = useAvisos()
  const sessao = sessaoDaEstacao(e.nome)
  const [pos, setPos] = useState({ x: e.pos_x || 0, y: e.pos_y || 0 })
  const arrasto = useRef<{ dx: number; dy: number } | null>(null)

  useEffect(() => setPos({ x: e.pos_x || 0, y: e.pos_y || 0 }), [e.pos_x, e.pos_y])

  function aoPressionar(ev: React.PointerEvent<HTMLDivElement>) {
    if (!modoConfig || (ev.target as HTMLElement).closest("button")) return
    ev.currentTarget.setPointerCapture(ev.pointerId)
    arrasto.current = { dx: ev.clientX - pos.x, dy: ev.clientY - pos.y }
  }
  function aoMover(ev: React.PointerEvent) {
    if (!arrasto.current) return
    setPos({
      x: Math.max(0, Math.round(ev.clientX - arrasto.current.dx)),
      y: Math.max(0, Math.round(ev.clientY - arrasto.current.dy)),
    })
  }
  async function aoSoltar() {
    if (!arrasto.current) return
    arrasto.current = null
    if (pos.x === e.pos_x && pos.y === e.pos_y) return
    try {
      await Api.put(`/api/estacoes/${e.id}/posicao`, { pos_x: pos.x, pos_y: pos.y })
      await recarregarEstacoes()
    } catch (err) {
      avisar((err as Error).message, "erro")
      setPos({ x: e.pos_x, y: e.pos_y })
    }
  }

  return (
    <div
      role={modoConfig ? undefined : "button"}
      tabIndex={modoConfig ? undefined : 0}
      aria-label={modoConfig ? undefined : `Estação ${e.nome}, ${e.status}`}
      onClick={() => !modoConfig && aoClicar()}
      onKeyDown={(ev) => !modoConfig && (ev.key === "Enter" || ev.key === " ") && aoClicar()}
      onPointerDown={aoPressionar}
      onPointerMove={aoMover}
      onPointerUp={aoSoltar}
      style={{ left: pos.x, top: pos.y, width: TAMANHO_PINO, height: TAMANHO_PINO }}
      className={cn(
        "absolute flex touch-none flex-col items-center justify-center rounded-[10px] border border-b-[3px] border-borda bg-superficie-2 select-none",
        BORDA_PINO[e.status],
        modoConfig ? "cursor-grab border-dashed active:cursor-grabbing" : "cursor-pointer hover:ring-2 hover:ring-borda-forte",
      )}
    >
      <span className="text-sm font-bold">{e.nome}</span>
      {sessao && (
        <>
          <span className="max-w-[70px] truncate text-[0.62rem] text-texto-suave">{sessao.cliente_nome}</span>
          <span className="text-[0.62rem] font-semibold text-ocupada tabular-nums">
            {formatarTempo(restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora))}
          </span>
        </>
      )}
      {modoConfig && (
        <button
          type="button"
          onClick={aoExcluir}
          aria-label={`Excluir estação ${e.nome}`}
          className="absolute -top-2 -right-2 flex size-5 cursor-pointer items-center justify-center rounded-full bg-perigo text-white"
        >
          <IconX size={12} />
        </button>
      )}
    </div>
  )
}

function PainelDetalhe({ estacao: e, aoFechar }: { estacao: Estacao; aoFechar: () => void }) {
  const { sessaoDaEstacao, agora, grupos, recarregarEstacoes } = useDados()
  const { encerrarSessao } = useAcoes()
  const avisar = useAvisos()
  const sessao = sessaoDaEstacao(e.nome)

  async function mudarGrupo(valor: string) {
    try {
      await Api.put(`/api/estacoes/${e.id}`, { grupo_id: Number(valor) })
      avisar("Grupo alterado")
      await recarregarEstacoes()
    } catch (err) {
      avisar((err as Error).message, "erro")
    }
  }

  return (
    <aside className="fixed top-[52px] right-0 bottom-0 z-[80] w-80 overflow-y-auto border-l border-borda bg-superficie p-5">
      <button
        type="button"
        onClick={aoFechar}
        aria-label="Fechar detalhes"
        className="absolute top-4 right-4 cursor-pointer text-texto-suave hover:text-texto"
      >
        <IconX size={18} />
      </button>
      <h3 className="mb-4 text-lg font-semibold">{e.nome}</h3>
      <Linha rotulo="Status">
        <SeloStatus status={e.status} />
      </Linha>
      <Linha rotulo="Grupo">
        {Api.ehAdmin() ? (
          <Select aria-label="Grupo da estação" value={e.grupo_id ?? ""} onChange={(ev) => mudarGrupo(ev.target.value)} className="h-9">
            {e.grupo_id === null && <option value="">Sem grupo</option>}
            {grupos.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nome}
              </option>
            ))}
          </Select>
        ) : (
          (e.grupo_nome ?? "Sem grupo")
        )}
      </Linha>
      {sessao && (
        <>
          <Linha rotulo="Cliente">
            {sessao.cliente_nome} ({sessao.cliente_login})
          </Linha>
          <Linha rotulo="Tempo total">{formatarTempo(sessao.tempo_total_segundos)}</Linha>
          <Linha rotulo="Tempo restante">
            <span className="tabular-nums">
              {formatarTempo(restanteDaSessao(sessao.iniciada_em, sessao.tempo_total_segundos, agora))}
            </span>
          </Linha>
          <Button
            variant="perigo"
            className="mt-4 w-full"
            onClick={async () => (await encerrarSessao(sessao.id, e.nome)) && aoFechar()}
          >
            Encerrar sessão
          </Button>
        </>
      )}
    </aside>
  )
}

function Linha({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 text-sm">
      <span className="mb-0.5 block text-xs text-texto-fraco uppercase">{rotulo}</span>
      {children}
    </div>
  )
}

function ModalNovaEstacao({
  aberto,
  grupoInicial,
  aoFechar,
}: {
  aberto: boolean
  grupoInicial: number | null
  aoFechar: () => void
}) {
  const { grupos, recarregarEstacoes } = useDados()
  const avisar = useAvisos()
  const [nome, setNome] = useState("")
  const [grupoId, setGrupoId] = useState("")
  const [erro, setErro] = useState("")

  useEffect(() => {
    if (aberto) {
      setNome("")
      setErro("")
      setGrupoId(String(grupoInicial ?? grupos[0]?.id ?? ""))
    }
  }, [aberto, grupoInicial, grupos])

  async function criar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return setErro("Informe o nome da estação")
    try {
      const params = new URLSearchParams({ nome: nome.trim() })
      if (grupoId) params.append("grupo_id", grupoId)
      await Api.post(`/api/estacoes/?${params}`)
      avisar("Estação criada")
      aoFechar()
      await recarregarEstacoes()
    } catch (e) {
      setErro((e as Error).message)
    }
  }

  return (
    <Modal titulo="Nova estação" aberto={aberto} aoFechar={aoFechar}>
      <form onSubmit={criar} className="flex flex-col gap-4">
        <Campo rotulo="Nome da estação" id="est-nome">
          <Input id="est-nome" placeholder="ex: PC-01" autoComplete="off" value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />
        </Campo>
        <Campo rotulo="Grupo" id="est-grupo">
          <Select id="est-grupo" value={grupoId} onChange={(e) => setGrupoId(e.target.value)}>
            {grupos.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nome}
              </option>
            ))}
          </Select>
        </Campo>
        <p className="text-xs text-texto-fraco">
          O nome precisa ser o mesmo usado no agente: <code>--estacao {nome.trim() || "PC-01"}</code>
        </p>
        <MensagemErro>{erro}</MensagemErro>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={aoFechar}>
            Cancelar
          </Button>
          <Button type="submit" className="flex-1">
            Criar
          </Button>
        </div>
      </form>
    </Modal>
  )
}
