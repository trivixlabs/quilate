/** Como as telas chamam o analista: o nome de exibição do config ou, sem ele, o termo genérico. */
const clean = (name?: string) => name?.trim() ?? "";

/** Início de frase: "O analista" ou o nome. */
export const subject = (name?: string) => clean(name) || "O analista";
/** Meio de frase: "o analista" ou o nome. */
export const mention = (name?: string) => clean(name) || "o analista";
/** Posse: "do analista" ou "de " + nome. */
export const of = (name?: string) => (clean(name) ? `de ${clean(name)}` : "do analista");
