import { BrowserRouter, Route, Routes } from "react-router";
import { LiveProvider } from "@/lib/live";
import { AppShell } from "@/components/AppShell";
import { Carteira } from "@/pages/Carteira";
import { Analista } from "@/pages/Analista";
import { Configuracao } from "@/pages/Configuracao";
import { Historico } from "@/pages/Historico";
import { Mercado } from "@/pages/Mercado";
import { Moeda } from "@/pages/Moeda";
import { Vereditos } from "@/pages/Vereditos";

export function App() {
  return (
    <BrowserRouter>
      <LiveProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Vereditos />} />
            <Route path="moeda/:symbol" element={<Moeda />} />
            <Route path="carteira" element={<Carteira />} />
            <Route path="analista" element={<Analista />} />
            <Route path="mercado" element={<Mercado />} />
            <Route path="historico" element={<Historico />} />
            <Route path="configuracao" element={<Configuracao />} />
          </Route>
        </Routes>
      </LiveProvider>
    </BrowserRouter>
  );
}
