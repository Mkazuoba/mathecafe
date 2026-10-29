import { useEffect, useState } from "react"
import { Api } from "@/lib/api"
import { useDados } from "@/lib/dados"
import type { Cliente } from "@/lib/tipos"

/** Filtros de GET /api/clientes/ — os mesmos no Painel e na aba Clientes. */
export interface FiltrosClientes {
  campo: "tudo" | "nome" | "login"
  modo: "contem" | "comeca" | "exato"
  status: "todos" | "ativos" | "inativos"
  saldo: "todos" | "com" | "sem"
  ordem: "nome" | "login" | "saldo" | "criado"
  desc: boolean
}

export const FILTROS_PADRAO: FiltrosClientes = {
  campo: "tudo",
  modo: "contem",
  status: "todos",
  saldo: "todos",
  ordem: "nome",
  desc: false,
}

/** Filtros guardados no navegador (o storage pode estar bloqueado). */
export function lerFiltros(chave: string, padrao: FiltrosClientes): FiltrosClientes {
  try {
    const salvo = JSON.parse(localStorage.getItem(chave) ?? "null")
    if (salvo && typeof salvo === "object") return { ...padrao, ...salvo }
  } catch {
    /* padrão */
  }
  return padrao
}

export function gravarFiltros(chave: string, filtros: FiltrosClientes) {
  try {
    localStorage.setItem(chave, JSON.stringify(filtros))
  } catch {
    /* sem storage: vale só até recarregar */
  }
}

/** Quantos filtros diferem do padrão (para o selo no botão de filtros). */
export function filtrosAtivos(f: FiltrosClientes, padrao: FiltrosClientes, campos: (keyof FiltrosClientes)[]): number {
  return campos.filter((k) => f[k] !== padrao[k]).length
}

/**
 * Busca no servidor (são ~43k clientes), com 300ms de espera enquanto digita.
 * Sem termo devolve vazio, a não ser com `tudo` (lista pela ordem escolhida).
 * Refaz a consulta quando alguém chama recarregarClientes.
 */
export function useBuscaClientes(
  busca: string,
  filtros: Partial<FiltrosClientes> = {},
  { tudo = false, limite = 50 }: { tudo?: boolean; limite?: number } = {},
) {
  const { versaoClientes } = useDados()
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [carregando, setCarregando] = useState(false)
  const chaveFiltros = JSON.stringify(filtros)

  useEffect(() => {
    const q = busca.trim()
    if (!q && !tudo) {
      setClientes([])
      return
    }
    let cancelado = false
    const params = new URLSearchParams({ busca: q, limite: String(limite) })
    for (const [k, v] of Object.entries(JSON.parse(chaveFiltros) as Partial<FiltrosClientes>)) params.set(k, String(v))
    if (tudo) params.set("tudo", "true")
    const timer = setTimeout(async () => {
      setCarregando(true)
      try {
        const res = await Api.get<Cliente[]>(`/api/clientes/?${params}`)
        if (!cancelado) setClientes(res)
      } catch {
        if (!cancelado) setClientes([])
      } finally {
        if (!cancelado) setCarregando(false)
      }
    }, 300)
    return () => {
      cancelado = true
      clearTimeout(timer)
    }
  }, [busca, chaveFiltros, tudo, limite, versaoClientes])

  return { clientes, carregando }
}
