export type Verdict = "Manter" | "Reduzir" | "Sair";
export type BudgetState = string; // valores definidos em backend/quilate/budget.py

export type Signal = { code: string; name: string; alert: boolean | null; value: unknown }; // alert null = sem dado

export type Card = {
  symbol: string; name: string; exchanges: string[];
  price_usd: number; change_24h: number | null; value_usd: number;
  pnl_usd: number | null; cost_unknown: boolean;
  verdict: Verdict; rubric_verdict: Verdict; ai_verdict: Verdict | null;
  confidence: number | null;
  alerts: number; // quantos dos 7 sinais estão em alerta
  signals: Signal[]; reason: string; no_analyst: boolean; flag: string | null;
};

export type Overview = {
  total_usd: number; total_brl: number | null;
  invested_usd: number; pnl_usd: number; pnl_pct: number | null; // fração (0,1 = 10%)
  by_exchange: { exchange: string; usd: number; stale: boolean; share: number }[];
  history: { ts: string; usd: number }[]; // ts = AAAA-MM-DD
  spent_month_usd: number; budget_usd: number; budget_state: BudgetState;
  last_cycle_utc: string | null; playbook_approved: boolean; disclaimer: string;
  analyst_name: string; // nome de exibição do analista; vazio quando o dono não configurou
};

export type Verdicts = { day: string; groups: Record<Verdict, Card[]> };

export type Quote = { id: string | null; text: string; date_utc: string; topic: string | null; kind: string; t_start: number | null };

export type CoinDetail = Card & {
  avg_cost_usd: number | null; qty: number;
  by_exchange: { exchange: string; wallet: string | null; qty: number }[];
  candles: { day: string; close: number }[];
  pros: string[]; cons: string[]; main_risk: string | null; quotes: Quote[];
};

export type Portfolio = {
  total_usd: number;
  coins: {
    symbol: string; name: string; qty: number; price_usd: number | null; value_usd: number | null;
    share: number | null; avg_cost_usd: number | null; cost_unknown: boolean; pnl_usd: number | null;
    exchanges: string[]; positions: { exchange: string; wallet: string | null; qty: number; stale: boolean; permissions_verified: boolean }[];
  }[];
};

/** `change_7d` só vem em `cg_global`: dominância de hoje menos a de 6 dias antes, em pontos percentuais. */
export type MarketItem = { day: string; source: string; value: unknown; change_7d?: number | null } | null;
export type Market = Record<string, MarketItem>;

export type HitRate = { n: number; hits: number; rate: number };
/** Retornos em fração. `r_paper` é o retorno se o veredito fosse seguido. */
export type Outcome = { r_hold: number; r_paper: number; r_btc: number; hit: boolean };
export type TrackedVerdict = { id: number; day: string; symbol: string; verdict: Verdict; outcomes: Record<string, Outcome> };
export type Track = {
  by_verdict: Partial<Record<Verdict, Record<string, HitRate>>>;
  by_signal: Record<string, Record<string, HitRate>>;
  verdicts: TrackedVerdict[]; // os mais recentes primeiro, só os que já têm resultado
};

export type Rule = { id: number; category: string; text: string; source_ids: string[]; approved: boolean };
export type Source = Omit<Quote, "id"> & { url: string | null };
export type LiveJob = { url: string; status: string; date_utc: string | null };
export type Playbook = {
  version_id: number | null; markdown: string; approved: boolean; rules: Rule[];
  sources: Record<string, Source>; // fontes citadas nas regras, por id (m:<msg> ou c:<trecho>)
  trigger_topic_name: string | null; // nulo sem tópico de gatilho, e então `timeline` vem vazia
  timeline: { id: string; date_utc: string; text: string; kind: string }[]; // análises do analista no tópico do gatilho
  lives: LiveJob[]; lives_count: Record<string, number>; // status: pendente, baixado, transcrito, erro
};

export type CostOverrideBody = { symbol: string; avg_cost_usd: number; qty?: number | null; note?: string | null };
export type Exchange = "binance" | "mexc" | "bybit" | "gate";

/** Página Configuração: espelho de `backend/quilate/api/setup.py`. Segredo só aparece como existe ou não. */
export type SecretName =
  | "binance_key" | "binance_secret" | "mexc_key" | "mexc_secret" | "bybit_key" | "bybit_secret" | "gate_key" | "gate_secret"
  | "anthropic_api_key" | "telegram_api_id" | "telegram_api_hash" | "telegram_session" | "telegram_group_id"
  | "telegram_bot_token" | "telegram_chat_id" | "coingecko_key" | "coinalyze_key" | "fred_key" | "coinglass_key" | "hf_token";
export type SetupConfig = {
  owner_name: string; analyst_username: string; analyst_name: string; confirmed_read_only: string[];
  budget_usd: number; budget_alert_ratio: number; dust_usd: number; cutoff_hour: number; intraday_move: number;
  sync_minutes: number; tz: string; data_dir: string;
};
export type SetupStep = { id: string; label: string; done: boolean; how: string };
export type Setup = {
  mode: "setup" | "full"; secrets: Record<SecretName, boolean>; config: SetupConfig;
  data: { messages: number; trades: number; positions: number; verdicts: number; playbook: boolean };
  checklist: SetupStep[]; restart_required: boolean; missing_for_serve: string[]; required_secrets: string[];
};
export type KeyCheck = { exchange: Exchange; status: "ok" | "unsafe" | "unconfirmed" | "missing" | "error"; detail: string };
