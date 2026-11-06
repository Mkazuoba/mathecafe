export type StatusEstacao = "livre" | "ocupada" | "desligada" | "manutencao"

/** Piso da biblioteca, cadastrado em Configurações → Pisos (app/pisos.py). */
export interface Piso {
  id: number
  nome: string
  /** #rrggbb: seletor, abas e colunas do painel ficam nesta cor */
  cor: string
  /** Vale para estação sem grupo, mapa antigo sem piso e cliente sem piso */
  padrao: boolean
  grupos: number
  clientes: number
}

/** Piso que vem junto de clientes, estações e grupos. */
export interface PisoDe {
  piso_id: number | null
  piso_nome: string | null
  piso_cor: string | null
}

export interface Estacao extends PisoDe {
  id: number
  nome: string
  grupo_id: number | null
  grupo_nome: string | null
  grupo_cor: string | null
  // piso: o do grupo; sem grupo ou mapa sem piso = o piso padrão
  status: StatusEstacao
  online: boolean
  ip: string | null
  ultimo_ping: string | null
  pos_x: number
  pos_y: number
  mac_address: string | null
}

/** Mapa (sala). piso_id vazio: mapa antigo ainda sem piso, o painel avisa. */
export interface Grupo extends PisoDe {
  id: number
  nome: string
  tempo_padrao_segundos: number
  cor: string
}

export interface Cliente extends PisoDe {
  id: number
  login: string
  nome: string
  ativo: boolean
  saldo_segundos: number
  observacao: string | null
  documento: string | null
  email: string | null
  /** AAAA-MM-DD */
  data_nascimento: string | null
  /** Quem trocou o piso por último e quando (null se nunca trocou). */
  piso_alterado_por: string | null
  piso_alterado_em: string | null
  tem_foto: boolean
  /** Quando a foto mudou (vai na URL da foto para o navegador não usar a antiga). */
  foto_em: string | null
  criado_em: string | null
  na_fila: boolean
  uso_hoje_segundos: number
}

export interface ItemFila {
  id: number
  cliente_id: number
  cliente_login: string
  cliente_nome: string
  cliente_piso_id: number
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
  /** Início da pausa em andamento (null fora da pausa). */
  pausada_em: string | null
}

export interface Operador {
  id: number
  login: string
  nome: string
  ativo: boolean
  perfil: string
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
