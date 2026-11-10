import { useEffect, useRef } from "react";
import {
  AreaSeries, createChart, LastPriceAnimationMode, LineStyle, type AutoscaleInfoProvider, type IChartApi, type IPriceLine, type ISeriesApi,
} from "lightweight-charts";
import type { CoinDetail } from "@/lib/types";

const TODAY = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }); // AAAA-MM-DD
const UP = ["#34d399", "rgba(52,211,153,0.28)"], DOWN = ["#fb7185", "rgba(251,113,133,0.28)"];
const NEUTRAL = ["#22d3ee", "rgba(34,211,238,0.28)"]; // sem preço médio não há lucro nem prejuízo para colorir

/**
 * Fechamentos diários com a linha tracejada do preço médio de compra.
 * O gráfico é criado uma vez por montagem: troca de moeda ou consulta nova só trocam os dados.
 * `last` é o preço ao vivo e vira o ponto de hoje.
 */
export function PriceChart({ candles, avg, last }: { candles: CoinDetail["candles"]; avg: number | null; last: number }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);
  const avgLine = useRef<IPriceLine | null>(null);
  const avgRef = useRef(avg); // lido pela escala: o preço médio sempre cabe no gráfico

  useEffect(() => {
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const c = createChart(el.current!, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#9aa3b5", fontFamily: "Geist Variable, sans-serif" },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false, scaleMargins: { top: 0.12, bottom: 0.06 } },
      // Sem a trava, a largura que o autoSize mede depois do fitContent deixa a linha só na metade direita.
      timeScale: { visible: false, lockVisibleTimeRangeOnResize: true },
      crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
      handleScroll: false, handleScale: false,
    });
    const s = c.addSeries(AreaSeries, {
      lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      lastPriceAnimation: still ? LastPriceAnimationMode.Disabled : LastPriceAnimationMode.Continuous,
      autoscaleInfoProvider: ((base) => {
        const r = base(), p = r?.priceRange, a = avgRef.current;
        if (!r || !p || a === null) return r;
        return { ...r, priceRange: { minValue: Math.min(p.minValue, a), maxValue: Math.max(p.maxValue, a) } };
      }) satisfies AutoscaleInfoProvider,
    });
    avgLine.current = s.createPriceLine({
      // O título da linha só aparece com a escala de preço visível: a legenda em HTML faz esse papel.
      price: 0, color: "#4b5367", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, lineVisible: false,
    });
    chart.current = c;
    series.current = s;
    return () => { chart.current = series.current = avgLine.current = null; c.remove(); };
  }, []);

  useEffect(() => {
    avgRef.current = avg;
    avgLine.current?.applyOptions(avg === null ? { lineVisible: false } : { price: avg, lineVisible: true });
    series.current?.setData(candles.map((k) => ({ time: k.day, value: k.close })));
    chart.current?.timeScale().fitContent();
  }, [candles, avg]);

  useEffect(() => {
    const lastDay = candles.at(-1)?.day;
    if (!lastDay) return;
    const today = TODAY.format(new Date());
    series.current?.update({ time: today > lastDay ? today : lastDay, value: last });
    const [line, top] = avg === null ? NEUTRAL : last >= avg ? UP : DOWN;
    series.current?.applyOptions({ lineColor: line, topColor: top, bottomColor: "rgba(0,0,0,0)" });
  }, [candles, avg, last]);

  return (
    <div className="flex flex-col gap-1">
      <span className={`flex items-center justify-end gap-1.5 text-[11px] text-texto-2 ${avg === null ? "invisible" : ""}`}>
        <span aria-hidden="true" className="w-4 border-t border-dashed border-[#4b5367]" />
        preço médio
      </span>
      <div ref={el} role="img" aria-label={`Preço nos últimos ${candles.length} dias`} className="h-[180px] w-full" />
    </div>
  );
}
