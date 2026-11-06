import { useEffect, useState } from "react"
import { Api } from "@/lib/api"

/**
 * Fotos dos clientes. A rota exige o token (uma <img src> não manda o login),
 * então cada foto é baixada uma vez e vira um object URL guardado aqui:
 * a lista do Painel e a ficha usam a mesma. A chave leva foto_em, que muda
 * quando a foto muda.
 */
const cache = new Map<string, Promise<string | null>>()

function baixar(id: number, fotoEm: string | null): Promise<string | null> {
  const chave = `${id}:${fotoEm ?? ""}`
  let foto = cache.get(chave)
  if (!foto) {
    foto = fetch(`/api/clientes/${id}/foto?v=${encodeURIComponent(fotoEm ?? "")}`, {
      headers: { Authorization: `Bearer ${Api.token()}` },
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => (b ? URL.createObjectURL(b) : null))
      .catch(() => null)
    cache.set(chave, foto)
    // falhou: tenta de novo da próxima vez
    foto.then((url) => url || cache.delete(chave))
  }
  return foto
}

/** URL da foto do cliente (null sem foto ou enquanto carrega). */
export function useFotoDoCliente(cliente: { id: number; tem_foto: boolean; foto_em: string | null }): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    setUrl(null)
    if (!cliente.tem_foto) return
    let cancelado = false
    baixar(cliente.id, cliente.foto_em).then((u) => !cancelado && setUrl(u))
    return () => {
      cancelado = true
    }
  }, [cliente.id, cliente.tem_foto, cliente.foto_em])
  return url
}
