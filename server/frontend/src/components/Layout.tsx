import { useEffect, useState } from "react"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import {
  IconChevronRight,
  IconHistory,
  IconLayoutSidebar,
  IconPower,
  IconSearch,
  IconSelector,
  IconLayoutDashboard,
  IconMap,
  IconMoon,
  IconSettings,
  IconSpeakerphone,
  IconSun,
  IconUsers,
} from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useDados } from "@/lib/dados"
import { useTema } from "@/lib/tema"
import { BuscaGlobal } from "@/components/BuscaGlobal"
import { cn } from "@/lib/utils"

export interface ContextoLayout {
  menuAberto: boolean
}

/** Subitem do menu: a mesma tela com um parâmetro (?aba= / ?secao=). */
interface Filho {
  rotulo: string
  chave: string
  valor: string
  soAdmin?: boolean
}

export const ITENS: {
  para: string
  rotulo: string
  Icone: typeof IconMap
  soAdmin: boolean
  filhos?: Filho[]
}[] = [
  { para: "/", rotulo: "Painel", Icone: IconLayoutDashboard, soAdmin: false },
  { para: "/clientes", rotulo: "Clientes", Icone: IconUsers, soAdmin: false },
  { para: "/mapa", rotulo: "Mapa", Icone: IconMap, soAdmin: false },
  {
    // o que a biblioteca divulga nos PCs (saiu de Configuracoes)
    para: "/programacao",
    rotulo: "Programação e avisos",
    Icone: IconSpeakerphone,
    soAdmin: true,
    filhos: [
      { rotulo: "Programação", chave: "aba", valor: "programacao" },
      { rotulo: "Avisos", chave: "aba", valor: "avisos" },
    ],
  },
  {
    para: "/historicos",
    rotulo: "Históricos",
    Icone: IconHistory,
    soAdmin: false,
    // as mesmas abas de pages/Historicos.tsx; a primeira é a padrão
    filhos: [
      { rotulo: "Por cliente", chave: "aba", valor: "cliente" },
      { rotulo: "Por estação", chave: "aba", valor: "estacao" },
      { rotulo: "Uso", chave: "aba", valor: "uso", soAdmin: true },
      { rotulo: "Ações dos operadores", chave: "aba", valor: "acoes", soAdmin: true },
    ],
  },
  {
    para: "/configuracoes",
    rotulo: "Configurações",
    Icone: IconSettings,
    soAdmin: true,
    // as mesmas seções de pages/Configuracoes.tsx (SECOES)
    filhos: [
      ["Operadores", "operadores"],
      ["Comportamento", "comportamento"],
      ["Horário", "horario"],
      ["Pisos", "pisos"],
      ["Mapas", "grupos"],
      ["Apps permitidos", "apps"],
      ["Servidor", "servidor"],
      ["Minha conta", "conta"],
    ].map(([rotulo, valor]) => ({ rotulo, chave: "secao", valor })),
  },
]

/**
 * Item com subitens (accordion): o pai abre a tela e mostra os filhos, recuados
 * e ligados por uma linha vertical; a seta gira 90° quando aberto.
 */
