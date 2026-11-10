import { createContext, createElement, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { DEMO } from "./api";
import type { Card } from "./types";

export type LivePrice = { price: number; dir: 1 | -1 | 0; flashUntil: number };
export type LiveState = Record<string, LivePrice>;
export type Tick = { symbol: string; price_usd: number };
export type LiveEvent = { type: "verdict"; symbol: string } | { type: "cycle"; day: string };

const FLASH_MS = 700;

/** Redutor puro: preço novo marca a direção e a piscada. Preço igual não muda nada. */
export function applyTick(state: LiveState, tick: Tick, now: number): LiveState {
  const old = state[tick.symbol];
  if (!old) return { ...state, [tick.symbol]: { price: tick.price_usd, dir: 0, flashUntil: 0 } };
  if (tick.price_usd === old.price) return state;
  const dir = tick.price_usd > old.price ? 1 : -1;
  return { ...state, [tick.symbol]: { price: tick.price_usd, dir, flashUntil: now + FLASH_MS } };
}

/** Cartão com o preço do último tick: posição, resultado e variação seguem a mesma proporção. */
export function withLive<T extends Card>(c: T, price: number): T {
  const r = price / c.price_usd, gain = c.value_usd * (r - 1);
  return {
    ...c, price_usd: price, value_usd: c.value_usd + gain,
    pnl_usd: c.pnl_usd === null ? null : c.pnl_usd + gain,
    change_24h: c.change_24h === null ? null : (1 + c.change_24h) * r - 1,
  };
}

/** Espera de reconexão: 1 s dobrando até 30 s. */
export const backoff = (attempt: number) => Math.min(1000 * 2 ** attempt, 30_000);

export type Live = { prices: LiveState; connected: boolean; lastEvent: LiveEvent | null };

/** Uma conexão só para a tela inteira. */
function useLiveSocket(): Live {
  const [prices, setPrices] = useState<LiveState>({});
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const attempt = useRef(0);

  useEffect(() => {
    if (import.meta.env.DEV && DEMO) {
      setConnected(true);
      let stop: (() => void) | undefined, off = false;
      import("../test/fixtures").then((f) => {
        if (!off) stop = f.demoTicks((t) => setPrices((s) => applyTick(s, t, Date.now())));
      });
      return () => { off = true; stop?.(); };
    }
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const open = () => {
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      ws.onopen = () => { attempt.current = 0; setConnected(true); };
      ws.onmessage = (m) => {
        let e: { type?: string; symbol?: string; price_usd?: number };
        try { e = JSON.parse(m.data); } catch { return; }
        if (e.type === "tick" && typeof e.symbol === "string" && typeof e.price_usd === "number") {
          const tick = { symbol: e.symbol, price_usd: e.price_usd };
          setPrices((s) => applyTick(s, tick, Date.now()));
        } else if (e.type === "verdict" || e.type === "cycle") {
          setLastEvent(e as LiveEvent);
        }
      };
      ws.onclose = () => {
        if (closed) return; // fechamento nosso (StrictMode, troca de página): não mostrar "Reconectando…"
        setConnected(false);
        timer = setTimeout(open, backoff(attempt.current++));
      };
    };
    open();
    return () => { closed = true; clearTimeout(timer); ws?.close(); };
  }, []);

  return { prices, connected, lastEvent };
}

const LiveContext = createContext<Live | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  return createElement(LiveContext.Provider, { value: useLiveSocket() }, children);
}

/** `lastEvent` muda a cada veredito ou ciclo novo: as páginas refazem a consulta quando ele muda. */
export function useLive(): Live {
  const live = useContext(LiveContext);
  if (!live) throw new Error("useLive precisa do LiveProvider.");
  return live;
}

/**
 * Consulta da página: refaz a cada veredito ou ciclo novo (`lastEvent`) e quando `key` muda.
 * Falha depois de um acerto mantém o último dado e preenche `error`.
 */
export function useLiveQuery<T>(load: () => Promise<T>, key = 0) {
  const { lastEvent } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let off = false;
    load().then((d) => { if (!off) { setData(d); setError(null); } }, (e: Error) => { if (!off) setError(e.message); });
    return () => { off = true; };
  }, [lastEvent, key]); // `load` é uma função fixa da API: fora das dependências
  return { data, error, setData };
}
