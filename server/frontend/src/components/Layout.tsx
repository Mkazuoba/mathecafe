import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import {
  IconChevronsLeft,
  IconChevronsRight,
  IconLayoutDashboard,
  IconMap,
  IconSettings,
  IconUsers,
} from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useDados } from "@/lib/dados"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const ITENS = [
  { para: "/", rotulo: "Painel", Icone: IconLayoutDashboard, soAdmin: false },
  { para: "/clientes", rotulo: "Clientes", Icone: IconUsers, soAdmin: false },
  { para: "/mapa", rotulo: "Mapa", Icone: IconMap, soAdmin: false },
  { para: "/configuracoes", rotulo: "Configurações", Icone: IconSettings, soAdmin: true },
]

function lerExpandida() {
  try {
    return localStorage.getItem("sidebarExpandida") === "1"
  } catch {
    return false
  }
}

export function Layout() {
  const [expandida, setExpandida] = useState(lerExpandida)
  const { tempoReal } = useDados()
  const admin = Api.ehAdmin()

  function alternar() {
    setExpandida((v) => {
      try {
        localStorage.setItem("sidebarExpandida", v ? "0" : "1")
      } catch {
        /* sem armazenamento */
      }
      return !v
    })
  }

  return (
    <div className="flex h-full">
      <nav
        aria-label="Menu principal"
        className={cn(
          "flex shrink-0 flex-col overflow-hidden border-r border-borda bg-fundo transition-[width] duration-200",
          expandida ? "w-52" : "w-[52px]",
        )}
      >
        <button
          type="button"
          onClick={alternar}
          title={expandida ? "Recolher menu" : "Expandir menu"}
          aria-label={expandida ? "Recolher menu" : "Expandir menu"}
          className="flex h-[52px] shrink-0 cursor-pointer items-center justify-center border-b border-borda text-texto-suave hover:text-texto"
        >
          {expandida ? <IconChevronsLeft size={18} /> : <IconChevronsRight size={18} />}
        </button>
        <div className="flex-1 py-2">
          {ITENS.filter((i) => admin || !i.soAdmin).map(({ para, rotulo, Icone }) => (
            <NavLink
              key={para}
              to={para}
              end={para === "/"}
              title={rotulo}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3.5 border-l-[3px] px-[13px] py-3 text-[13px] font-medium whitespace-nowrap transition-colors",
                  isActive
                    ? "border-l-destaque bg-destaque/15 text-texto"
                    : "border-l-transparent text-texto-suave hover:bg-white/5 hover:text-texto",
                )
              }
            >
              <Icone size={20} className="shrink-0" />
              <span className={cn(!expandida && "sr-only")}>{rotulo}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[52px] shrink-0 items-center gap-4 border-b border-borda bg-superficie px-5">
          <span className="text-[1.05rem] font-bold tracking-wide text-destaque">MatheCafé</span>
          <span className="rounded-md border border-borda bg-superficie-3 px-2.5 py-0.5 text-xs text-texto-suave uppercase">
            {Api.perfil()}
          </span>
          <div className="flex-1" />
          <span className="flex items-center gap-1.5 text-xs text-texto-fraco">
            <span className={cn("size-2 rounded-full", tempoReal ? "bg-livre" : "bg-desligada")} />
            {tempoReal ? "tempo real" : "reconectando..."}
          </span>
          <span className="text-sm text-texto-suave">{Api.nome()}</span>
          <Button variant="outline" size="sm" onClick={() => Api.sair()}>
            Sair
          </Button>
        </header>
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

/** Cabeçalho padrão das telas Clientes e Mapa. */
export function CabecalhoTela({ titulo, children }: { titulo: string; children?: React.ReactNode }) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-borda bg-superficie px-6 py-3.5">
      <h1 className="text-lg font-bold">{titulo}</h1>
      {children}
    </div>
  )
}
