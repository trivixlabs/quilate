import { expect, test } from "vitest";
import { applyTick } from "./live";

test("tick marca direção e piscada de 700 ms", () => {
  const s = applyTick({ BTC: { price: 100, dir: 0, flashUntil: 0 } }, { symbol: "BTC", price_usd: 101 }, 1000);
  expect(s.BTC).toEqual({ price: 101, dir: 1, flashUntil: 1700 });
});
test("tick de moeda nova não tem direção; preço igual mantém a direção", () => {
  const a = applyTick({}, { symbol: "ETH", price_usd: 5 }, 0);
  expect(a.ETH).toEqual({ price: 5, dir: 0, flashUntil: 0 });
  const b = applyTick({ ETH: { price: 5, dir: -1, flashUntil: 10 } }, { symbol: "ETH", price_usd: 5 }, 99);
  expect(b.ETH).toEqual({ price: 5, dir: -1, flashUntil: 10 });
});
