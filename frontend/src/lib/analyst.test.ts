import { expect, test } from "vitest";
import { mention, of, subject } from "./analyst";

test("sem nome usa o termo genérico", () => {
  expect(subject("")).toBe("O analista");
  expect(mention("  ")).toBe("o analista");
  expect(of(undefined)).toBe("do analista");
});
test("com nome usa o nome", () => {
  expect(subject(" Ana ")).toBe("Ana");
  expect(mention("Ana")).toBe("Ana");
  expect(of("Ana")).toBe("de Ana");
});
