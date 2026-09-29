export const Api = {
  token(): string | null {
    return localStorage.getItem("token")
  },

  perfil(): string | null {
    return localStorage.getItem("perfil")
  },

  nome(): string | null {
    return localStorage.getItem("nome")
  },

  ehAdmin(): boolean {
    return this.perfil() === "admin"
  },

  entrar(token: string, perfil: string, nome: string) {
    localStorage.setItem("token", token)
    localStorage.setItem("perfil", perfil)
    localStorage.setItem("nome", nome)
  },

  sair() {
    localStorage.removeItem("token")
    localStorage.removeItem("perfil")
    localStorage.removeItem("nome")
    window.location.href = "/login"
  },

  async chamar<T = unknown>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(opcoes.headers as Record<string, string>),
    }
    const token = this.token()
    if (token) headers["Authorization"] = `Bearer ${token}`

    const resp = await fetch(caminho, { ...opcoes, headers })

    if (resp.status === 401 && token) {
      this.sair()
      throw new Error("Sessão expirada, faça login novamente")
    }

    if (!resp.ok) {
      let detalhe = "Erro inesperado"
      try {
        const corpo = await resp.json()
        detalhe = typeof corpo.detail === "string" ? corpo.detail : JSON.stringify(corpo.detail)
      } catch {
        /* resposta sem JSON */
      }
      throw new Error(detalhe)
    }

    return resp.json()
  },

  get<T = unknown>(caminho: string) {
    return this.chamar<T>(caminho)
  },

  post<T = unknown>(caminho: string, dados?: unknown) {
    return this.chamar<T>(caminho, {
      method: "POST",
      body: dados === undefined ? undefined : JSON.stringify(dados),
    })
  },

  put<T = unknown>(caminho: string, dados: unknown) {
    return this.chamar<T>(caminho, { method: "PUT", body: JSON.stringify(dados) })
  },

  del<T = unknown>(caminho: string) {
    return this.chamar<T>(caminho, { method: "DELETE" })
  },

  /** Baixa um arquivo de uma rota autenticada (ex.: relatório CSV). */
  async baixar(caminho: string, nomeArquivo: string) {
    const resp = await fetch(caminho, { headers: { Authorization: `Bearer ${this.token()}` } })
    if (!resp.ok) throw new Error("Erro ao gerar o arquivo")
    const url = URL.createObjectURL(await resp.blob())
    const a = document.createElement("a")
    a.href = url
    a.download = nomeArquivo
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}
