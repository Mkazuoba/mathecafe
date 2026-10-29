import { useEffect, useRef, useState } from "react"
import { IconX } from "@tabler/icons-react"
import { useBuscaClientes } from "@/lib/buscaClientes"
import type { Cliente } from "@/lib/tipos"
import { Input } from "@/components/ui/campos"

export type ClienteResumo = Pick<Cliente, "id" | "login" | "nome">

/** Escolher um cliente buscando no servidor (são ~43k, não cabem num select). */
export function SeletorCliente({ id, valor, aoMudar, placeholder = "Todos — digite para buscar" }: {
  id?: string
  valor: ClienteResumo | null
  aoMudar: (c: ClienteResumo | null) => void
  placeholder?: string
}) {
  const [busca, setBusca] = useState("")
  const [aberto, setAberto] = useState(false)
  const caixa = useRef<HTMLDivElement>(null)
  const { clientes, carregando } = useBuscaClientes(busca, {}, { limite: 8 })

  useEffect(() => {
    if (!aberto) return
    const fora = (ev: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(ev.target as Node)) setAberto(false)
    }
    document.addEventListener("mousedown", fora)
    return () => document.removeEventListener("mousedown", fora)
  }, [aberto])

  if (valor) {
    return (
      <div className="flex h-10 items-center justify-between gap-2 rounded-md border border-borda bg-superficie-2 px-3 text-sm">
        <span className="truncate">
          {valor.nome} <span className="text-texto-fraco">({valor.login})</span>
        </span>
        <button
          type="button"
          onClick={() => aoMudar(null)}
          title="Tirar o filtro de cliente"
          className="shrink-0 rounded p-0.5 text-texto-fraco hover:text-texto"
        >
          <IconX size={15} />
        </button>
      </div>
    )
  }

  const mostrar = aberto && busca.trim() !== ""
  return (
    <div ref={caixa} className="relative">
      <Input
        id={id}
        type="search"
        autoComplete="off"
        placeholder={placeholder}
        value={busca}
        onChange={(e) => {
          setBusca(e.target.value)
          setAberto(true)
        }}
        onFocus={() => setAberto(true)}
        onKeyDown={(e) => e.key === "Escape" && setAberto(false)}
      />
      {mostrar && (
        <ul role="listbox" className="absolute top-full right-0 left-0 z-30 mt-1 max-h-64 overflow-y-auto rounded-md border border-borda bg-superficie py-1 shadow-xl">
          {clientes.length ? (
            clientes.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => {
                    aoMudar(c)
                    setBusca("")
                    setAberto(false)
                  }}
                  className="w-full px-3 py-1.5 text-left text-sm hover:bg-superficie-2"
                >
                  {c.nome} <span className="text-texto-fraco">({c.login})</span>
                </button>
              </li>
            ))
          ) : (
            <li className="px-3 py-1.5 text-sm text-texto-fraco">{carregando ? "Buscando..." : "Nenhum cliente encontrado"}</li>
          )}
        </ul>
      )}
    </div>
  )
}
