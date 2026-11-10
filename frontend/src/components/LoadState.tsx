/** "Carregando…" antes da primeira resposta, ou a mensagem de erro dela. */
export function LoadState({ what, error }: { what: string; error: string | null }) {
  return error
    ? <p role="alert" className="m-0 text-sair">Não consegui carregar {what} ({error}).</p>
    : <p className="m-0 text-texto-2">Carregando…</p>;
}

/** Aviso de falha depois de um acerto: a tela segue com a última consulta. */
export function StaleError({ error }: { error: string | null }) {
  return error && <p role="alert" className="m-0 text-sm text-sair">Falha ao atualizar ({error}). Mostrando a última consulta.</p>;
}
