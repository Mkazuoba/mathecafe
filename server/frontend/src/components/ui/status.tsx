import type { StatusEstacao } from "@/lib/tipos"
import { cn } from "@/lib/utils"

export const ROTULO_STATUS: Record<StatusEstacao, string> = {
  livre: "livre",
  ocupada: "ocupada",
  desligada: "desligada",
  manutencao: "manutenção",
}

const CORES: Record<StatusEstacao, string> = {
  livre: "border-livre-borda bg-livre-fundo text-livre",
  ocupada: "border-ocupada-borda bg-ocupada-fundo text-ocupada",
  desligada: "border-desligada-borda bg-desligada-fundo text-desligada",
  manutencao: "border-manutencao-borda bg-manutencao-fundo text-manutencao",
}

export function SeloStatus({ status }: { status: StatusEstacao }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize", CORES[status])}>
      <span className="size-1.5 rounded-full bg-current" />
      {ROTULO_STATUS[status]}
    </span>
  )
}

export function SeloAtivo({ ativo }: { ativo: boolean }) {
  return (
    <span
      className={cn(
        "rounded-full border px-2 py-0.5 text-[0.7rem] font-semibold uppercase",
        ativo ? "border-livre-borda bg-livre-fundo text-livre" : "border-desligada-borda bg-desligada-fundo text-desligada",
      )}
    >
      {ativo ? "Ativo" : "Inativo"}
    </span>
  )
}

/** Cor da borda por status (cards do Painel e pinos do Mapa). */
export const COR_BORDA_STATUS: Record<StatusEstacao, string> = {
  livre: "border-l-livre",
  ocupada: "border-l-ocupada",
  desligada: "border-l-desligada opacity-60",
  manutencao: "border-l-manutencao opacity-85",
}

export function Vazio({ children }: { children: React.ReactNode }) {
  return <div className="px-4 py-8 text-center text-sm text-texto-fraco">{children}</div>
}