function ItemComFilhos({ item, expandida, admin }: { item: (typeof ITENS)[number]; expandida: boolean; admin: boolean }) {
  const { pathname, search } = useLocation()
  const navegar = useNavigate()
  const naTela = pathname.startsWith(item.para)
  const [aberto, setAberto] = useState(naTela)
  useEffect(() => {
    if (naTela) setAberto(true)
  }, [naTela])

  const filhos = (item.filhos ?? []).filter((f) => admin || !f.soAdmin)
  const params = new URLSearchParams(search)
  const ativo = (f: Filho) => naTela && (params.get(f.chave) ?? filhos[0]?.valor) === f.valor
  const { Icone } = item

  if (!expandida) {
    return (
      <NavLink
        to={item.para}
        title={item.rotulo}
        className={({ isActive }) =>
          cn(
            "flex h-9 items-center justify-center rounded-lg transition-all duration-200 ease-in-out",
            isActive ? "bg-texto/10 text-texto" : "text-texto-menu hover:bg-texto/5 hover:text-texto",
          )
        }
      >
        <Icone size={18} className="shrink-0" />
        <span className="sr-only">{item.rotulo}</span>
      </NavLink>
    )
  }

  return (
    <div>
      <button
        type="button"
        aria-expanded={aberto}
        onClick={() => {
          if (!naTela) {
            navegar(item.para)
            setAberto(true)
          } else setAberto((v) => !v)
        }}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap transition-all duration-200 ease-in-out",
          naTela ? "text-texto" : "text-texto-menu hover:bg-texto/5 hover:text-texto",
        )}
      >
        <Icone size={18} className="shrink-0" />
        <span className="flex-1 text-left">{item.rotulo}</span>
        <IconChevronRight
          size={14}
          className={cn("shrink-0 text-texto-fraco transition-transform duration-200 ease-in-out", aberto && "rotate-90")}
        />
      </button>
      <div
        className={cn(
          "grid transition-all duration-300 ease-in-out",
          aberto ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">
          <div className="my-0.5 ml-[18px] flex flex-col gap-px border-l border-borda/80 pl-2.5">
            {filhos.map((f) => (
              <NavLink
                key={f.valor}
                to={`${item.para}?${f.chave}=${f.valor}`}
                tabIndex={aberto ? undefined : -1}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-[12px] whitespace-nowrap transition-all duration-200 ease-in-out",
                  ativo(f)
                    ? "bg-texto/10 font-medium text-texto"
                    : "font-normal text-texto-sub hover:bg-texto/5 hover:text-texto",
                )}
              >
                {f.rotulo}
              </NavLink>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function lerExpandida() {
  try {
    return localStorage.getItem("sidebarExpandida") === "1"
  } catch {
    return false
  }
}

/** Seletor de piso em pílula: o ativo na cor do piso. */
export function SeletorPiso({ className }: { className?: string }) {
  const { pisos, piso, trocarPiso } = useDados()
  return (
    <div
      role="radiogroup"
      aria-label="Piso"
      className={cn("flex rounded-xl border border-borda bg-superficie-2 p-1", className)}
    >
      {pisos.map((p) => {
        const ativo = piso?.id === p.id
        return (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={ativo}
            onClick={() => trocarPiso(p.id)}
            title={`Mostrar só as estações, a fila e os clientes do piso ${p.nome}`}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-semibold transition-all duration-300 ease-in-out",
              ativo ? "text-zinc-50 shadow-md" : "text-texto-suave hover:text-texto",
            )}
            style={ativo ? { background: p.cor, boxShadow: `0 4px 12px -4px ${p.cor}` } : undefined}
          >
            {!ativo && <span className="size-2 rounded-full" style={{ background: p.cor }} />}
            Piso {p.nome}
          </button>
        )
      })}
    </div>
  )
}

export function Layout() {
  const [expandida, setExpandida] = useState(lerExpandida)
  const [buscando, setBuscando] = useState(false)
  const { tempoReal } = useDados()
  const admin = Api.ehAdmin()
  const { tema, alternar: alternarTema } = useTema()
  const { pathname } = useLocation()
  const atual = ITENS.find((i) => (i.para === "/" ? pathname === "/" : pathname.startsWith(i.para)))
  // o piso so muda o que aparece no Painel, em Clientes e no Mapa; Historicos
  // tem o filtro dele e Configuracoes vale para todos os pisos
  // o seletor de piso fica dentro de cada tela que usa (Painel e Mapa; Clientes tem as abas de piso)

  // Ctrl+K (ou Cmd+K no Mac) abre a busca de qualquer tela
  useEffect(() => {
    const aoTeclar = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault()
        setBuscando((v) => !v)
      }
    }
    document.addEventListener("keydown", aoTeclar)
    return () => document.removeEventListener("keydown", aoTeclar)
  }, [])

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

  const nome = Api.nome() ?? ""
  return (
    <div className="transicao-piso flex h-full bg-fundo">
      <nav
        aria-label="Menu principal"
        className={cn(
          "flex shrink-0 flex-col overflow-hidden border-r border-borda bg-fundo transition-[width] duration-300 ease-in-out",
          expandida ? "w-[260px]" : "w-16",
        )}
      >
        {/* WorkspaceSwitcher: a unidade e o perfil de quem entrou */}
        <div className="flex h-14 shrink-0 items-center px-3">
          <div
            className={cn(
              "flex w-full items-center gap-2.5 rounded-lg p-1.5 transition-all duration-200 ease-in-out hover:bg-texto/5",
              !expandida && "justify-center",
            )}
            title="MatheCafé"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-destaque text-sm font-semibold text-zinc-100">
              M
            </span>
            {expandida && (
              <span className="flex min-w-0 flex-col leading-tight">
                <span className="truncate text-sm font-semibold">MatheCafé</span>
                <span className="truncate text-xs text-texto-fraco capitalize">SP Leituras · {Api.perfil()}</span>
              </span>
            )}
            {expandida && <IconSelector size={16} className="ml-auto shrink-0 text-texto-fraco" />}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2">
          {(
            [
              ["Operação", ITENS.slice(0, 4)],
              ["Gestão", ITENS.slice(4)],
            ] as const
          ).map(([grupo, itens]) => (
            <div key={grupo} className="mb-3">
              {expandida ? (
                <p className="px-2.5 pb-1.5 text-[11px] font-semibold tracking-[0.05em] text-rotulo uppercase">{grupo}</p>
              ) : (
                grupo !== "Operação" && <span className="mx-auto mb-2 block h-px w-6 bg-borda" />
              )}
              <div className="flex flex-col gap-0.5">
                {itens
                  .filter((i) => admin || !i.soAdmin)
                  .map((item) =>
                    item.filhos ? (
                      <ItemComFilhos key={item.para} item={item} expandida={expandida} admin={admin} />
                    ) : (
                      <NavLink
                        key={item.para}
                        to={item.para}
                        end={item.para === "/"}
                        title={item.rotulo}
                        className={({ isActive }) =>
                          cn(
                            "flex items-center gap-3 rounded-lg px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap transition-all duration-200 ease-in-out",
                            !expandida && "h-9 justify-center px-0 py-0",
                            isActive ? "bg-texto/10 text-texto" : "text-texto-menu hover:bg-texto/5 hover:text-texto",
                          )
                        }
                      >
                        <item.Icone size={18} className="shrink-0" />
                        <span className={cn(!expandida && "sr-only")}>{item.rotulo}</span>
                      </NavLink>
                    ),
                  )}
              </div>
            </div>
          ))}
        </div>

        {/* quem está usando o painel */}
        <div className="shrink-0 border-t border-borda p-3">
          <div className={cn("flex items-center gap-2.5", !expandida && "flex-col")}>
            <span
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-superficie-3 text-xs font-semibold text-texto-suave"
              title={nome}
            >
              {nome.slice(0, 1).toUpperCase()}
            </span>
            {expandida && (
              <span className="flex min-w-0 flex-1 flex-col leading-tight">
                <span className="truncate text-sm">{nome}</span>
                <span className="text-[11px] text-texto-fraco capitalize">{Api.perfil()}</span>
              </span>
            )}
          </div>
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-borda px-4">
          <button
            type="button"
            onClick={alternar}
            title={expandida ? "Recolher menu" : "Expandir menu"}
            aria-label={expandida ? "Recolher menu" : "Expandir menu"}
            className="rounded-md p-1.5 text-texto-suave transition-all duration-200 ease-in-out hover:bg-texto/5 hover:text-texto"
          >
            <IconLayoutSidebar size={18} />
          </button>
          <span className="h-4 w-px bg-borda" />
          <nav aria-label="Você está em" className="flex items-center gap-1.5 text-sm">
            <span className="text-texto-fraco">MatheCafé</span>
            <IconChevronRight size={14} className="text-texto-fraco" />
            <span className="font-medium">{pathname === "/" ? "Painel principal" : (atual?.rotulo ?? "")}</span>
          </nav>


          <div className="flex-1" />
          <button
            type="button"
            onClick={() => setBuscando(true)}
            className="flex h-8 w-56 items-center gap-2 rounded-xl border border-borda bg-superficie/60 px-2.5 text-sm text-texto-fraco backdrop-blur transition-all duration-200 ease-in-out hover:bg-texto/5 hover:text-texto-suave"
          >
            <IconSearch size={15} />
            <span>Buscar...</span>
            <kbd className="ml-auto rounded border border-borda bg-superficie-3 px-1.5 text-[10px] font-medium">Ctrl K</kbd>
          </button>
          <span
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-medium",
              tempoReal ? "border-livre-borda bg-livre-fundo text-livre" : "border-borda bg-superficie-2 text-texto-fraco",
            )}
            title={tempoReal ? "Recebendo as mudanças na hora" : "Sem conexão com o servidor: tentando de novo"}
          >
            <span className="relative flex size-2">
              {tempoReal && <span className="absolute inline-flex size-full animate-ping rounded-full bg-livre opacity-60" />}
              <span className={cn("relative inline-flex size-2 rounded-full", tempoReal ? "bg-livre" : "bg-desligada")} />
            </span>
            <span className="hidden lg:inline">{tempoReal ? "Tempo real" : "Reconectando..."}</span>
          </span>
          <button
            type="button"
            onClick={alternarTema}
            title={tema === "claro" ? "Usar o tema escuro" : "Usar o tema claro"}
            aria-label={tema === "claro" ? "Usar o tema escuro" : "Usar o tema claro"}
            className="rounded-md p-1.5 text-texto-suave transition-all duration-200 ease-in-out hover:bg-texto/5 hover:text-texto"
          >
            {tema === "claro" ? <IconMoon size={18} /> : <IconSun size={18} />}
          </button>
          <button
            type="button"
            onClick={() => Api.sair()}
            title="Encerrar a sessão no painel"
            className="flex items-center gap-1.5 rounded-xl border border-perigo-borda bg-perigo-fundo px-3 py-1.5 text-xs font-semibold text-perigo transition-all duration-200 hover:brightness-110 active:scale-95"
          >
            <IconPower size={14} />
            Sair
          </button>
        </header>
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {/* as telas sabem se o menu está aberto (Configurações esconde a lista própria) */}
          <Outlet context={{ menuAberto: expandida } satisfies ContextoLayout} />
        </main>
      </div>
      <BuscaGlobal aberta={buscando} aoFechar={() => setBuscando(false)} />
    </div>
  )
}

/** Cabeçalho padrão das telas Clientes e Mapa. */
export function CabecalhoTela({ titulo, children }: { titulo: string; children?: React.ReactNode }) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-borda px-6 py-3.5">
      <h1 className="text-lg font-semibold tracking-tight">{titulo}</h1>
      {children}
    </div>
  )
}
