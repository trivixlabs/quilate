/**
 * Dados fictícios dos testes e do modo de demonstração (`?demo=1` no `npm run dev`).
 * Nenhum número aqui é da carteira real.
 */
import type {
  Card, CoinDetail, HitRate, KeyCheck, Market, Overview, Playbook, Portfolio, Quote, SecretName, Setup, SetupConfig, Signal, Track,
  Verdict, Verdicts,
} from "@/lib/types";
import type { Tick } from "@/lib/live";

/** A carteira (`/api/portfolio`) sai dos cartões, mais a poeira de `DUST`. */
export type Seed = { overview: Overview; verdicts: Verdicts; playbook: Playbook; market: Market; track: Track };

const NAMES = ["Força contra o BTC", "Tendência de queda", "Liquidez", "Oferta nova", "Risco de deslistagem", "Analista", "Atenção do grupo"];
const signals = (flags: (0 | 1 | null)[], vals: string[]): Signal[] =>
  flags.map((f, i) => ({ code: `S${i + 1}`, name: NAMES[i], alert: f === null ? null : f === 1, value: f === null ? "sem dado" : vals[i] }));

/** O que só o foco da moeda mostra: valor medido de cada sinal, falas do analista e argumentos da IA. */
type Detail = { vals: string[]; quotes: Omit<Quote, "id">[]; pros: string[]; cons: string[]; risk: string | null };
const q = (text: string, date_utc: string, topic: string | null, kind: string, t_start: number | null = null) =>
  ({ text, date_utc, topic, kind, t_start });

const DETAIL: Record<string, Detail> = {
  ARB: { vals: ["−34% em 90 d", "−75% da máxima", "volume 0,46×", "4,10% em 90 d", "em 2 corretora(s)", "mandou sair", "menções 0,8× a média"],
    quotes: [q("Endereços ativos na rede caíram de 600 mil para 210 mil por dia. Sem uso, sai no rebalanceamento.", "2026-10-14T13:20:00+00:00", "ON-CHAIN DATA", "texto"),
      q("Dez fechamentos semanais seguidos abaixo da média de 50 semanas. Meu limite é oito.", "2026-09-25T22:40:00+00:00", "MARKET UPDATES", "transcricao", 1980)],
    pros: ["Ecossistema com TVL alto."], cons: ["Desbloqueio grande em 20 dias.", "Perde para o BTC há 5 meses."],
    risk: "Desbloqueio de 4% da oferta em 20 dias." },
  PEPE: { vals: ["−41% em 90 d", "−68% da máxima", "volume 0,31×", "0,00% em 90 d", "em 1 corretora(s)", "silêncio 104 d", "menções 0,2× a média"],
    quotes: [q("Memecoin eu trato como bilhete de loteria: mão pequena e prazo curto.", "2026-07-18T17:05:00+00:00", "LOUNGE", "audio")],
    pros: ["Liquidez ainda alta na MEXC."], cons: ["O grupo parou de falar da moeda.", "Risco de deslistagem nas outras corretoras."],
    risk: "Só está em 1 das 4 corretoras." },
  LINK: { vals: ["−22% em 90 d", "−41% da máxima", "volume 0,92×", "1,20% em 90 d", "em 2 corretora(s)", "silêncio 3 d", "menções 1,1× a média"],
    quotes: [q("Saldo de LINK nas corretoras cresceu 9% em um mês. Mais moeda pronta para venda, então diminuo a exposição.", "2026-11-04T10:37:00+00:00", "ON-CHAIN DATA", "foto")],
    pros: ["Uso da rede estável, segundo o analista."], cons: ["Abaixo da média de 200 dias.", "Fraco contra o BTC."],
    risk: null },
  OP: { vals: ["−28% em 90 d", "−79% da máxima", "volume 0,74×", "3,40% em 90 d", "em 1 corretora(s)", "silêncio 32 d", "menções 0,9× a média"],
    quotes: [q("OP fica em meio por cento da carteira até as taxas da rede voltarem a crescer.", "2026-10-06T22:15:00+00:00", null, "transcricao", 4140)],
    pros: ["Fatia pequena na carteira limita a perda."], cons: ["Desbloqueio todo mês.", "Setor fora da narrativa."],
    risk: "Desbloqueio mensal da oferta." },
  BTC: { vals: ["", "−8% da máxima", "volume 1,20×", "inflação 0,80% ao ano", "em 4 corretora(s)", "silêncio 0 d", "menções 1,4× a média"],
    quotes: [q("BTC é 55% da carteira. No rebalanceamento do dia 1º, volto para essa fatia.", "2026-11-04T10:31:00+00:00", "MARKET UPDATES", "texto")],
    pros: ["Tendência de alta.", "Maior fatia da carteira no método do analista."], cons: ["Funding subindo pede atenção."], risk: null },
  ETH: { vals: ["−9% em 90 d", "−29% da máxima", "volume 1,00×", "inflação 0,50% ao ano", "em 4 corretora(s)", "silêncio 5 d", "menções 1,2× a média"],
    quotes: [q("As taxas pagas na rede Ethereum subiram três meses seguidos. É esse dado que me mantém dentro.", "2026-10-29T22:50:00+00:00", "MARKET UPDATES", "transcricao", 2700)],
    pros: ["Acima da média de 200 dias."], cons: ["Fraco contra o BTC."], risk: null },
  SOL: { vals: ["+6% em 90 d", "−42% da máxima", "volume 1,30×", "inflação 4,60% ao ano", "em 4 corretora(s)", "silêncio 3 d", "menções 1,6× a média"],
    quotes: [q("Na rotação deste mês, o setor de pagamentos recebeu o fluxo. SOL ganha 1 ponto na carteira.", "2026-11-02T14:25:00+00:00", "WEEKLY CLOSE", "texto")],
    pros: ["Lucro de 19% sobre o preço médio.", "Forte contra o BTC."], cons: ["Inflação da oferta acima de 4%."], risk: null },
  FET: { vals: ["−12% em 90 d", "−63% da máxima", "volume 1,10×", "0,00% em 90 d", "em 3 corretora(s)", "", "menções 2,1× a média"],
    quotes: [], pros: ["Setor de IA em alta no grupo."], cons: ["Sem análise direta do analista.", "Fraco contra o BTC."], risk: null },
};

