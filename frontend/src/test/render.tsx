import type { ReactElement } from "react";
import { render as rtlRender } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { vi } from "vitest";
import { LiveProvider } from "@/lib/live";

/** WebSocket que nunca conecta: a tela fica em "Reconectando…" e sem ticks. */
class SilentWebSocket {
  onopen = null; onmessage = null; onclose = null;
  close() {}
}

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

/** Renderiza com o `fetch` falso, rota em memória e o provedor de preços. */
export function render(ui: ReactElement, { api, route = "/" }: { api: typeof fetch; route?: string }) {
  vi.stubGlobal("fetch", api);
  vi.stubGlobal("WebSocket", SilentWebSocket);
  return rtlRender(
    <MemoryRouter initialEntries={[route]}>
      <LiveProvider>{ui}<Location /></LiveProvider>
    </MemoryRouter>,
  );
}
