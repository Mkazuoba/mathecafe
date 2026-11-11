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
  /** versão que o agente informou ao conectar (null: nunca conectou ou agente antigo) */
  versao_agente: string | null
  /** versão que o servidor distribui */
  versao_atual: string
  /** o agente só se atualiza no modo manutenção: o painel avisa onde fazer */
  agente_desatualizado: boolean
  /** UUID da instalação (agente 1.14); null: cadastrada no painel e agente antigo */
  identificador?: string | null
  /** false: PC novo esperando em "Novas estações" (ninguém faz login até aprovar) */
  aprovada?: boolean
  /** nome trocado no próprio PC, esperando o admin aceitar (Novas estações) */
  nome_pedido?: string | null
}

/** Mapa (sala). piso_id vazio: mapa antigo ainda sem piso, o painel avisa. */
export interface Grupo extends PisoDe {
  id: number
  nome: string
  tempo_padrao_segundos: number
  cor: string
  /** Posição e tamanho da zona no Mapa (px); null = o Mapa arruma sozinho */
  zona: { x: number; y: number; largura: number; altura: number } | null
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
  estacao_id: number
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
  /** frase curta no card do agente (vazia: o nome da categoria) */
  descricao?: string | null
  grupo_id: number | null
  grupo_nome: string
  ativo: boolean
  /** pisos em que o app está ligado (aparece no menu das estações do piso) */
  pisos: number[]
  /** categoria (filtro da tela de apps do agente); vazio = "Outros" */
  categoria_id?: number | null
  categoria_nome?: string | null
}

export interface CategoriaApp {
  id: number
  nome: string
  ordem: number
  /** #rrggbb: selo, fundo da logo e brilho dos apps dela no agente */
  cor: string
  /** quantos apps estão nela */
  apps: number
}

export interface ConfigSistema {
  reiniciar_ao_encerrar: boolean
  tempo_padrao_segundos: number
}