type Base = [symbol: string, name: string, exchanges: string[], qty: number, avg: number, price: number, ch: number,
  verdict: Verdict, flags: (0 | 1 | null)[], conf: number, reason: string];

const BASE: Base[] = [
  ["ARB", "Arbitrum", ["binance", "gate"], 4200, 1.65, 0.41, -0.034, "Sair", [1, 1, 1, 1, 0, 1, 0], 0.78,
    "Perdeu 34% contra o BTC em 90 dias. Desbloqueio de 4% da oferta em 20 dias."],
  ["PEPE", "Pepe", ["mexc"], 52_000_000, 0.0000162, 0.0000094, -0.051, "Sair", [1, 1, 1, 0, 1, 1, 1], 0.81,
    "Volume caiu para 0,3 vez a média. Só está em 1 das 4 corretoras."],
  ["LINK", "Chainlink", ["binance", "mexc"], 310, 19.8, 15.62, -0.009, "Reduzir", [1, 1, 0, 0, 0, 1, 0], 0.64,
    "O analista viu o saldo nas corretoras crescer e pediu menos exposição. Abaixo da média de 200 dias."],
  ["OP", "Optimism", ["bybit"], 1800, 2.9, 1.12, -0.022, "Reduzir", [1, 1, 0, 1, 0, 0, 0], 0.59,
    "Fraca contra o BTC e com desbloqueio mensal."],
  ["BTC", "Bitcoin", ["binance", "bybit"], 0.42, 68_400, 101_250, 0.018, "Manter", [null, 0, 0, 0, 0, 0, 0], 0.86,
    "Tendência de alta e dominância subindo. O analista mantém o BTC como a maior fatia da carteira."],
  ["ETH", "Ethereum", ["binance"], 3.1, 3150, 3480, 0.024, "Manter", [1, 0, 0, 0, 0, 0, 0], 0.72,
    "Acima da média de 200 dias. Ainda fraco contra o BTC."],
  ["SOL", "Solana", ["bybit", "gate"], 28, 142, 168.4, 0.031, "Manter", [0, 0, 0, 1, 0, 0, 0], 0.74,
    "Lucro de 19%. O analista aumentou a fatia do setor de pagamentos na rotação do mês."],
  ["FET", "Fetch.ai", ["gate"], 900, 1.9, 1.38, 0.006, "Manter", [1, 0, 0, 0, 0, null, 0], 0.48,
    "Setor de IA em alta no grupo. A posição está abaixo do teto de 3% da carteira."],
];

const CARDS: Card[] = BASE.map(([symbol, name, exchanges, qty, avg, price, ch, verdict, flags, conf, reason]) => ({
  symbol, name, exchanges, price_usd: price, change_24h: ch, value_usd: qty * price,
  pnl_usd: qty * (price - avg), cost_unknown: false,
  verdict, rubric_verdict: verdict, ai_verdict: verdict, confidence: conf,
  alerts: flags.filter((f) => f === 1).length, signals: signals(flags, DETAIL[symbol].vals), reason, no_analyst: false, flag: null,
}));

