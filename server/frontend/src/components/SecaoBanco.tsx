import { useEffect, useState } from "react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Campo, Input } from "@/components/ui/campos"

interface BancoAtual {
  tipo: string
  destino: string
  no_ambiente: boolean
}

interface Teste {
  ok: boolean
  vazio: boolean | null
  mensagem: string
}

/** Configurações → Servidor: trocar o banco sem reinstalar (vale ao reiniciar o servidor). */
export function SecaoBanco() {
  const avisar = useAvisos()
  const [atual, setAtual] = useState<BancoAtual | null>(null)
  const [url, setUrl] = useState("")
  const [teste, setTeste] = useState<Teste | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [salvo, setSalvo] = useState(false)

  useEffect(() => {
    Api.get<BancoAtual>("/api/config/banco")
      .then(setAtual)
      .catch((e) => avisar((e as Error).message, "erro"))
  }, [avisar])

  async function testar() {
    setOcupado(true)
    try {
      setTeste(await Api.post<Teste>("/api/config/banco/testar", { url }))
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setOcupado(false)
    }
  }

  async function salvar(ev: React.FormEvent) {
    ev.preventDefault()
    if (teste?.vazio && !window.confirm("Esse banco está vazio: clientes, estações e operadores não vão aparecer. Usar mesmo assim?")) return
    setOcupado(true)
    try {
      setTeste(await Api.put<Teste>("/api/config/banco", { url }))
      setSalvo(true)
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setOcupado(false)
    }
  }

  return (
    <form onSubmit={salvar}>
      <h2 className="mb-2 text-lg font-semibold">Servidor</h2>
      <p className="mb-5 text-sm text-texto-suave">
        Banco de dados que o servidor usa. O endereço do servidor em cada estação se troca no próprio PC: modo
        manutenção → Configurar conexão.
      </p>

      <div className="mb-5 rounded-lg border border-borda bg-superficie-2 px-4 py-3.5 text-sm">
        <div className="mb-0.5 font-semibold">Banco em uso</div>
        {atual ? (
          <span className="text-texto-suave">
            {atual.tipo} · <span className="font-mono">{atual.destino}</span>
          </span>
        ) : (
          <span className="text-texto-fraco">Carregando...</span>
        )}
      </div>

      {atual?.no_ambiente ? (
        <p className="text-sm text-texto-suave">
          Este servidor lê o banco da variável de ambiente <span className="font-mono">DATABASE_URL</span> (no Render:
          Environment). Para trocar, mude lá e reinicie o serviço.
        </p>
      ) : (
        <>
          <Campo rotulo="Novo banco (URL)" id="banco-url">
            <Input
              id="banco-url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value)
                setTeste(null)
                setSalvo(false)
              }}
              placeholder="postgresql://usuario:senha@servidor:5432/postgres"
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
            />
          </Campo>
          <p className="mt-1.5 mb-4 text-xs text-texto-fraco">
            PostgreSQL (Supabase: Project Settings → Database → Connection string) ou SQLite
            (sqlite:///./cybercafe.db). A senha não aparece de novo depois de salva.
          </p>

          {teste && (
            <p role="status" className={cn("mb-4 text-sm", teste.ok ? "text-livre" : "text-perigo")}>
              {teste.mensagem}
            </p>
          )}
          {salvo && (
            <p className="mb-4 rounded-lg border border-borda bg-superficie-2 px-4 py-3 text-sm">
              Salvo no <span className="font-mono">server/.env</span>. Reinicie o servidor para passar a usar o banco
              novo; até lá ele continua no atual.
            </p>
          )}

          <div className="flex gap-2">
            <Button type="button" variant="outline" disabled={!url.trim() || ocupado} onClick={testar}>
              {ocupado ? "..." : "Testar conexão"}
            </Button>
            <Button type="submit" disabled={!teste?.ok || ocupado || salvo}>
              Salvar
            </Button>
          </div>
        </>
      )}
    </form>
  )
}
