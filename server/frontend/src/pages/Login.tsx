import { useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { Api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Campo, Input, MensagemErro } from "@/components/ui/campos"

interface RespostaLogin {
  access_token: string
  perfil: string
  nome: string
}

export default function Login() {
  const navigate = useNavigate()
  const [login, setLogin] = useState("")
  const [senha, setSenha] = useState("")
  const [erro, setErro] = useState("")
  const [enviando, setEnviando] = useState(false)

  if (Api.token()) return <Navigate to="/" replace />

  async function entrar(ev: React.FormEvent) {
    ev.preventDefault()
    setErro("")
    if (!login.trim() || !senha) {
      setErro("Preencha login e senha")
      return
    }
    setEnviando(true)
    try {
      const r = await Api.post<RespostaLogin>("/api/auth/login", { login: login.trim(), senha })
      Api.entrar(r.access_token, r.perfil, r.nome)
      navigate("/", { replace: true })
    } catch (e) {
      setErro(e instanceof Error && e.message !== "Failed to fetch" ? e.message : "Servidor indisponível")
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-fundo p-4">
      <form onSubmit={entrar} className="w-full max-w-[340px] rounded-xl border border-borda bg-superficie p-10">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-widest text-destaque">MatheCafé</h1>
          <p className="mt-1 text-sm text-texto-suave">Sistema de gerenciamento</p>
        </div>
        <div className="flex flex-col gap-4">
          <Campo rotulo="Login" id="login">
            <Input id="login" autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} autoFocus />
          </Campo>
          <Campo rotulo="Senha" id="senha">
            <Input
              id="senha"
              type="password"
              autoComplete="current-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
          </Campo>
          <Button type="submit" className="mt-2 w-full" disabled={enviando}>
            {enviando ? "Entrando..." : "Entrar"}
          </Button>
          <MensagemErro>{erro}</MensagemErro>
        </div>
      </form>
    </div>
  )
}