const total = CARDS.reduce((a, c) => a + c.value_usd, 0);
const pnl = CARDS.reduce((a, c) => a + (c.pnl_usd ?? 0), 0);
const invested = total - pnl;
const SHARES: [string, number][] = [["binance", 0.62], ["bybit", 0.17], ["gate", 0.12], ["mexc", 0.09]];

const PLAYBOOK: Playbook = {
  version_id: 4, approved: false,
  markdown: [
    "# Manual de estratégia", "",
    "## Tamanho de posição", "Nenhuma altcoin passa de 3% da carteira. O rebalanceamento é no dia 1º de cada mês.", "",
    "## Entrada e saída",
    "- Entrar só depois de 2 fechamentos semanais acima da média de 50 semanas.", "- Sair após 8 fechamentos semanais abaixo da média de 50 semanas.", "",
    "## Venda em escada", "Vender 20% da posição cada vez que o preço dobrar. **Sempre** conferir os endereços ativos antes de comprar.",
  ].join("\n"),
  rules: [
    { id: 1, category: "moedas", text: "Nenhuma altcoin passa de 3% da carteira. O excesso volta ao teto no rebalanceamento do dia 1º.", source_ids: ["m:7101"], approved: true },
    { id: 2, category: "realizacao", text: "Vender 20% da posição cada vez que o preço dobrar sobre o preço de compra.", source_ids: ["c:601", "m:7102"], approved: true },
    { id: 3, category: "saida", text: "Sair após 8 fechamentos semanais abaixo da média de 50 semanas.", source_ids: ["m:7103"], approved: false },
    { id: 4, category: "entrada", text: "Entrar só com 2 fechamentos semanais acima da média de 50 semanas e endereços ativos em alta.", source_ids: ["m:7104", "c:602"], approved: false },
  ],
  sources: {
    "m:7101": { date_utc: "2026-10-21T12:15:00+00:00", topic: "MARKET UPDATES", kind: "texto", text: "Teto de 3% por altcoin. O que passar disso volta ao limite no dia 1º.", url: null, t_start: null },
    "c:601": { date_utc: "2026-09-25T22:40:00+00:00", topic: null, kind: "transcricao", text: "Cada vez que a moeda dobra sobre o meu preço de compra, vendo um quinto da posição.", url: "https://www.youtube.com/watch?v=demo190&t=3300s", t_start: 3300 },
    "m:7102": { date_utc: "2026-10-14T13:20:00+00:00", topic: "ON-CHAIN DATA", kind: "foto", text: "Tabela da escada de venda: 2×, 4× e 8× o preço de compra.", url: null, t_start: null },
    "m:7103": { date_utc: "2026-10-14T13:24:00+00:00", topic: "ON-CHAIN DATA", kind: "texto", text: "Oito semanas fechando abaixo da média de 50 semanas é o meu limite.", url: null, t_start: null },
    "m:7104": { date_utc: "2026-11-02T14:25:00+00:00", topic: "WEEKLY CLOSE", kind: "audio", text: "Antes de entrar, quero dois fechamentos semanais acima da média e endereços ativos subindo.", url: null, t_start: null },
    "c:602": { date_utc: "2026-10-08T09:30:00+00:00", topic: null, kind: "link", text: "Texto sobre endereços ativos como medida de uso, indicado pelo analista.", url: "https://example.com/enderecos-ativos", t_start: null },
  },
  trigger_topic_name: "MARKET UPDATES",
  timeline: [
    { id: "m:7110", date_utc: "2026-11-04T10:31:00+00:00", kind: "texto", text: "Fechamento semanal do BTC acima da média de 50 semanas pela 12ª vez seguida." },
    { id: "m:7109", date_utc: "2026-11-03T10:55:00+00:00", kind: "foto", text: "Gráfico com a fatia de cada setor na carteira em novembro." },
    { id: "m:7108", date_utc: "2026-11-01T11:40:00+00:00", kind: "texto", text: "Saldo de BTC nas corretoras no menor nível em 3 anos." },
    { id: "m:7107", date_utc: "2026-10-31T10:45:00+00:00", kind: "audio", text: "Resumo da live: a rotação de setores do mês e o rebalanceamento do dia 1º." },
  ],
  lives: [
    { url: "https://www.youtube.com/watch?v=demo204", status: "pendente", date_utc: "2026-11-04T22:30:00+00:00" },
    { url: "https://www.youtube.com/watch?v=demo203", status: "baixado", date_utc: "2026-11-02T22:30:00+00:00" },
    { url: "https://www.youtube.com/watch?v=demo202", status: "transcrito", date_utc: "2026-10-29T22:30:00+00:00" },
    { url: "https://www.youtube.com/watch?v=demo201", status: "erro", date_utc: "2026-10-26T22:30:00+00:00" },
  ],
  lives_count: { pendente: 1, baixado: 2, transcrito: 9, erro: 1 },
};

