import { useState } from "react"

export type Tema = "escuro" | "claro"

/** Tema escolhido neste navegador (o storage pode estar bloqueado). */
export function lerTema(): Tema {
  try {
    return localStorage.getItem("tema") === "claro" ? "claro" : "escuro"
  } catch {
    return "escuro"
  }
}

/** As cores do tema claro estão em index.css, em :root[data-tema="claro"]. */
export function aplicarTema(tema: Tema) {
  document.documentElement.dataset.tema = tema
}

export function useTema() {
  const [tema, setTema] = useState<Tema>(lerTema)
  function alternar() {
    const novo: Tema = tema === "claro" ? "escuro" : "claro"
    aplicarTema(novo)
    setTema(novo)
    try {
      localStorage.setItem("tema", novo)
    } catch {
      /* sem storage: vale até recarregar */
    }
  }
  return { tema, alternar }
}
