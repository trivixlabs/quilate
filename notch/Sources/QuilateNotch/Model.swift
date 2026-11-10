import SwiftUI

// Formato do JSON do backend Quilate (backend/quilate/api/app.py).
// Só os campos que o painel usa; o resto do JSON é ignorado na decodificação.

enum Verdict: String, Decodable, CaseIterable, Sendable {
    // Ordem do pior para o melhor: é a ordem da lista e do ciclo fechado.
    case sair = "Sair", reduzir = "Reduzir", manter = "Manter"

    // Ícone diferente por veredito: a cor sozinha não basta.
    var symbol: String {
        switch self {
        case .manter: "checkmark.circle.fill"
        case .reduzir: "arrow.down.right.circle.fill"
        case .sair: "xmark.octagon.fill"
        }
    }

    var color: Color {
        switch self {
        case .manter: .green
        case .reduzir: .orange
        case .sair: .red
        }
    }
}

struct Card: Decodable, Identifiable, Sendable {
    let symbol: String
    let name: String
    let priceUsd: Double
    let change24h: Double?   // fração; null sem fechamento de ontem
    let valueUsd: Double
    let pnlUsd: Double?      // null quando o custo é desconhecido
    let verdict: Verdict

    var id: String { symbol }

    enum CodingKeys: String, CodingKey {
        case symbol, name, verdict
        case priceUsd = "price_usd", change24h = "change_24h", valueUsd = "value_usd", pnlUsd = "pnl_usd"
    }
}

struct Overview: Decodable, Sendable {
    let totalUsd: Double
    let totalBrl: Double?    // null sem câmbio no snapshot
    let investedUsd: Double
    let pnlUsd: Double
    let pnlPct: Double?      // fração
    let budgetState: String
    let lastCycleUtc: String?
    let history: [HistoryPoint]?  // patrimônio dos últimos 30 dias, um ponto por dia

    enum CodingKeys: String, CodingKey {
        case totalUsd = "total_usd", totalBrl = "total_brl", investedUsd = "invested_usd"
        case pnlUsd = "pnl_usd", pnlPct = "pnl_pct", budgetState = "budget_state", lastCycleUtc = "last_cycle_utc"
        case history
    }
}

struct HistoryPoint: Decodable, Sendable {
    let ts: String  // AAAA-MM-DD
    let usd: Double
}

struct Verdicts: Decodable, Sendable {
    let day: String
    let groups: [String: [Card]]

    // Pior veredito primeiro; dentro do grupo o backend já ordena por valor.
    var cards: [Card] { Verdict.allCases.flatMap { groups[$0.rawValue] ?? [] } }
}

struct Costs: Decodable, Sendable {
    let spentMonthUsd: Double
    let budgetUsd: Double
    let budgetState: String

    enum CodingKeys: String, CodingKey {
        case spentMonthUsd = "spent_month_usd", budgetUsd = "budget_usd", budgetState = "budget_state"
    }
}

// Estado da IA vindo de `budget_state` (backend/quilate/budget.py).
enum AIState: String, Sendable {
    case ok, alerta, bloqueado

    var label: String {
        switch self {
        case .ok: "IA ok"
        case .alerta: "IA em alerta"
        case .bloqueado: "IA bloqueada"
        }
    }

    var symbol: String {
        switch self {
        case .ok: "brain"
        case .alerta: "exclamationmark.triangle.fill"
        case .bloqueado: "nosign"
        }
    }

    var color: Color {
        switch self {
        case .ok: .secondary
        case .alerta: .orange
        case .bloqueado: .red
        }
    }
}

func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
    try JSONDecoder().decode(type, from: data)
}

// MARK: Formatação em pt-BR

// Computada de propósito: global armazenada em módulo executável fica nula dentro do `swift test`.
nonisolated var ptBR: Locale { Locale(identifier: "pt_BR") }

func money(_ value: Double, _ code: String, sign: Bool = false) -> String {
    // Moeda barata (ex.: US$ 0,0000094) precisa de mais casas.
    var style = FloatingPointFormatStyle<Double>.Currency(code: code, locale: ptBR)
        .precision(.fractionLength(value.magnitude < 1 && value != 0 ? 2...8 : 2...2))
    if sign { style = style.sign(strategy: .always()) }
    return value.formatted(style)
}

func pct(_ fraction: Double, sign: Bool = true) -> String {
    fraction.formatted(.percent.precision(.fractionLength(2))
        .sign(strategy: sign ? .always() : .automatic).locale(ptBR))
}

func gainColor(_ value: Double) -> Color {
    value > 0 ? .green : value < 0 ? .red : .secondary
}

// Resultado do dia em US$ a partir da variação de 24 h de cada moeda. Moeda sem variação fica de fora.
func dayResult(_ cards: [Card]) -> (usd: Double, pct: Double?) {
    var usd = 0.0, base = 0.0
    for c in cards {
        guard let ch = c.change24h, ch > -1 else { continue }
        let before = c.valueUsd / (1 + ch)
        usd += c.valueUsd - before
        base += before
    }
    return (usd, base > 0 ? usd / base : nil)
}

// Pontos da linha do gráfico na caixa width × height. y cresce para baixo, como na tela.
// Série plana fica no meio da altura. Menos de dois pontos não vira linha.
func sparkline(_ values: [Double], width: Double, height: Double) -> [CGPoint] {
    guard values.count > 1, let lo = values.min(), let hi = values.max() else { return [] }
    let step = width / Double(values.count - 1)
    return values.enumerated().map { i, v in
        CGPoint(x: Double(i) * step, y: hi == lo ? height / 2 : height * (1 - (v - lo) / (hi - lo)))
    }
}

// Tom das moedas que todo mundo reconhece pela cor; as outras saem do símbolo. A mesma regra do dashboard (hue em VerdictCard.tsx).
private let knownHues: [String: Double] = ["BTC": 30, "ETH": 228, "SOL": 272, "BNB": 45, "XRP": 200, "USDT": 160, "USDC": 212]

func coinHue(_ symbol: String) -> Double {
    if let h = knownHues[symbol] { return h }
    let h = symbol.unicodeScalars.reduce(UInt32(7)) { $0 &* 31 &+ $1.value }
    return Double((h &* 2654435761) % 360)
}

func coinColor(_ symbol: String) -> Color {
    Color(hue: coinHue(symbol) / 360, saturation: 0.55, brightness: 0.7)
}
