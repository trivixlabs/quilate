const MINUS = "−"; // U+2212

const fmt = (min: number, max: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: min, maximumFractionDigits: max });

const INT = fmt(0, 0), CENTS = fmt(2, 2), FOUR = fmt(4, 4);

/** Preço em dólar, com casas por magnitude: >=100 inteiro, >=1 centavos, >=0,01 quatro casas, abaixo disso 7. Zero tem centavos. */
export function usd(v: number): string {
  const a = Math.abs(v);
  const s = a >= 100 ? INT.format(a) : a >= 1 || a === 0 ? CENTS.format(a) : a >= 0.01 ? FOUR.format(a) : fmt(7, 7).format(a);
  return `${v < 0 ? MINUS : ""}US$ ${s}`;
}

/** Percentual com sinal explícito. Recebe pontos percentuais (2 = 2%). */
export function pct(v: number): string {
  return `${v < 0 ? MINUS : "+"}${CENTS.format(Math.abs(v))}%`;
}

const EXCHANGES: Record<string, string> = { binance: "Binance", mexc: "MEXC", bybit: "Bybit", gate: "Gate" };
/** Nome de exibição da corretora ("mexc" vira "MEXC"). */
export const exchangeName = (e: string) => EXCHANGES[e] ?? e;

/** Resultado com sinal explícito: "+US$ 13.797", "−US$ 5.208". */
export const signedUsd = (v: number) => `${v >= 0 ? "+" : ""}${usd(v)}`;

const QTY = fmt(0, 8);
/** Quantidade de moeda, até 8 casas: "1.260", "0,42". */
export const qty = (v: number) => QTY.format(v);

const DAY = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" });
/** Dia AAAA-MM-DD da API em "04/11/2026". */
export const day = (iso: string) => DAY.format(new Date(`${iso}T00:00:00Z`));
