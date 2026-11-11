import { useCallback, useEffect, useState } from "react"
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
    if (
      teste?.vazio &&
      !window.confirm("Esse banco está vazio: clientes, estações e operadores não vão aparecer. Usar mesmo assim?")
    )
      return
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
    <div>
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
      <SecaoReiniciar />
      <SecaoBackup />
    </div>
  )
}

interface Backup {
  nome: string
  bytes: number
  feito_em: string
}

interface InfoBackup {
  ativo: boolean
  pasta: string
  dias: number
  backups: Backup[]
  /** o banco de antes de cada restauração (para desfazer) e os enviados */
  outros?: Backup[]
  sessoes_abertas?: number
}

/** "cybercafe-2026-11-11-0001.db" -> "11/11/2026 00:01" (o momento do backup) */
function quando(nome: string) {
  const m = nome.match(/(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})/)
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}` : nome
}

function rotuloOutro(nome: string) {
  return nome.startsWith("antes-da-restauracao")
    ? `Banco de antes da restauração de ${quando(nome)}`
    : `Enviado em ${quando(nome)}`
}

/** Espera o servidor voltar depois de reiniciar (no_ar_desde muda). */
async function esperarServidor(antes: string | null) {
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 1000))
    try {
      const novo = await Api.get<{ no_ar_desde: string }>("/api/config/servidor")
      if (novo.no_ar_desde !== antes) return true
    } catch {
      /* ainda subindo */
    }
  }
  return false
}

function tamanho(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
}

/** Backup diário do SQLite: lista, "fazer agora" e baixar uma cópia. */
interface InfoServidor {
  pode_reiniciar: boolean
  no_ar_desde: string
}

/**
 * Reiniciar o servidor sem PowerShell de administrador: o servidor termina e o
 * iniciar_servidor.bat (tarefa MatheCafe-Servidor) o sobe de novo em segundos.
 * Os PCs com agente 1.8+ seguem a sessão e reconectam sozinhos.
 */
function SecaoReiniciar() {
  const avisar = useAvisos()
  const [info, setInfo] = useState<InfoServidor | null>(null)
  const [estado, setEstado] = useState<"parado" | "reiniciando">("parado")

  const carregar = useCallback(
    () =>
      Api.get<InfoServidor>("/api/config/servidor")
        .then(setInfo)
        .catch(() => setInfo(null)),
    [],
  )
  useEffect(() => {
    carregar()
  }, [carregar])

  async function reiniciar() {
    if (!info) return
    if (
      !window.confirm(
        "Reiniciar o servidor agora?\n\nO painel e os computadores ficam sem conexão por alguns segundos. " +
          "Quem estiver usando continua a sessão normalmente.",
      )
    )
      return
    const antes = info.no_ar_desde
    setEstado("reiniciando")
    try {
      await Api.post("/api/config/reiniciar")
    } catch (e) {
      setEstado("parado")
      avisar((e as Error).message, "erro")
      return
    }
    // espera o servidor voltar (no_ar_desde muda quando ele sobe de novo)
    for (let i = 0; i < 60; i++) {
      await new Promise((r) => setTimeout(r, 1000))
      try {
        const novo = await Api.get<InfoServidor>("/api/config/servidor")
        if (novo.no_ar_desde !== antes) {
          setInfo(novo)
          setEstado("parado")
          avisar("Servidor reiniciado")
          return
        }
      } catch {
        /* ainda subindo */
      }
    }
    setEstado("parado")
    avisar("O servidor não voltou em 1 minuto. Veja server\\logs\\servidor.log no computador do servidor.", "erro")
  }

  if (!info) return null
  return (
    <div className="mt-10">
      <h3 className="mb-2 font-semibold">Reiniciar o servidor</h3>
      <p className="mb-4 text-sm text-texto-suave">
        Para aplicar uma atualização do sistema (depois do git pull) ou se algo travar. O servidor fica alguns segundos
        fora do ar e volta sozinho; quem estiver usando os computadores continua a sessão. No ar desde{" "}
        {new Date(info.no_ar_desde).toLocaleString("pt-BR")}.
      </p>
      {info.pode_reiniciar ? (
        <Button type="button" variant="outline" disabled={estado === "reiniciando"} onClick={reiniciar}>
          {estado === "reiniciando" ? "Reiniciando..." : "Reiniciar servidor"}
        </Button>
      ) : (
        <p className="text-sm text-texto-fraco">
          Este servidor foi aberto à mão (sem o iniciar_servidor.bat da tarefa MatheCafe-Servidor): reinicie no terminal
          onde ele está rodando.
        </p>
      )}
    </div>
  )
}

function SecaoBackup() {
  const avisar = useAvisos()
  const [info, setInfo] = useState<InfoBackup | null>(null)
  const [fazendo, setFazendo] = useState(false)
  const [restaurando, setRestaurando] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const carregar = useCallback(() => {
    Api.get<InfoBackup>("/api/config/backup")
      .then(setInfo)
      .catch((e) => avisar((e as Error).message, "erro"))
  }, [avisar])

  useEffect(carregar, [carregar])

  async function fazerAgora() {
    setFazendo(true)
    try {
      await Api.post("/api/config/backup")
      avisar("Backup feito")
      carregar()
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setFazendo(false)
    }
  }

  /**
   * Restaurar (10.2): o servidor confere o arquivo, reinicia e, ao subir, guarda o
   * banco atual e põe o backup no lugar. Tudo depois do backup some.
   */
  async function restaurar(nome: string, rotulo: string) {
    if (!info) return
    const abertas = info.sessoes_abertas ?? 0
    const ok = window.confirm(
      `Restaurar ${rotulo}?\n\n` +
        "O sistema volta a como estava nesse momento: o que foi feito depois (clientes, tempos, sessões, " +
        "configurações) deixa de aparecer. O banco de agora fica guardado na lista, para desfazer.\n\n" +
        (abertas
          ? `ATENÇÃO: ${abertas} computador(es) em uso agora. As sessões voltam ao estado do backup e podem ser encerradas.\n\n`
          : "") +
        "O servidor reinicia: o painel e os computadores ficam sem conexão por alguns segundos.",
    )
    if (!ok) return
    setRestaurando(nome)
    try {
      const antes = await Api.get<{ no_ar_desde: string }>("/api/config/servidor")
        .then((r) => r.no_ar_desde)
        .catch(() => null)
      const r = await Api.post<{ reiniciando: boolean }>(`/api/config/backup/${encodeURIComponent(nome)}/restaurar`, {
        confirmar: true,
      })
      if (!r.reiniciando) {
        avisar("Restauração agendada: vale quando o servidor for iniciado de novo (ele foi aberto à mão)")
        return
      }
      if (await esperarServidor(antes)) {
        avisar("Backup restaurado")
        // tudo mudou: recarrega o painel com os dados do backup
        setTimeout(() => window.location.reload(), 800)
      } else {
        avisar("O servidor não voltou em 1 minuto. Veja server\\logs\\servidor.log no computador do servidor.", "erro")
      }
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setRestaurando(null)
    }
  }

  /** Um banco trazido de fora (a cópia guardada em outro lugar): sobe, confere e restaura. */
  async function enviarArquivo(arquivo: File) {
    setEnviando(true)
    try {
      const corpo = new FormData()
      corpo.append("arquivo", arquivo)
      const resp = await fetch("/api/config/backup/enviar", {
        method: "POST",
        headers: { Authorization: `Bearer ${Api.token()}` },
        body: corpo,
      })
      const dados = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(typeof dados.detail === "string" ? dados.detail : "Não foi possível enviar o arquivo")
      carregar()
      const c = dados.conferido as { clientes: number; estacoes: number; sessoes: number }
      await restaurar(
        dados.nome,
        `o arquivo ${arquivo.name} (${c.clientes.toLocaleString("pt-BR")} clientes, ${c.estacoes} estações, ` +
          `${c.sessoes.toLocaleString("pt-BR")} sessões)`,
      )
    } catch (e) {
      avisar((e as Error).message, "erro")
    } finally {
      setEnviando(false)
    }
  }

  async function baixar(nome: string) {
    try {
      await Api.baixar(`/api/config/backup/${nome}`, nome)
    } catch (e) {
      avisar((e as Error).message, "erro")
    }
  }

  return (
    <div className="mt-10">
      <h3 className="mb-2 font-semibold">Backup do banco</h3>
      {!info ? (
        <p className="text-sm text-texto-fraco">Carregando...</p>
      ) : !info.ativo ? (
        <p className="text-sm text-texto-suave">
          O backup automático é só para o SQLite. No PostgreSQL (Supabase), use o backup do próprio provedor.
        </p>
      ) : (
        <>
          <p className="mb-4 text-sm text-texto-suave">
            Feito sozinho todo dia logo depois da meia-noite (ou quando o servidor sobe, se o do dia ainda não foi
            feito). Guarda os últimos {info.dias} dias em <span className="font-mono break-all">{info.pasta}</span>.
            Baixe uma cópia de vez em quando para outro lugar: se o disco do servidor falhar, a pasta vai junto.
          </p>
          <div className="mb-4 flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={fazendo} onClick={fazerAgora}>
              {fazendo ? "Fazendo..." : "Fazer backup agora"}
            </Button>
            {/* um backup guardado fora do servidor (pendrive, outro PC) */}
            <label
              className={cn(
                "inline-flex h-10 cursor-pointer items-center rounded-lg border border-borda bg-superficie-3 px-4 text-sm font-semibold text-texto-suave hover:border-borda-forte hover:text-texto",
                (enviando || restaurando) && "pointer-events-none opacity-50",
              )}
            >
              {enviando ? "Enviando..." : "Restaurar de um arquivo..."}
              <input
                type="file"
                accept=".db"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ""
                  if (f) enviarArquivo(f)
                }}
              />
            </label>
          </div>
          {restaurando && (
            <p className="mb-4 rounded-lg border border-manutencao-borda bg-manutencao-fundo px-3 py-2 text-sm text-manutencao">
              Restaurando... o servidor está reiniciando; o painel recarrega sozinho quando ele voltar.
            </p>
          )}
          {!info.backups.length ? (
            <p className="text-sm text-texto-fraco">Nenhum backup ainda.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {info.backups.map((b) => (
                <li
                  key={b.nome}
                  className="flex items-center gap-3 rounded-lg border border-borda bg-superficie-2 px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate font-mono">{b.nome}</span>
                  <span className="text-texto-fraco">{tamanho(b.bytes)}</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => baixar(b.nome)}>
                    Baixar
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!!restaurando || enviando}
                    onClick={() => restaurar(b.nome, `o backup de ${quando(b.nome)}`)}
                  >
                    Restaurar
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {!!info.outros?.length && (
            <>
              <h4 className="mt-6 mb-2 text-sm font-semibold">Para desfazer uma restauração</h4>
              <p className="mb-2 text-xs text-texto-fraco">
                O banco como estava antes de cada restauração, e os arquivos enviados. Não são apagados sozinhos.
              </p>
              <ul className="flex flex-col gap-1.5">
                {info.outros.map((b) => (
                  <li
                    key={b.nome}
                    className="flex items-center gap-3 rounded-lg border border-borda bg-superficie-2 px-3 py-2 text-sm"
                  >
                    <span className="min-w-0 flex-1 truncate">{rotuloOutro(b.nome)}</span>
                    <span className="text-texto-fraco">{tamanho(b.bytes)}</span>
                    <Button type="button" variant="ghost" size="sm" onClick={() => baixar(b.nome)}>
                      Baixar
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!!restaurando || enviando}
                      onClick={() => restaurar(b.nome, rotuloOutro(b.nome).toLowerCase())}
                    >
                      Restaurar
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
