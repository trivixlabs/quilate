import type {
  CoinDetail, CostOverrideBody, Exchange, KeyCheck, Market, Overview, Playbook, Portfolio, SecretName, Setup, SetupConfig,
  Track, Verdicts,
} from "./types";

/** Modo de demonstração: `?demo=1`, só no `npm run dev`. O build de produção remove este ramo. */
export const DEMO = import.meta.env.DEV && new URLSearchParams(location.search).get("demo") === "1";

/**
 * Erro da API com mensagem em português, pronta para a tela. `status` é 0 quando o servidor não responde.
 * O 422 do pydantic vem em inglês: a mensagem fica genérica e quem chama decide o texto pelo `status`.
 */
export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  // DEV repetido no ponto do import: assim o build de produção descarta o chunk dos dados fictícios.
  const f = import.meta.env.DEV && DEMO ? await import("../test/fixtures").then((m) => m.demoApi) : fetch;
  let r: Response;
  try {
    r = await f(url, init);
  } catch {
    throw new ApiError(0, "o sistema local não respondeu");
  }
  if (!r.ok) {
    let detail = "";
    try {
      const d = (await r.json()).detail;
      // O backend escreve o `detail` em português e com ponto final. "Not Found" e afins são do Starlette, em inglês.
      // ponytail: heurística pelo formato da frase; trocar por código de erro se o backend passar a ter um.
      if (typeof d === "string" && r.status !== 422 && !/^[A-Za-z ]+$/.test(d)) detail = d;
    } catch { /* corpo não é JSON */ }
    throw new ApiError(r.status, detail || (r.status === 422 ? "dados recusados pelo sistema" : "o sistema local recusou o pedido"));
  }
  return r.json() as Promise<T>;
}

const post = (body: BodyInit | null, headers?: HeadersInit): RequestInit => ({ method: "POST", body, headers });

export const getOverview = () => req<Overview>("/api/overview");
export const getVerdicts = (day?: string) => req<Verdicts>(`/api/verdicts${day ? `?day=${encodeURIComponent(day)}` : ""}`);
export const getCoin = (symbol: string) => req<CoinDetail>(`/api/coins/${encodeURIComponent(symbol)}`);
export const getPortfolio = () => req<Portfolio>("/api/portfolio");
export const getMarket = () => req<Market>("/api/market");
export const getTrack = () => req<Track>("/api/track");
export const getPlaybook = () => req<Playbook>("/api/playbook");
export const approveRule = (id: number) =>
  req<{ ok: boolean; playbook_approved: boolean }>(`/api/playbook/rules/${id}/approve`, post(null));
export const saveCostOverride = (body: CostOverrideBody) =>
  req<{ ok: boolean } & CostOverrideBody>("/api/cost-overrides", post(JSON.stringify(body), { "Content-Type": "application/json" }));
/** Corpo cru do arquivo, sem multipart (o backend lê o corpo da requisição, máximo 5 MB). */
export const uploadCsv = (exchange: Exchange, file: Blob) =>
  req<{ imported: number; read: number }>(`/api/csv/${exchange}`, post(file, { "Content-Type": "text/csv" }));

// Página Configuração. O valor do segredo só viaja no corpo do POST, para 127.0.0.1, e nunca volta.
const json = (body: unknown, method = "POST"): RequestInit =>
  ({ method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
export const getSetup = () => req<Setup>("/api/setup");
export const saveSecret = (name: SecretName, value: string) =>
  req<{ ok: boolean; name: string }>(`/api/setup/secrets/${name}`, json({ value }));
export const deleteSecret = (name: SecretName) =>
  req<{ ok: boolean; name: string }>(`/api/setup/secrets/${name}`, { method: "DELETE" });
export const saveConfig = (body: Partial<Omit<SetupConfig, "tz" | "data_dir">>) =>
  req<{ ok: boolean; config: SetupConfig; restart_required: boolean }>("/api/setup/config", json(body, "PUT"));
export const checkKeys = () => req<{ exchanges: KeyCheck[]; safe: boolean }>("/api/setup/check-keys", json({}));
export const telegramSendCode = (phone: string) => req<{ ok: boolean }>("/api/setup/telegram/send-code", json({ phone }));
export const telegramSignIn = (code: string, password?: string) =>
  req<{ ok: boolean; needs_password?: boolean; username?: string | null }>("/api/setup/telegram/sign-in", json({ code, password }));
export const restartServer = () => req<{ ok: boolean }>("/api/setup/restart", json({}));