const MARKET: Market = {
  fng: { day: "2026-11-04", source: "Alternative.me", value: 62 },
  cg_global: { day: "2026-11-04", source: "CoinGecko", value: { btc_dominance: 57.31 }, change_7d: 0.84 },
  alt_season: { day: "2026-11-04", source: "Calculado a partir do CoinGecko", value: 32 },
  btc_onchain: { day: "2026-11-03", source: "BGeometrics", value: { mvrv: 2.14, nupl: 0.52, sopr: 1.01 } },
  derivs: { day: "2026-11-04", source: "Coinalyze", value: { BTC: { funding: 0.0082, open_interest: 1.8e10, liquidations_24h: 4.1e7 } } },
  dxy: { day: "2026-10-31", source: "FRED", value: 121.38 },
  etf_flows: { day: "2026-11-04", source: "TFTC", value: [{ day: "2026-11-02", net_usd: -88_000_000 }, { day: "2026-11-03", net_usd: 245_300_000 }] },
  stablecoins: { day: "2026-11-04", source: "DefiLlama", value: 2.9e11 },
};

const hr = (n: number, hits: number): HitRate => ({ n, hits, rate: hits / n });
const out = (r_hold: number, r_btc: number, verdict: Verdict) => {
  const r_paper = verdict === "Sair" ? -0.002 : verdict === "Reduzir" ? r_hold / 2 - 0.001 : r_hold;
  return { r_hold, r_paper, r_btc, hit: verdict === "Manter" ? r_hold >= r_btc - 0.002 : r_paper > r_hold };
};
const TRACK: Track = {
  by_verdict: {
    Manter: { "7": hr(24, 15), "30": hr(16, 10) }, Reduzir: { "7": hr(10, 6), "30": hr(6, 4) }, Sair: { "7": hr(8, 6), "30": hr(5, 4) },
  },
  by_signal: {
    S1: { "7": hr(14, 9), "30": hr(9, 6) }, S2: { "7": hr(12, 8) }, S3: { "7": hr(5, 3) }, S4: { "7": hr(6, 3) },
    S5: { "7": hr(2, 2) }, S6: { "7": hr(9, 7), "30": hr(5, 4) }, S7: {},
  },
  verdicts: [
    { id: 41, day: "2026-10-28", symbol: "ARB", verdict: "Sair", outcomes: { "7": out(-0.061, 0.012, "Sair") } },
    { id: 42, day: "2026-10-28", symbol: "BTC", verdict: "Manter", outcomes: { "7": out(0.024, 0.024, "Manter") } },
    { id: 43, day: "2026-10-28", symbol: "LINK", verdict: "Reduzir", outcomes: { "7": out(0.031, 0.024, "Reduzir") } },
    { id: 21, day: "2026-10-05", symbol: "SOL", verdict: "Manter", outcomes: { "7": out(0.052, 0.018, "Manter"), "30": out(0.094, 0.071, "Manter") } },
    { id: 22, day: "2026-10-05", symbol: "PEPE", verdict: "Sair", outcomes: { "7": out(-0.12, 0.018, "Sair"), "30": out(-0.33, 0.071, "Sair") } },
  ],
};

export const SEED: Seed = {
  playbook: PLAYBOOK, market: MARKET, track: TRACK,
  overview: {
    total_usd: total, total_brl: total * 5.42, invested_usd: invested, pnl_usd: pnl, pnl_pct: pnl / invested,
    by_exchange: SHARES.map(([exchange, share]) => ({ exchange, usd: total * share, share, stale: false })),
    // 30 dias de 06/10 a 04/11/2026, com oscilação fixa (testes estáveis).
    history: Array.from({ length: 30 }, (_, i) => ({
      ts: new Date(Date.UTC(2026, 9, 6 + i)).toISOString().slice(0, 10),
      usd: total * (0.94 + i * 0.002 + Math.sin(i / 2.5) * 0.012),
    })),
    spent_month_usd: 3.2, budget_usd: 50, budget_state: "ok",
    last_cycle_utc: "2026-11-04T14:00:00+00:00", playbook_approved: true, analyst_name: "",
    disclaimer: "Material de apoio à decisão, não é recomendação de investimento.",
  },
  verdicts: { day: "2026-11-04", groups: group(CARDS) },
};

