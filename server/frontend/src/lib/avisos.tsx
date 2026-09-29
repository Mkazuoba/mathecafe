import { createContext, useCallback, useContext, useState } from "react"
import { cn } from "@/lib/utils"

type Tipo = "ok" | "erro"
interface Aviso {
  id: number
  texto: string
  tipo: Tipo
}

const AvisosContext = createContext<(texto: string, tipo?: Tipo) => void>(() => {})

let proximoId = 1

export function ProvedorAvisos({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([])

  const avisar = useCallback((texto: string, tipo: Tipo = "ok") => {
    const id = proximoId++
    setAvisos((a) => [...a, { id, texto, tipo }])
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), 3500)
  }, [])

  return (
    <AvisosContext.Provider value={avisar}>
      {children}
      <div className="fixed right-6 bottom-6 z-[2000] flex flex-col gap-2" role="status" aria-live="polite">
        {avisos.map((a) => (
          <div
            key={a.id}
            className={cn(
              "rounded-lg border border-borda border-l-[3px] bg-superficie-2 px-4 py-2.5 text-sm shadow-lg",
              a.tipo === "ok" ? "border-l-livre" : "border-l-perigo",
            )}
          >
            {a.texto}
          </div>
        ))}
      </div>
    </AvisosContext.Provider>
  )
}

export function useAvisos() {
  return useContext(AvisosContext)
}
