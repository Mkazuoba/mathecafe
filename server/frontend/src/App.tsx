import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Api } from "@/lib/api"
import { ProvedorAvisos } from "@/lib/avisos"
import { ProvedorDados } from "@/lib/dados"
import { Layout } from "@/components/Layout"
import Login from "@/pages/Login"
import Painel from "@/pages/Painel"
import Clientes from "@/pages/Clientes"
import Mapa from "@/pages/Mapa"
import Configuracoes from "@/pages/Configuracoes"

function AreaLogada() {
  if (!Api.token()) return <Navigate to="/login" replace />
  return (
    <ProvedorDados>
      <Layout />
    </ProvedorDados>
  )
}

export default function App() {
  return (
    <ProvedorAvisos>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AreaLogada />}>
            <Route path="/" element={<Painel />} />
            <Route path="/clientes" element={<Clientes />} />
            <Route path="/mapa" element={<Mapa />} />
            <Route path="/configuracoes" element={<Configuracoes />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ProvedorAvisos>
  )
}
