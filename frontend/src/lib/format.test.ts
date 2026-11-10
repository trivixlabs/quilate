import { expect, test } from "vitest";
import { pct, usd } from "./format";

test("usd por magnitude", () => {
  expect(usd(101250)).toBe("US$ 101.250");
  expect(usd(15.62)).toBe("US$ 15,62");
  expect(usd(0.41)).toBe("US$ 0,4100");
  expect(usd(0.0000094)).toBe("US$ 0,0000094");
  expect(usd(0)).toBe("US$ 0,00");  // gasto zerado no mês, não "0,0000000"
});
test("pct com sinal", () => {
  expect(pct(-3.4)).toBe("−3,40%");
  expect(pct(2)).toBe("+2,00%");
});
