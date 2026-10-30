import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import App from "./App.tsx"
import { aplicarTema, lerTema } from "./lib/tema"

// antes de desenhar, para a tela não piscar no tema errado
aplicarTema(lerTema())

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
