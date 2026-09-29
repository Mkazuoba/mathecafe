/** Saldo e contagem regressiva: sempre HH:MM:SS em todo o painel. */
export function formatarTempo(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const seg = s % 60
  return [h, m, seg].map((n) => String(n).padStart(2, "0")).join(":")
}

/** Aceita HH:MM ou HH:MM:SS. Devolve null se o texto não estiver nesse formato. */
export function lerTempo(texto: string): number | null {
  const partes = texto.trim().split(":")
  if (partes.length < 2 || partes.length > 3) return null
  if (partes.some((p) => !/^\d+$/.test(p))) return null
  const [h, m, s = 0] = partes.map(Number)
  if (m > 59 || s > 59) return null
  return h * 3600 + m * 60 + s
}

/** As datas do servidor vêm em UTC sem o "Z". */
export function dataDoServidor(iso: string): Date {
  return new Date(iso.endsWith("Z") ? iso : iso + "Z")
}

export function restanteDaSessao(iniciadaEm: string, totalSegundos: number, agora: number): number {
  const decorrido = (agora - dataDoServidor(iniciadaEm).getTime()) / 1000
  return Math.max(0, totalSegundos - decorrido)
}

export function haQuantoTempo(iso: string, agora: number): string {
  const diff = (agora - dataDoServidor(iso).getTime()) / 1000
  if (diff < 60) return `${Math.max(0, Math.floor(diff))}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}min`
  return `${Math.floor(diff / 3600)}h`
}
