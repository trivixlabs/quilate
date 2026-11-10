import Foundation
import Testing
@testable import QuilateNotch

// Exemplos gravados no formato real de backend/quilate/api/app.py.
private func fixture(_ name: String) throws -> Data {
    let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "Fixtures/\(name)")
    return try Data(contentsOf: url)
}

@Test func decodificaOverview() throws {
    let o = try decode(Overview.self, from: fixture("overview.json"))
    #expect(o.totalUsd == 59877.2)
    #expect(o.totalBrl == 329324.6)
    #expect(o.pnlUsd == 7293.2)
    #expect(o.pnlPct.map { abs($0 - 0.143) < 0.001 } == true)
    #expect(o.budgetState == "ok")
    #expect(o.lastCycleUtc == "2026-11-04T09:00:12+00:00")
}

@Test func decodificaVerdictsDoPiorParaOMelhor() throws {
    let v = try decode(Verdicts.self, from: fixture("verdicts.json"))
    #expect(v.day == "2026-11-04")
    #expect(v.cards.map(\.symbol) == ["ARB", "LINK", "BTC", "ETH"])
    #expect(v.cards.map(\.verdict) == [.sair, .reduzir, .manter, .manter])
    let btc = v.cards[2]
    #expect(btc.priceUsd == 101250)
    #expect(btc.change24h == 0.018)
    #expect(btc.pnlUsd == 13797)
    // ETH sem custo e sem fechamento de ontem.
    #expect(v.cards[3].pnlUsd == nil)
    #expect(v.cards[3].change24h == nil)
}

@Test func decodificaCosts() throws {
    let c = try decode(Costs.self, from: fixture("costs.json"))
    #expect(c.spentMonthUsd == 8.9)
    #expect(c.budgetUsd == 10)
    #expect(AIState(rawValue: c.budgetState) == .alerta)
}

@Test func dinheiroEmPtBR() {
    #expect(money(59877.2, "USD") == "US$\u{00A0}59.877,20")
    #expect(money(329324.6, "BRL") == "R$\u{00A0}329.324,60")
    #expect(money(0.0000094, "USD") == "US$\u{00A0}0,0000094")
    #expect(money(1295.8, "USD", sign: true) == "+US$\u{00A0}1.295,80")
    #expect(money(-1295.8, "USD", sign: true) == "-US$\u{00A0}1.295,80")
}

@Test func porcentagemEmPtBR() {
    #expect(pct(0.018) == "+1,80%")
    #expect(pct(-0.034) == "-3,40%")
    #expect(pct(0.034, sign: false) == "3,40%")
    #expect(pct(0) == "+0,00%")
}

@Test func corESimboloPorVeredito() {
    #expect(Verdict.manter.color == .green)
    #expect(Verdict.reduzir.color == .orange)
    #expect(Verdict.sair.color == .red)
    // Três ícones distintos: quem não distingue cor ainda lê o veredito.
    #expect(Set(Verdict.allCases.map(\.symbol)).count == 3)
    #expect(AIState.ok.label == "IA ok")
    #expect(AIState.bloqueado.color == .red)
}

@Test func resultadoDoDiaIgnoraMoedaSemVariacao() {
    let cards = [
        Card(symbol: "A", name: "A", priceUsd: 1, change24h: 0.018, valueUsd: 1018, pnlUsd: nil, verdict: .manter),
        Card(symbol: "B", name: "B", priceUsd: 1, change24h: -0.1, valueUsd: 900, pnlUsd: nil, verdict: .sair),
        Card(symbol: "C", name: "C", priceUsd: 1, change24h: nil, valueUsd: 5000, pnlUsd: nil, verdict: .manter),
    ]
    let r = dayResult(cards)
    #expect(abs(r.usd - (18 - 100)) < 1e-9)
    #expect(r.pct.map { abs($0 - (-82.0 / 2000)) < 1e-9 } == true)
    #expect(dayResult([]).pct == nil)
}

@Test func decodificaHistoricoDoPatrimonio() throws {
    let o = try decode(Overview.self, from: fixture("overview.json"))
    #expect(o.history?.map(\.usd) == [58120.5, 58904.1, 59877.2])
}

@Test func linhaDoGraficoOcupaACaixa() {
    let pts = sparkline([1, 3, 2], width: 100, height: 40)
    #expect(pts == [CGPoint(x: 0, y: 40), CGPoint(x: 50, y: 0), CGPoint(x: 100, y: 20)])
    // série plana fica no meio da altura; um ponto só não vira linha
    #expect(sparkline([5, 5], width: 10, height: 10).allSatisfy { $0.y == 5 })
    #expect(sparkline([7], width: 10, height: 10).isEmpty)
}

@Test func corDaMoedaIgualAoDashboard() {
    // Mesmos tons de hue() em frontend/src/components/VerdictCard.tsx do Quilate.
    #expect(coinHue("BTC") == 30)
    #expect(coinHue("ETH") == 228)
    #expect(coinHue("ARB") == 290)
    #expect(coinHue("PEPE") == 9)
    #expect(coinHue("LINK") == 145)
}