function group(cards: Card[]): Record<Verdict, Card[]> {
  return { Sair: cards.filter((c) => c.verdict === "Sair"), Reduzir: cards.filter((c) => c.verdict === "Reduzir"),
    Manter: cards.filter((c) => c.verdict === "Manter") };
}

/** Cópia do SEED com o cartão `symbol` alterado e, opcionalmente, o overview. */
function withCard(seed: Seed, symbol: string, patch: Partial<Card>, ov: Partial<Overview> = {}): Seed {
  const cards = Object.values(seed.verdicts.groups).flat().map((c) => (c.symbol === symbol ? { ...c, ...patch } : c));
  return { ...seed, overview: { ...seed.overview, ...ov }, verdicts: { ...seed.verdicts, groups: group(cards) } };
}

export const SEED_FET_NO_ANALYST_IA_PAUSADA = withCard(SEED, "FET",
  { no_analyst: true, flag: "ai_paused", ai_verdict: null, confidence: null }, { budget_state: "bloqueado", spent_month_usd: 50.1 });

export const SEED_COST_UNKNOWN = withCard(SEED, "PEPE", { cost_unknown: true, pnl_usd: null });

export const SEED_MANUAL_PENDENTE = withCard(SEED, "LINK", { rubric_verdict: "Manter", ai_verdict: "Reduzir" }, {
  playbook_approved: false, total_brl: null,
  by_exchange: SEED.overview.by_exchange.map((e) => ({ ...e, stale: e.exchange === "gate" })),
});

/** O modo de demonstração mostra todos os avisos de uma vez. */
export const DEMO_SEED: Seed = [
  (s: Seed) => withCard(s, "FET", { no_analyst: true, flag: "ai_paused", ai_verdict: null, confidence: null }),
  (s: Seed) => withCard(s, "PEPE", { cost_unknown: true, pnl_usd: null }),
  (s: Seed) => withCard(s, "LINK", { rubric_verdict: "Manter", ai_verdict: "Reduzir" }, { playbook_approved: false }),
  (s: Seed) => withCard(s, "OP", { flag: "ai_failed", ai_verdict: null, confidence: null }, {
    by_exchange: s.overview.by_exchange.map((e) => ({ ...e, stale: e.exchange === "gate" })) }),
].reduce((s, f) => f(s), SEED);

export const SEED_ARB_COST_UNKNOWN = withCard(SEED, "ARB", { cost_unknown: true, pnl_usd: null });

/** Antes do primeiro horizonte de 7 dias: nenhuma amostra. */
export const SEED_TRACK_EMPTY: Seed = {
  ...SEED, track: { by_verdict: {}, by_signal: Object.fromEntries(NAMES.map((_, i) => [`S${i + 1}`, {}])), verdicts: [] },
};

const HELD = Object.fromEntries(BASE.map(([symbol, , , qty, avg]) => [symbol, { qty, avg }]));

/** Cartão depois do preço médio salvo pelo formulário: custo conhecido e resultado recalculado. */
function withOverride(c: Card, avg: number | undefined): Card {
  return avg === undefined ? c : { ...c, cost_unknown: false, pnl_usd: HELD[c.symbol].qty * (c.price_usd - avg) };
}

/** A primeira corretora fica com 70%. Na Binance, parte está na carteira earn. */
function split(exchanges: string[], qty: number) {
  return exchanges.flatMap((exchange, i) => {
    const part = exchanges.length === 1 ? qty : i === 0 ? qty * 0.7 : (qty * 0.3) / (exchanges.length - 1);
    return exchange === "binance"
      ? [{ exchange, wallet: "spot", qty: part * 0.8 }, { exchange, wallet: "earn", qty: part * 0.2 }]
      : [{ exchange, wallet: "spot", qty: part }];
  });
}

/** Moeda abaixo de US$ 10: fica fora do veredito e aparece só na seção de poeira da Carteira. */
const DUST: Portfolio["coins"] = [
  { symbol: "DOGE", name: "Dogecoin", qty: 50, price_usd: 0.18, value_usd: 9, share: null, avg_cost_usd: 0.31, cost_unknown: false,
    pnl_usd: 50 * (0.18 - 0.31), exchanges: ["mexc"], positions: [{ exchange: "mexc", wallet: "spot", qty: 50, stale: false, permissions_verified: false }] },
];

