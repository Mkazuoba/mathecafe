import { useState } from "react"
import { IconDownload, IconMessage, IconPlayerStop, IconPower, IconRefresh, IconWifi, IconX } from "@tabler/icons-react"
import { Api } from "@/lib/api"
import { useAvisos } from "@/lib/avisos"
import { useDados } from "@/lib/dados"
import { Button } from "@/components/ui/button"
import { Campo, MensagemErro, Textarea } from "@/components/ui/campos"
import { Modal } from "@/components/ui/modal"

type Acao = "mensagem" | "encerrar" | "reiniciar" | "desligar" | "ligar" | "atualizar"

const PERGUNTA: Partial<Record<Acao, string>> = {
  encerrar: "Encerrar as sessões de {n}? O tempo que sobrou volta para cada cliente.",
  reiniciar: "Reiniciar {n}? Quem estiver usando sai da sessão e o tempo que sobrou volta para o cliente.",
  desligar: "Desligar {n}? Quem estiver usando sai da sessão e o tempo que sobrou volta para o cliente.",
  atualizar:
    "Atualizar o agente de {n}? Só as estações sem cliente atualizam: o agente baixa a versão do servidor e volta na tela de login.",
}
const FEITO: Record<Acao, string> = {
  mensagem: "Mensagem enviada",
  encerrar: "Sessões encerradas",
  reiniciar: "Reiniciando",
  desligar: "Desligando",
  ligar: "Comando de ligar enviado",
  atualizar: "Atualizando o agente",
}

function nomesDe(n: number) {
  return n === 1 ? "1 estação" : `${n} estações`
}

/**
 * Barra que aparece no Controle de sessões com estações selecionadas: o mesmo
 * comando para todas de uma vez (POST /api/estacoes/acoes). Cada estação
 * responde à parte; as que falharem (offline, sem sessão) aparecem no aviso.
 */
export function AcoesEmMassa({ estacoes, aoLimpar }: { estacoes: string[]; aoLimpar: () => void }) {
  const avisar = useAvisos()
  const { recarregar, estacoes: doPiso } = useDados()
  const [enviando, setEnviando] = useState(false)
  const [escrevendo, setEscrevendo] = useState(false)
  const [texto, setTexto] = useState("")
  const [erro, setErro] = useState("")

  async function executar(acao: Acao, mensagem?: string) {
    const pergunta = PERGUNTA[acao]
    if (pergunta && !window.confirm(pergunta.replace("{n}", nomesDe(estacoes.length)))) return false
    setEnviando(true)
    try {
      const r = await Api.post<{ resultados: Record<string, string> }>("/api/estacoes/acoes", {
        acao,
        estacoes, // servidor antigo (até reiniciar): só os nomes
        // pelo id: o nome pode estar nos dois pisos (o painel mostra um por vez)
        ids: estacoes.map((n) => doPiso.find((e) => e.nome === n)?.id).filter((id) => id != null),
        texto: mensagem,
      })
      const falhas = Object.entries(r.resultados).filter(([, res]) => res !== "ok")
      const certas = estacoes.length - falhas.length
      if (!falhas.length) avisar(`${FEITO[acao]}: ${nomesDe(certas)}`)
      else
        avisar(
          `${FEITO[acao]}: ${nomesDe(certas)}. Não foi: ${falhas.map(([nome, motivo]) => `${nome} (${motivo})`).join(", ")}`,
          certas ? undefined : "erro",
        )
      await recarregar()
      return true
    } catch (e) {
      avisar((e as Error).message, "erro")
      return false
    } finally {
      setEnviando(false)
    }
  }

  async function enviarMensagem(ev: React.FormEvent) {
    ev.preventDefault()
    if (!texto.trim()) return setErro("Escreva a mensagem")
    if (await executar("mensagem", texto.trim())) {
      setEscrevendo(false)
      setTexto("")
    }
  }

  return (
    <div
      role="toolbar"
      aria-label="Ações para as estações selecionadas"
      className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-piso-borda bg-piso-fundo px-3 py-1.5"
    >
      <span className="mr-1 text-xs font-semibold">{nomesDe(estacoes.length)} selecionada(s)</span>
      <Button
        size="xs"
        variant="outline"
        disabled={enviando}
        onClick={() => {
          setErro("")
          setEscrevendo(true)
        }}
      >
        <IconMessage size={13} className="mr-1" /> Mensagem
      </Button>
      <Button size="xs" variant="outline" disabled={enviando} onClick={() => executar("encerrar")}>
        <IconPlayerStop size={13} className="mr-1" /> Encerrar sessões
      </Button>
      <Button size="xs" variant="outline" disabled={enviando} onClick={() => executar("ligar")}>
        <IconWifi size={13} className="mr-1" /> Ligar
      </Button>
      <Button size="xs" variant="outline" disabled={enviando} onClick={() => executar("reiniciar")}>
        <IconRefresh size={13} className="mr-1" /> Reiniciar
      </Button>
      <Button size="xs" variant="outline" disabled={enviando} onClick={() => executar("atualizar")}>
        <IconDownload size={13} className="mr-1" /> Atualizar agente
      </Button>
      <Button size="xs" variant="perigo" disabled={enviando} onClick={() => executar("desligar")}>
        <IconPower size={13} className="mr-1" /> Desligar
      </Button>
      <button
        type="button"
        onClick={aoLimpar}
        title="Limpar a seleção"
        aria-label="Limpar a seleção"
        className="ml-auto rounded p-1 text-texto-suave hover:text-texto"
      >
        <IconX size={15} />
      </button>

      <Modal
        titulo={`Mensagem para ${nomesDe(estacoes.length)}`}
        aberto={escrevendo}
        aoFechar={() => setEscrevendo(false)}
      >
        <form onSubmit={enviarMensagem} className="flex flex-col gap-3">
          <Campo rotulo="Aparece na tela dos computadores" id="msg-massa">
            <Textarea
              id="msg-massa"
              rows={3}
              autoFocus
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="ex.: A biblioteca fecha em 10 minutos"
            />
          </Campo>
          <MensagemErro>{erro}</MensagemErro>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => setEscrevendo(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={enviando}>
              {enviando ? "Enviando..." : "Enviar"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
