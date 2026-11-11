import { Navigate, useSearchParams } from "react-router-dom"
import { Api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { CabecalhoTela } from "@/components/Layout"
import { SecaoAvisos } from "@/components/SecaoAvisos"
import { SecaoProgramacao } from "@/components/SecaoProgramacao"

const ABAS = [
  { id: "programacao", rotulo: "Programação" },
  { id: "avisos", rotulo: "Avisos" },
] as const
type Aba = (typeof ABAS)[number]["id"]

/**
 * Programação (cartazes na tela de login do PC) e Avisos (à direita da tela de
 * apps): o que a biblioteca divulga nas estações. Saiu de Configurações.
 */
export default function Divulgacao() {
  const [params, setParams] = useSearchParams()
  if (!Api.ehAdmin()) return <Navigate to="/" replace />
  const aba = (ABAS.find((a) => a.id === params.get("aba"))?.id ?? "programacao") as Aba

  return (
    <>
      <CabecalhoTela titulo="Programação e avisos">
        <div className="flex rounded-md border border-borda bg-superficie-2 p-0.5 text-sm" role="tablist">
          {ABAS.map((a) => (
            <button
              key={a.id}
              type="button"
              role="tab"
              aria-selected={aba === a.id}
              onClick={() => setParams({ aba: a.id })}
              className={cn(
                "rounded px-3 py-1 transition-all duration-200 ease-in-out",
                aba === a.id ? "bg-destaque text-zinc-100" : "text-texto-suave hover:text-texto",
              )}
            >
              {a.rotulo}
            </button>
          ))}
        </div>
      </CabecalhoTela>
      <div className="min-h-0 flex-1 overflow-auto px-8 py-6">
        <div className="max-w-2xl">{aba === "programacao" ? <SecaoProgramacao /> : <SecaoAvisos />}</div>
      </div>
    </>
  )
}
