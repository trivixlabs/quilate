import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// O jsdom não tem canvas: o gráfico vira um objeto vazio nos testes.
vi.mock("lightweight-charts", () => {
  const series = { setData: vi.fn(), update: vi.fn(), applyOptions: vi.fn(), createPriceLine: vi.fn(() => ({ applyOptions: vi.fn() })) };
  const chart = { addSeries: vi.fn(() => series), timeScale: vi.fn(() => ({ fitContent: vi.fn() })), remove: vi.fn() };
  return {
    createChart: vi.fn(() => chart), AreaSeries: {}, LastPriceAnimationMode: { Disabled: 0, Continuous: 1 }, LineStyle: { Dashed: 2 },
  };
});
Object.defineProperty(window, "matchMedia", { value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) });

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});
