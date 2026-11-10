import { useId, type ReactNode } from "react";
import { getMarket } from "@/lib/api";
import { day } from "@/lib/format";
import { useLiveQuery } from "@/lib/live";
import type { MarketItem } from "@/lib/types";
import { LoadState, StaleError } from "@/components/LoadState";

const MINUS = "−";
const fmt = (d: number) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
const N0 = fmt(0), N2 = fmt(2), N4 = fmt(4);
const signed = (f: Intl.NumberFormat, v: number) => `${v < 0 ? MINUS : "+"}${f.format(Math.abs(v))}`;
const COMPACT = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const DAY_MONTH = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", day: "2-digit", month: "2-digit" });

const FNG: [number, string][] = [[25, "medo extremo"], [45, "medo"], [56, "neutro"], [76, "ganância"], [101, "ganância extrema"]];
const fngWord = (v: number) => FNG.find(([lim]) => v < lim)![1];

/** Número em `value[...path]`, ou null quando falta ou não é número. */
function num(value: unknown, ...path: string[]): number | null {
  const v = path.reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), value);
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

type Shown = { value: string | null; note?: string };
type Tile = [label: string, key: string, show: (item: NonNullable<MarketItem>) => Shown];

const TILES: Tile[] = [
  ["Medo e Ganância", "fng", (i) => {
    const v = num(i.value);
    return { value: v === null ? null : `${N0.format(v)} de 100`, note: v === null ? undefined : `${fngWord(v)}. 0 é pânico, 100 é euforia.` };
  }],
  ["Dominância do BTC", "cg_global", (i) => {
    const v = num(i.value, "btc_dominance"), ch = i.change_7d ?? null;
    return { value: v === null ? null : `${N2.format(v)}%`,
      note: ch === null ? "Variação de 7 dias ainda sem dado." : `${signed(N2, ch)} p.p. em 7 dias` };
  }],
  ["Altcoin Season Index", "alt_season", (i) => {
    const v = num(i.value);
    return { value: v === null ? null : `${N0.format(v)} de 100`, note: "Parte das 50 maiores altcoins que rendeu mais que o BTC em 90 dias." };
  }],
  ["MVRV do BTC", "btc_onchain", (i) => {
    const v = num(i.value, "mvrv");
    return { value: v === null ? null : N2.format(v) };
  }],
  ["NUPL do BTC", "btc_onchain", (i) => {
    const v = num(i.value, "nupl");
    return { value: v === null ? null : N2.format(v) };
  }],
  // ponytail: unidade da Coinalyze não confirmada na documentação; tratada como percentual por período.
  ["Funding do BTC", "derivs", (i) => {
    const v = num(i.value, "BTC", "funding");
    return { value: v === null ? null : `${v < 0 ? MINUS : ""}${N4.format(Math.abs(v))}%`, note: "Taxa dos contratos perpétuos." };
  }],
  ["Fluxo dos ETFs de BTC", "etf_flows", (i) => {
    const last = Array.isArray(i.value) ? i.value.at(-1) : undefined;
    const v = num(last, "net_usd"), d = (last as { day?: unknown } | undefined)?.day;
    return { value: v === null ? null : `${v < 0 ? MINUS : "+"}US$ ${COMPACT.format(Math.abs(v))}`,
      note: typeof d === "string" ? `Fluxo líquido de ${DAY_MONTH.format(new Date(`${d}T00:00:00Z`))}.` : undefined };
  }],
  ["Dólar (índice amplo)", "dxy", (i) => {
    const v = num(i.value);
    return { value: v === null ? null : N2.format(v), note: "Índice amplo do dólar do Fed (DTWEXBGS)." };
  }],
];