/** Resposta do GET /api/portfolio: uma moeda por cartão (com o preço médio salvo, se houver) e a poeira. */
function portfolio(cards: Card[], overrides: Record<string, number>, stale: Set<string>): Portfolio {
  const coins = [...cards.map((c) => {
    const { qty, avg } = HELD[c.symbol];
    return {
      symbol: c.symbol, name: c.name, qty, price_usd: c.price_usd, value_usd: c.value_usd, share: null,
      avg_cost_usd: overrides[c.symbol] ?? (c.cost_unknown ? null : avg), cost_unknown: c.cost_unknown, pnl_usd: c.pnl_usd,
      exchanges: c.exchanges, positions: split(c.exchanges, qty).map((p) => ({
        ...p, stale: stale.has(p.exchange), permissions_verified: !["mexc", "gate"].includes(p.exchange) })),
    };
  }), ...DUST];
  const total = coins.reduce((a, c) => a + (c.value_usd ?? 0), 0);
  return { total_usd: total, coins: coins.map((c) => ({ ...c, share: (c.value_usd ?? 0) / total })).sort((a, b) => (b.value_usd ?? 0) - (a.value_usd ?? 0)) };
}

/** Resposta do GET /api/coins/{symbol}: 90 dias de fechamento terminando no preço atual. */
function coinDetail(card: Card, override: number | undefined): CoinDetail {
  const { qty, avg } = HELD[card.symbol];
  const c = withOverride(card, override);
  const avgCost = override ?? (c.cost_unknown ? null : avg);
  const start = avgCost === null ? c.price_usd * 1.2 : (avgCost + c.price_usd) / 2;
  const d = DETAIL[c.symbol];
  return {
    ...c, avg_cost_usd: avgCost, qty,
    by_exchange: split(c.exchanges, qty),
    candles: Array.from({ length: 90 }, (_, i) => ({
      day: new Date(Date.UTC(2026, 10, 4 - 89 + i)).toISOString().slice(0, 10),
      close: i === 89 ? c.price_usd : (start + ((c.price_usd - start) * i) / 89) * (1 + Math.sin(i / 4) * 0.04),
    })),
    pros: d.pros, cons: d.cons, main_risk: d.risk, quotes: d.quotes.map((x, i) => ({ id: `m:${i}`, ...x })),
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/**
 * `fetch` falso que responde as rotas da API com o seed. Rota desconhecida dá 404.
 * O POST /api/cost-overrides valida como o backend (422 com a lista do pydantic) e vale para as consultas seguintes.
 * A aprovação de regra também vale para as consultas seguintes. O POST /api/csv/{corretora} responde 413 acima de 5 MB
 * e 422 quando a primeira linha não tem vírgula.
 */
const SECRET_NAMES: SecretName[] = [
  "binance_key", "binance_secret", "mexc_key", "mexc_secret", "bybit_key", "bybit_secret", "gate_key", "gate_secret",
  "anthropic_api_key", "telegram_api_id", "telegram_api_hash", "telegram_session", "telegram_group_id",
  "telegram_bot_token", "telegram_chat_id", "coingecko_key", "coinalyze_key", "fred_key", "coinglass_key", "hf_token",
];
const REQUIRED = ["anthropic_api_key", "telegram_api_id", "telegram_api_hash", "telegram_group_id", "telegram_bot_token", "telegram_chat_id"];
const UNVERIFIED = ["mexc", "gate"];

/** Estado da página Configuração no `fetch` falso: começa sem nenhum segredo, como um Mac recém-instalado. */
function setupState(mode: Setup["mode"]) {
  const secrets = Object.fromEntries(SECRET_NAMES.map((n) => [n, false])) as Record<SecretName, boolean>;
  const config: SetupConfig = { owner_name: "", analyst_username: "", analyst_name: "", confirmed_read_only: [], budget_usd: 50, budget_alert_ratio: 0.8,
    dust_usd: 10, cutoff_hour: 12, intraday_move: 0.1, sync_minutes: 5, tz: "America/Sao_Paulo", data_dir: "~/quilate-dados" };
  const st = { secrets, config, mode, restart: false, login: { sent: false } };
  const missing = () => [...REQUIRED.filter((n) => !secrets[n as SecretName]), ...(config.analyst_username ? [] : ["analyst_username"])];
  const status = (): Setup => {
    const every = (...n: SecretName[]) => n.every((x) => secrets[x]);
    const withKeys = (["binance", "mexc", "bybit", "gate"] as const).filter((e) => secrets[`${e}_key`] && secrets[`${e}_secret`]);
    const pending = withKeys.filter((e) => UNVERIFIED.includes(e) && !config.confirmed_read_only.includes(e));
    const data = { messages: 0, trades: 0, positions: 0, verdicts: 0, playbook: false };
    return { mode: st.mode, secrets, config, data, restart_required: st.restart, missing_for_serve: missing(), required_secrets: REQUIRED,
      checklist: [
        { id: "analista", label: "Usuário do analista no Telegram", done: !!config.analyst_username, how: "Quem publica as análises no grupo, sem @." },
        { id: "corretoras", label: "Chave somente leitura de pelo menos uma corretora", done: withKeys.length > 0, how: "Crie a chave no site da corretora, sem trade nem saque, e grave aqui." },
        { id: "confirmacao", label: "MEXC e Gate confirmadas como somente leitura", done: pending.length === 0, how: pending.length ? `Pendente: ${pending.join(", ")}.` : "Só MEXC e Gate." },
        { id: "telegram_app", label: "Aplicativo do Telegram (api_id, api_hash e id do grupo)", done: every("telegram_api_id", "telegram_api_hash", "telegram_group_id"), how: "Crie o aplicativo em my.telegram.org e informe o id do grupo." },
        { id: "telegram_login", label: "Login do Telegram (sessão no Keychain)", done: secrets.telegram_session, how: "Telefone, código e senha de duas etapas." },
        { id: "bot", label: "Bot dos avisos (token e chat)", done: every("telegram_bot_token", "telegram_chat_id"), how: "Bot criado no @BotFather e o id do seu chat com ele." },
        { id: "claude", label: "Chave da API do Claude", done: secrets.anthropic_api_key, how: "Chave criada no console da Anthropic." },
        { id: "mercado", label: "Chaves de dados de mercado (CoinGecko, Coinalyze, FRED)", done: every("coingecko_key", "coinalyze_key", "fred_key"), how: "Planos gratuitos bastam. A CoinGlass é opcional." },
        { id: "hf", label: "Token do Hugging Face (licença do EmbeddingGemma aceita)", done: secrets.hf_token, how: "Aceite a licença do google/embeddinggemma-300m e crie um token de leitura." },
        { id: "importar", label: "Histórico do grupo importado", done: false, how: "No terminal: cd ~/quilate/backend && uv run quilate importar --meses 12" },
        { id: "manual", label: "Manual inicial do analista criado", done: false, how: "No terminal: cd ~/quilate/backend && uv run quilate manual-inicial" },
        { id: "servir", label: "Servidor completo no ar (agendador, corretoras e Telegram)", done: st.mode === "full", how: "Use Reiniciar o servidor." },
      ] };
  };
  return { st, status, missing };
}

export function mockApi(seed: Seed, setupMode: Setup["mode"] = "setup"): typeof fetch {
  const overrides: Record<string, number> = {};
  const setup = setupState(setupMode);
  const rules = seed.playbook.rules.map((r) => ({ ...r }));
  const stale = new Set(seed.overview.by_exchange.filter((e) => e.stale).map((e) => e.exchange));
  const cards = () => Object.values(seed.verdicts.groups).flat().map((c) => withOverride(c, overrides[c.symbol]));
  return async (input, init) => {
    const path = new URL(String(input), "http://127.0.0.1").pathname;
    if (path === "/api/overview") return json(seed.overview);
    if (path === "/api/portfolio") return json(portfolio(cards(), overrides, stale));
    if (path === "/api/market") return json(seed.market);
    if (path === "/api/track") return json(seed.track);
    if (path === "/api/playbook") return json({ ...seed.playbook, rules, approved: rules.every((r) => r.approved) });
    const approve = /^\/api\/playbook\/rules\/(\d+)\/approve$/.exec(path);
    if (approve && init?.method === "POST") {
      const rule = rules.find((r) => r.id === Number(approve[1]));
      if (!rule) return json({ detail: "Regra não encontrada." }, 404);
      rule.approved = true;
      return json({ ok: true, playbook_approved: rules.every((r) => r.approved) });
    }
    const csv = /^\/api\/csv\/(binance|mexc|bybit|gate)$/.exec(path);
    if (csv && init?.method === "POST") {
      const file = init.body as Blob;
      if (file.size > 5 * 1024 * 1024) return json({ detail: "Arquivo acima de 5 MB." }, 413);
      const lines = (await file.text()).split("\n").filter((l) => l.trim());
      if (!lines[0]?.includes(",")) return json({ detail: `CSV fora do formato de ${csv[1]}: KeyError` }, 422);
      return json({ imported: lines.length - 1, read: lines.length - 1 });
    }
    if (path === "/api/verdicts") return json({ ...seed.verdicts, groups: group(cards()) });
    const coin = /^\/api\/coins\/([^/]+)$/.exec(path);
    const card = coin && Object.values(seed.verdicts.groups).flat().find((c) => c.symbol === coin[1]);
    if (card) return json(coinDetail(card, overrides[card.symbol]));
    if (coin) return json({ detail: "Moeda sem veredito." }, 404);
    if (path === "/api/cost-overrides" && init?.method === "POST") {
      const b = JSON.parse(String(init.body));
      const msg = typeof b.avg_cost_usd !== "number" ? "Input should be a valid number"
        : b.avg_cost_usd > 0 ? null : "Input should be greater than 0";
      if (msg) return json({ detail: [{ type: "value_error", loc: ["body", "avg_cost_usd"], msg }] }, 422);
      overrides[b.symbol] = b.avg_cost_usd;
      return json({ ok: true, ...b });
    }
    if (path.startsWith("/api/setup")) return setupApi(setup, path, init);
    return json({ detail: "Não há dado de demonstração para esta rota." }, 404);
  };
}

async function setupApi(setup: ReturnType<typeof setupState>, path: string, init?: RequestInit): Promise<Response> {
  const { st, status, missing } = setup;
  const body = init?.body ? JSON.parse(String(init.body)) : {};
  const secret = /^\/api\/setup\/secrets\/([a-z_]+)$/.exec(path);
  if (path === "/api/setup") return json(status());
  if (secret) {
    const name = secret[1] as SecretName;
    if (!SECRET_NAMES.includes(name)) return json({ detail: "Segredo desconhecido." }, 404);
    if (init?.method === "DELETE") { st.secrets[name] = false; return json({ ok: true, name }); }
    if (typeof body.value !== "string" || !body.value.trim()) return json({ detail: [{ msg: "String should have at least 1 character" }] }, 422);
    st.secrets[name] = true;
    return json({ ok: true, name });
  }
  if (path === "/api/setup/config" && init?.method === "PUT") {
    const bad = (body.confirmed_read_only ?? []).filter((e: string) => !UNVERIFIED.includes(e));
    if (bad.length) return json({ detail: `Só MEXC e Gate precisam de confirmação. Recusado: ${bad.join(", ")}.` }, 422);
    if (body.analyst_username !== undefined) body.analyst_username = body.analyst_username.replace(/^@/, "");
    if (body.confirmed_read_only) body.confirmed_read_only = [...new Set(body.confirmed_read_only as string[])].sort();
    Object.assign(st.config, body);
    st.restart ||= ["sync_minutes", "confirmed_read_only", "analyst_username"].some((k) => k in body);
    return json({ ok: true, config: st.config, restart_required: st.restart });
  }
  if (path === "/api/setup/check-keys") {
    const exchanges: KeyCheck[] = (["binance", "mexc", "bybit", "gate"] as const).map((e) => {
      if (!(st.secrets[`${e}_key`] && st.secrets[`${e}_secret`])) return { exchange: e, status: "missing", detail: "sem chave no Keychain" };
      if (UNVERIFIED.includes(e) && !st.config.confirmed_read_only.includes(e))
        return { exchange: e, status: "unconfirmed", detail: "a API não informa a permissão: confira no site e marque a confirmação" };
      return { exchange: e, status: "ok", detail: "somente leitura confirmada" };
    });
    return json({ exchanges, safe: exchanges.every((x) => x.status === "ok" || x.status === "missing") });
  }
  if (path === "/api/setup/telegram/send-code") {
    if (!st.secrets.telegram_api_id || !st.secrets.telegram_api_hash) return json({ detail: "Grave telegram_api_id antes do login." }, 409);
    st.login.sent = true;
    return json({ ok: true });
  }
  if (path === "/api/setup/telegram/sign-in") {
    if (!st.login.sent) return json({ detail: "Peça o código antes." }, 409);
    if (!body.password) return json({ ok: false, needs_password: true });
    st.secrets.telegram_session = true;
    st.login.sent = false;
    return json({ ok: true, username: "demo_user" });
  }
  if (path === "/api/setup/restart") {
    st.restart = false;
    if (missing().length === 0) st.mode = "full";
    return json({ ok: true });
  }
  return json({ detail: "Não há dado de demonstração para esta rota." }, 404);
}

/** API do modo de demonstração. Uma só instância: o preço médio salvo vale até recarregar a página.
 * O servidor finge estar completo: as páginas não mostram a faixa de instalação incompleta,
 * e a Configuração continua com as etapas pendentes do checklist. */
export const demoApi = mockApi(DEMO_SEED, "full");

/** Ticks falsos a cada 600 ms para o modo de demonstração. Devolve a função que para. */
export function demoTicks(onTick: (t: Tick) => void): () => void {
  const last = Object.fromEntries(Object.values(DEMO_SEED.verdicts.groups).flat().map((c) => [c.symbol, c.price_usd]));
  const symbols = Object.keys(last);
  const id = setInterval(() => {
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    last[symbol] *= 1 + (Math.random() - 0.5) * 0.008;
    onTick({ symbol, price_usd: last[symbol] });
  }, 600);
  return () => clearInterval(id);
}
