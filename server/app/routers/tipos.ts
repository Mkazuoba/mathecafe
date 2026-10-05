export type StatusEstacao = "livre" | "ocupada" | "desligada" | "manutencao"

export interface Estacao {
  id: number
  nome: string
  grupo_id: number | null
  grupo_nome: string | null
  status: StatusEstacao
  online: boolean
  ip: string | null
  ultimo_ping: string | null
  pos_x: number
  pos_y: number
  mac_address: string | null
}

export interface Grupo {
  id: number
  nome: string
  tempo_padrao_segundos: number
}

export interface Cliente {
  id: number
  login: string
  nome: string
  ativo: boolean
  saldo_segundos: number
  observacao: string | null
  criado_em: string | null
  na_fila: boolean
  uso_hoje_segundos: number
}

export interface ItemFila {
  id: number
  cliente_id: number
  cliente_login: string
  cliente_nome: string
  saldo_segundos: number
  autorizado_em: string
  autorizado_por: string
}

export interface Sessao {
  id: number
  cliente_id: number
  cliente_login: string
  cliente_nome: string
  estacao_nome: string
  iniciada_em: string
  encerrada_em: string | null
  tempo_total_segundos: number
  tempo_consumido_segundos: number
  motivo_encerramento: string | null
  ativa: boolean
  pausada: boolean
}

export interface Operador {
  id: number
  login: string
  nome: string
  ativo: boolean
  criado_em: string | null
}

export interface AppPermitido {
  id: number
  nome: string
  processo: string
  caminho: string | null
  imagem_url: string | null
  grupo_id: number | null
  grupo_nome: string
  ativo: boolean
}

export interface ConfigSistema {
  reiniciar_ao_encerrar: boolean
  tempo_padrao_segundos: number
}
