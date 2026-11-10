import Foundation
import Observation

// Cliente de leitura do backend local. Só GET, só 127.0.0.1, nenhum segredo.
struct Backend: Sendable {
    nonisolated static var base: URL { URL(string: "http://127.0.0.1:8000")! }

    private let session: URLSession

    init() {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 5
        config.timeoutIntervalForResource = 5
        config.urlCache = nil
        session = URLSession(configuration: config)
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        let (data, response) = try await session.data(from: Self.base.appending(path: path))
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
        return try decode(type, from: data)
    }
}

// Estado que o painel observa. Backend fora do ar: `offline` liga e o último dado fica na tela.
@MainActor @Observable
final class Carteira {
    var overview: Overview?
    var cards: [Card] = []
    var costs: Costs?
    var updatedAt: Date?
    var offline = false

    private let backend = Backend()

    var aiState: AIState? {
        (costs?.budgetState ?? overview?.budgetState).flatMap(AIState.init(rawValue:))
    }

    func count(_ verdict: Verdict) -> Int {
        cards.count { $0.verdict == verdict }
    }

    // `/api/overview` e `/api/verdicts` juntos: totais e cartões da mesma leitura.
    func refresh() async {
        do {
            async let o = backend.get("/api/overview", as: Overview.self)
            async let v = backend.get("/api/verdicts", as: Verdicts.self)
            let (overview, verdicts) = try await (o, v)
            self.overview = overview
            cards = verdicts.cards
            updatedAt = .now
            offline = false
            if costs == nil { await refreshCosts() }  // backend subiu depois do app: estado da IA já na primeira leitura
        } catch {
            offline = true
        }
    }

    func refreshCosts() async {
        costs = try? await backend.get("/api/costs", as: Costs.self)
    }
}