/** Gráfico de cada indicador em destaque. Recebe o item já coletado; sem número, não desenha nada. */
const VISUAL: Record<string, (item: NonNullable<MarketItem>) => ReactNode> = {
  fng: (i) => {
    const v = num(i.value);
    if (v === null) return null;
    const angle = (v - 50) * 1.8;  // 0 aponta para a esquerda, 100 para a direita
    return (
      <svg viewBox="0 0 200 112" role="img" aria-label={`Índice ${N0.format(v)} de 100, ${fngWord(v)}`} className="mx-auto w-full max-w-[240px]">
        <defs>
          <linearGradient id="fng" x1="0" x2="1">
            <stop offset="0" stopColor="var(--color-sair)" /><stop offset=".5" stopColor="var(--color-reduzir)" /><stop offset="1" stopColor="var(--color-alta)" />
          </linearGradient>
        </defs>
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="#1c2130" strokeWidth="14" strokeLinecap="round" />
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="url(#fng)" strokeWidth="14" strokeLinecap="round" pathLength={100}
          strokeDasharray={`${v} 100`} className="gauge-arc" />
        <g className="gauge-needle" style={{ transform: `rotate(${angle}deg)`, transformOrigin: "100px 100px" }}>
          <path d="M100 100 L100 34" stroke="var(--color-texto)" strokeWidth="3" strokeLinecap="round" />
        </g>
        <circle cx="100" cy="100" r="6" fill="var(--color-texto)" />
      </svg>
    );
  },
  cg_global: (i) => {
    const v = num(i.value, "btc_dominance");
    if (v === null) return null;
    return (
      <div className="flex flex-col gap-1.5">
        <div aria-hidden="true" className="flex h-3 gap-0.5 overflow-hidden rounded-full">
          <span className="bg-[#f59e0b] transition-[flex-grow] duration-700" style={{ flexGrow: v }} />
          <span className="bg-[#2b3247]" style={{ flexGrow: 100 - v }} />
        </div>
        <div className="flex justify-between text-[11px] text-texto-2"><span>BTC</span><span>outras moedas</span></div>
      </div>
    );
  },
  alt_season: (i) => {
    const v = num(i.value);
    if (v === null) return null;
    return (
      <div className="flex flex-col gap-1.5">
        <div aria-hidden="true" className="relative mt-2">
          <div className="h-3 rounded-full bg-[linear-gradient(90deg,#f59e0b_0_25%,#2b3247_25%_75%,var(--color-violeta)_75%_100%)]" />
          <span className="absolute -top-1.5 h-6 w-1 -translate-x-1/2 rounded-sm bg-texto shadow-[0_0_0_3px_var(--color-painel)] transition-[left] duration-700"
            style={{ left: `${Math.min(100, Math.max(0, v))}%` }} />
        </div>
        <div className="flex justify-between text-[11px] text-texto-2"><span>Temporada do BTC</span><span>Temporada alt</span></div>
      </div>
    );
  },
};

/** Aba Mercado: três indicadores em destaque com gráfico e os outros em cartões, com a fonte e o dia da coleta. */
export function Mercado() {
  const { data, error } = useLiveQuery(getMarket);
  if (!data) return <LoadState what="os dados de mercado" error={error} />;
  const featured = TILES.filter(([, key]) => key in VISUAL), others = TILES.filter(([, key]) => !(key in VISUAL));
  return (
    <div className="flex flex-col gap-6">
      <header className="flex max-w-3xl flex-col gap-1.5">
        <h1 className="m-0 text-[28px] font-semibold tracking-tight">Mercado</h1>
        <p className="m-0 text-sm leading-relaxed text-texto-2">
          O clima geral do mercado, coletado todo dia às 3h. Estes números entram na régua como filtro: com o BTC forte,
          altcoin precisa de mais motivo para ficar. Dado com mais de 7 dias conta como sem dado.
        </p>
      </header>
      <StaleError error={error} />
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(280px, 100%), 1fr))" }}>
        {featured.map(([label, key, show], i) =>
          <MarketTile key={label} label={label} item={data[key] ?? null} show={show} visual={VISUAL[key]} delay={i * 60} />)}
      </div>
      <section aria-labelledby="outros" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="outros" className="m-0 text-lg font-semibold">Outros indicadores</h2>
          <span className="text-[13px] text-texto-2">Blockchain do BTC, derivativos, ETFs e dólar.</span>
        </div>
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(220px, 100%), 1fr))" }}>
          {others.map(([label, key, show], i) =>
            <MarketTile key={label} label={label} item={data[key] ?? null} show={show} small delay={180 + i * 50} />)}
        </div>
      </section>
    </div>
  );
}

function MarketTile({ label, item, show, visual, small = false, delay = 0 }: {
  label: string; item: MarketItem; show: Tile[2]; visual?: (item: NonNullable<MarketItem>) => ReactNode; small?: boolean; delay?: number;
}) {
  const id = useId();
  const shown = item ? show(item) : { value: null };
  const Title = small ? "h3" : "h2";
  return (
    <section aria-labelledby={id} className="fade-in flex flex-col gap-3 rounded-[18px] border border-borda bg-painel p-5" style={{ animationDelay: `${delay}ms` }}>
      <Title id={id} className="m-0 text-[13px] font-normal text-texto-2">{label}</Title>
      {shown.value === null
        ? <p className={`m-0 text-sm text-texto-2 ${small ? "" : "rounded-xl border border-dashed border-[#2b3247] px-3 py-6 text-center"}`}>Sem dado coletado.</p>
        : <>
            {visual && item && visual(item)}
            <p className={`m-0 font-mono font-semibold leading-tight tracking-tight ${small ? "text-2xl" : "text-[34px]"}`}>{shown.value}</p>
          </>}
      {shown.value !== null && shown.note && <p className="m-0 text-xs leading-relaxed text-[#c9ceda]">{shown.note}</p>}
      {item && <p className="m-0 mt-auto text-xs text-texto-2">{item.source} · {day(item.day)}</p>}
    </section>
  );
}
