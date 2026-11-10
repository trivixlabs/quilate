import { expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { render } from "@/test/render";
import { mockApi, SEED } from "@/test/fixtures";
import { Analista } from "./Analista";

test("aprovar regra do manual", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Analista />, { api });
  const rules = await screen.findByRole("list", { name: "Regras do manual" });
  const rule = within(rules).getByText("Sair após 8 fechamentos semanais abaixo da média de 50 semanas.").closest("li")!;
  expect(screen.getByText("2 de 4 regras aprovadas")).toBeInTheDocument();

  fireEvent.click(within(rule).getByRole("button", { name: "Aprovar" }));

  await waitFor(() => expect(within(rule).queryByRole("button", { name: "Aprovar" })).toBeNull());
  expect(within(rule).getByText("Aprovada")).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith("/api/playbook/rules/3/approve", expect.objectContaining({ method: "POST" }));
  expect(screen.getByText("3 de 4 regras aprovadas")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Regras aprovadas" })).toHaveAttribute("aria-valuenow", "3");
});

test("regras pendentes vêm primeiro", async () => {
  render(<Analista />, { api: mockApi(SEED) });
  const rules = await screen.findByRole("list", { name: "Regras do manual" });
  const items = within(rules).getAllByRole("listitem").filter((li) => li.parentElement === rules);
  expect(within(items[0]).getByRole("button", { name: "Aprovar" })).toBeInTheDocument();
  expect(within(items[3]).getByText("Aprovada")).toBeInTheDocument();
});

test("título usa o termo genérico sem nome configurado", async () => {
  render(<Analista />, { api: mockApi(SEED) });
  expect(await screen.findByRole("heading", { level: 1, name: "Manual do analista" })).toBeInTheDocument();
});

test("título usa o nome de exibição do analista", async () => {
  render(<Analista />, { api: mockApi({ ...SEED, overview: { ...SEED.overview, analyst_name: "Ana" } }) });
  expect(await screen.findByRole("heading", { level: 1, name: "Manual de Ana" })).toBeInTheDocument();
});

test("manual em Markdown vira títulos e lista", async () => {
  render(<Analista />, { api: mockApi(SEED) });
  const manual = await screen.findByRole("region", { name: "Manual das estratégias do analista" });
  expect(within(manual).getByRole("heading", { name: "Entrada e saída" })).toBeInTheDocument();
  expect(within(manual).getAllByRole("listitem")).toHaveLength(2);
  expect(within(manual).getByText("Sempre").tagName).toBe("STRONG");
});

test("fonte da regra abre o trecho e o link da live", async () => {
  render(<Analista />, { api: mockApi(SEED) });
  const rules = await screen.findByRole("list", { name: "Regras do manual" });
  const source = within(rules).getByRole("button", { name: "25/09 · live no YouTube, minuto 55" });
  expect(source).toHaveAttribute("aria-expanded", "false");

  fireEvent.click(source);

  expect(source).toHaveAttribute("aria-expanded", "true");
  expect(within(rules).getByText(/vendo um quinto da posição/)).toBeInTheDocument();
  expect(within(rules).getByRole("link", { name: "Abrir a live no minuto 55" }))
    .toHaveAttribute("href", "https://www.youtube.com/watch?v=demo190&t=3300s");
});

test("linha do tempo do tópico e fila de lives", async () => {
  render(<Analista />, { api: mockApi(SEED) });
  const timeline = await screen.findByRole("region", { name: "Análises no tópico MARKET UPDATES" });
  const items = within(timeline).getAllByRole("listitem");
  expect(items).toHaveLength(4);
  expect(items[0]).toHaveTextContent("04/11, 07:31 · texto");
  expect(items[0]).toHaveTextContent("Fechamento semanal do BTC acima da média de 50 semanas");

  const lives = screen.getByRole("region", { name: "Fila de lives" });
  const counts = within(lives).getByRole("list", { name: "Lives por status" });
  expect(within(counts).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Pendente3", "Transcrito9", "Erro1"]);
  expect(within(lives).getByRole("link", { name: "https://www.youtube.com/watch?v=demo201" }).closest("li")).toHaveTextContent("erro");
});

test("sem tópico de gatilho a linha do tempo pede a configuração", async () => {
  render(<Analista />, { api: mockApi({ ...SEED, playbook: { ...SEED.playbook, trigger_topic_name: null, timeline: [] } }) });
  const timeline = await screen.findByRole("region", { name: "Análises no tópico do gatilho" });
  expect(within(timeline).getByText("Nenhuma análise para mostrar. Confira trigger_topic e o nome do tópico em [group_topics] no config.local.toml.")).toBeInTheDocument();
  expect(within(timeline).queryAllByRole("listitem")).toHaveLength(0);
});

test("tópico de gatilho sem nome mostra a lista sem o aviso", async () => {
  render(<Analista />, { api: mockApi({ ...SEED, playbook: { ...SEED.playbook, trigger_topic_name: null } }) });
  const timeline = await screen.findByRole("region", { name: "Análises no tópico do gatilho" });
  expect(within(timeline).getAllByRole("listitem")).toHaveLength(4);
  expect(within(timeline).queryByText(/Confira trigger_topic/)).toBeNull();
});

test("sem manual gerado", async () => {
  render(<Analista />, { api: mockApi({ ...SEED, playbook: { ...SEED.playbook, version_id: null, markdown: "", rules: [] } }) });
  expect(await screen.findByText("O manual do analista ainda não foi gerado.")).toBeInTheDocument();
});
