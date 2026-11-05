import { useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import type { Piso } from "@/lib/tipos"
import { Button } from "@/components/ui/button"
import { Campo, Input } from "@/components/ui/campos"

/**
 * Configurações → Pisos: os pisos da biblioteca (Adulto, Infantil...). Cada mapa
 * (grupo) e cada cliente pertence a um, e o cliente só entra nos PCs do seu piso.
 */
export function SecaoPisos() {
  const avisar = useAvisos()
  const { pisos, recarregar } = useDados()
  const [nome, setNome] = useState("")
  const [cor, setCor] = useState("#22c55e")
  const [criando, setCriando] = useState(false)
  const [editando, setEditando] = useState<Record<number, { nome?: string; cor?: string }>>({})

  async function criar(ev: React.FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return
    setCriando(true)
    try {
      await Api.post("/api/pisos/", { nome: nome.trim(), cor })
      avisar("Piso criado")
      setNome("")
      await recarregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setCriando(false)
    }
  }

  async function salvar(p: Piso, mudanca: { nome?: string; cor?: string; padrao?: boolean }) {
    try {
      await Api.put(`/api/pisos/${p.id}`, mudanca)
      setEditando((prev) => {
        const n = { ...prev }
        delete n[p.id]
        return n
      })
      avisar("Piso atualizado")
      await recarregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  async function tornarPadrao(p: Piso) {
    if (
      !window.confirm(
        `Usar ${p.nome} como piso padrão?\n\nO padrão vale para estação sem mapa e mapa antigo ainda sem piso. ` +
          "Os clientes não mudam de piso.",
      )
    )
      return
    await salvar(p, { padrao: true })
  }

  async function excluir(p: Piso) {
    if (!window.confirm(`Excluir o piso ${p.nome}?`)) return
    try {
      await Api.del(`/api/pisos/${p.id}`)
      avisar("Piso excluído")
      await recarregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Pisos</h2>
      <p className="mb-4 text-sm text-texto-fraco">
        Cada mapa (em Mapas) e cada cliente pertence a um piso, e o cliente só entra nos computadores do piso dele. A
        cor aparece no seletor do topo, nas abas e nas colunas do painel.
      </p>
      <div className="mb-5 flex flex-col gap-2">
        {pisos.map((p) => {
          const ed = editando[p.id] ?? {}
          const alterado = (ed.nome !== undefined && ed.nome !== p.nome) || (ed.cor !== undefined && ed.cor !== p.cor)
          return (
            <div
              key={p.id}
              className="flex items-center gap-3 rounded-lg border border-borda bg-superficie-2 px-4 py-2.5"
            >
              <input
                type="color"
                value={ed.cor ?? p.cor}
                onChange={(ev) => setEditando((prev) => ({ ...prev, [p.id]: { ...ed, cor: ev.target.value } }))}
                className="size-7 shrink-0 cursor-pointer rounded-full border-0 bg-transparent p-0"
                title="Cor do piso"
                aria-label={`Cor do piso ${p.nome}`}
              />
              <input
                type="text"
                aria-label={`Nome do piso ${p.nome}`}
                value={ed.nome ?? p.nome}
                onChange={(ev) => setEditando((prev) => ({ ...prev, [p.id]: { ...ed, nome: ev.target.value } }))}
                className="w-40 min-w-0 rounded-md border border-borda bg-superficie px-2 py-1 text-sm outline-none focus:border-destaque"
              />
              <span className="flex-1 text-xs text-texto-fraco">
                {p.grupos} {p.grupos === 1 ? "mapa" : "mapas"} · {p.clientes.toLocaleString("pt-BR")}{" "}
                {p.clientes === 1 ? "cliente" : "clientes"}
              </span>
              {alterado && (
                <Button size="sm" onClick={() => salvar(p, { nome: ed.nome?.trim() || undefined, cor: ed.cor })}>
                  Salvar
                </Button>
              )}
              {p.padrao ? (
                <span className="rounded-full border border-borda px-2 text-xs text-texto-suave">Padrão</span>
              ) : (
                <>
                  <Button size="sm" variant="ghost" onClick={() => tornarPadrao(p)}>
                    Tornar padrão
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => excluir(p)} className="text-perigo">
                    Excluir
                  </Button>
                </>
              )}
            </div>
          )
        })}
      </div>
      <form onSubmit={criar} className="flex items-end gap-2">
        <input
          type="color"
          value={cor}
          onChange={(e) => setCor(e.target.value)}
          className="size-9 shrink-0 cursor-pointer rounded-md border border-borda bg-transparent p-0.5"
          title="Cor do piso"
          aria-label="Cor do piso novo"
        />
        <div className="flex-1">
          <Campo rotulo="Nome do piso novo" id="novo-piso-nome">
            <Input
              id="novo-piso-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="ex: Juvenil"
            />
          </Campo>
        </div>
        <Button type="submit" disabled={criando || !nome.trim()}>
          {criando ? "..." : "+ Criar piso"}
        </Button>
      </form>
    </div>
  )
}
