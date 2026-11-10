import SwiftUI

// Medidas do notch. Em tela sem notch a largura é 0 e o painel vira uma pílula no topo.
struct NotchGeometry {
    var width: CGFloat
    var height: CGFloat

    init(_ screen: NSScreen?) {
        guard let screen else {
            width = 0
            height = 24
            return
        }
        if let left = screen.auxiliaryTopLeftArea, let right = screen.auxiliaryTopRightArea {
            width = screen.frame.width - left.width - right.width
        } else {
            width = 0
        }
        height = max(screen.safeAreaInsets.top, screen.frame.maxY - screen.visibleFrame.maxY, 24)
    }
}

@MainActor @Observable
final class HoverState {
    var inside = false
}

// Janela sem borda no topo da tela, acima da barra de menus, em todas as mesas.
final class NotchPanel: NSPanel {
    private let carteira: Carteira
    private let hover = HoverState()
    private var size = CGSize.zero

    static var screen: NSScreen? { NSScreen.screens.first { $0.safeAreaInsets.top > 0 } ?? NSScreen.main }

    init(carteira: Carteira) {
        self.carteira = carteira
        super.init(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        level = .statusBar
        collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        mount()
        orderFrontRegardless()
        NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification,
                                               object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.mount() }
        }
    }

    // Não rouba o teclado do app em uso.
    override var canBecomeKey: Bool { false }

    private func mount() {
        let view = NotchView(geometry: NotchGeometry(Self.screen), hover: hover,
                             mouseInWindow: { [weak self] in self?.frame.contains(NSEvent.mouseLocation) ?? false },
                             onResize: { [weak self] in self?.resize($0) })
        let host = FirstMouseHost(rootView: AnyView(view.environment(carteira)))
        host.sizingOptions = []
        host.autoresizingMask = [.width, .height]
        let area = TrackingArea()
        area.onHover = { [hover] inside in hover.inside = inside }
        area.addSubview(host)
        contentView = area
        host.frame = area.bounds
    }

    // A janela tem sempre o tamanho do desenho, para não bloquear cliques no que está atrás.
    private func resize(_ new: CGSize) {
        let shrinking = new.width < size.width || new.height < size.height
        size = new
        guard shrinking else { return place() }
        Task {  // espera a animação de fechar antes de encolher a janela
            try? await Task.sleep(for: .milliseconds(450))
            place()
        }
    }

    private func place() {
        guard let screen = Self.screen?.frame else { return }
        setFrame(NSRect(x: screen.midX - size.width / 2, y: screen.maxY - size.height,
                        width: size.width, height: size.height), display: true)
    }
}

// Rastreia o mouse mesmo com o app em segundo plano.
final class TrackingArea: NSView {
    var onHover: (Bool) -> Void = { _ in }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways], owner: self))
    }

    override func mouseEntered(with event: NSEvent) { onHover(true) }
    override func mouseExited(with event: NSEvent) { onHover(false) }
}

// O primeiro clique já vale, sem ativar a janela antes.
final class FirstMouseHost: NSHostingView<AnyView> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

struct NotchView: View {
    @Environment(Carteira.self) private var carteira
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let geometry: NotchGeometry
    let hover: HoverState
    let mouseInWindow: () -> Bool
    let onResize: (CGSize) -> Void

    @State private var expanded = false
    @State private var index = 0

    private let ear: CGFloat = 92       // área de cada lado do notch, fechado
    private let openWidth: CGFloat = 440
    private let maxRows = 10

    private var animation: Animation {
        reduceMotion ? .easeOut(duration: 0.15) : .spring(response: 0.36, dampingFraction: 0.82)
    }

    private var swap: AnyTransition { reduceMotion ? .opacity : .push(from: .bottom) }

    private var shape: UnevenRoundedRectangle {
        let radius: CGFloat = expanded ? 24 : 12
        return UnevenRoundedRectangle(bottomLeadingRadius: radius, bottomTrailingRadius: radius, style: .continuous)
    }

    var body: some View {
        Group {
            if expanded {
                open.transition(.opacity)
            } else {
                closed.transition(.opacity)
            }
        }
        .frame(width: expanded ? max(openWidth, geometry.width + 2 * ear) : geometry.width + 2 * ear, alignment: .top)
        .frame(minHeight: geometry.height, alignment: .top)
        .background(.black)
        .clipShape(shape)
        .overlay {
            // Moeda em Sair: anel rosa girando em volta do painel fechado. Parado com Reduzir Movimento.
            if !expanded, current?.verdict == .sair { SairRing(shape: shape, still: reduceMotion) }
        }
        .contentShape(shape)
        .onTapGesture {
            if !expanded { withAnimation(animation) { expanded = true } }
        }
        .contextMenu {
            Button("Abrir dashboard", action: openDashboard)
            Divider()
            Button("Sair") { NSApp.terminate(nil) }
        }
        .fixedSize()
        .onGeometryChange(for: CGSize.self, of: { $0.size }, action: onResize)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .environment(\.colorScheme, .dark)
        .task(id: hover.inside) {
            // 150 ms para abrir evita abrir sem querer a caminho da barra de menus; 350 ms para fechar.
            try? await Task.sleep(for: .milliseconds(hover.inside ? 150 : 350))
            guard !Task.isCancelled else { return }
            withAnimation(animation) { expanded = hover.inside }
        }
        .task(id: expanded) {
            // Rede de segurança: se o macOS não avisar que o mouse saiu (ex.: aberto por clique), fecha mesmo assim.
            while expanded && !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(500))
                if expanded && !mouseInWindow() {
                    hover.inside = false
                    withAnimation(animation) { expanded = false }
                }
            }
        }
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(4))
                withAnimation(animation) { index &+= 1 }
            }
        }
    }

    // MARK: Fechado: uma moeda por vez, nas "orelhas" ao lado do notch

    private var current: Card? {
        carteira.cards.isEmpty ? nil : carteira.cards[index % carteira.cards.count]
    }

    private var closed: some View {
        let card = current
        return HStack(spacing: 0) {
            ZStack(alignment: .leading) {
                if let card {
                    HStack(spacing: 6) {
                        Monogram(symbol: card.symbol, size: 16)
                        Text(card.symbol)
                            .font(.system(size: 12, weight: .semibold))
                            .lineLimit(1)
                    }
                    .id(card.id)
                    .transition(swap)
                } else {
                    Image(systemName: carteira.offline ? "bolt.slash.fill" : "bitcoinsign.circle")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: ear - 14, alignment: .leading)

            Spacer(minLength: geometry.width)

            ZStack(alignment: .trailing) {
                if let card {
                    // Ícone na cor do veredito; a variação na cor da direção, sempre com seta.
                    HStack(spacing: 4) {
                        Image(systemName: card.verdict.symbol)
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(card.verdict.color)
                        if let change = card.change24h {
                            HStack(spacing: 2) {
                                Arrow(value: change)
                                Text(pct(abs(change), sign: false))
                            }
                            .foregroundStyle(gainColor(change))
                        } else {
                            Text(card.verdict.rawValue).foregroundStyle(card.verdict.color)
                        }
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .monospacedDigit()
                    .id(card.id)
                    .transition(swap)
                } else if carteira.offline {
                    Text("desligada")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: ear - 14, alignment: .trailing)
        }
        .padding(.horizontal, 14)
        .frame(height: geometry.height)
        .foregroundStyle(.white)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(closedLabel)
        .accessibilityHint("Passe o mouse ou clique para ver a carteira")
    }

    private var closedLabel: String {
        guard let card = current else { return carteira.offline ? "Quilate desligado" : "Quilate" }
        let change = card.change24h.map { ", \($0 >= 0 ? "alta" : "queda") de \(pct(abs($0), sign: false)) hoje" } ?? ""
        return "\(card.symbol), \(card.verdict.rawValue)\(change)"
    }

    // MARK: Aberto: patrimônio com gráfico, barra de vereditos e lista

    private var open: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Quilate")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.secondary)
                Spacer(minLength: geometry.width + 16)
                Button(action: openDashboard) {
                    Image(systemName: "arrow.up.forward.square")
                        .font(.system(size: 14, weight: .medium))
                        .frame(width: 30, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Abrir dashboard")
                .accessibilityLabel("Abrir dashboard")
            }
            .frame(height: geometry.height)

            if let overview = carteira.overview {
                summary(overview).rise(0, still: reduceMotion)
                verdictBar.rise(1, still: reduceMotion)
                list
            } else {
                empty
            }
            footer
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 16)
        .foregroundStyle(.white)
    }

    private var empty: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(carteira.offline ? "Quilate desligado" : "Carregando…")
                .font(.system(size: 15, weight: .semibold))
            if carteira.offline {
                Text("Rode `uv run quilate servir` em ~/quilate/backend. Tento de novo a cada 30 s.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func summary(_ overview: Overview) -> some View {
        let day = dayResult(carteira.cards)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Patrimônio")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.secondary)
                    Text(money(overview.totalUsd, "USD"))
                        .font(.system(size: 27, weight: .semibold, design: .monospaced))
                        .contentTransition(.numericText())
                    Text(overview.totalBrl.map { money($0, "BRL") } ?? "R$ sem câmbio")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if let history = overview.history, history.count > 1 {
                    Spark(values: history.map(\.usd), still: reduceMotion)
                        .frame(width: 120, height: 52)
                        .accessibilityLabel("Patrimônio nos últimos \(history.count) dias")
                }
            }
            // Lado a lado quando cabe; um embaixo do outro quando os valores são grandes.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    Chip(label: "Hoje", usd: day.usd, pct: day.pct)
                    Chip(label: "Resultado", usd: overview.pnlUsd, pct: overview.pnlPct)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Chip(label: "Hoje", usd: day.usd, pct: day.pct)
                    Chip(label: "Resultado", usd: overview.pnlUsd, pct: overview.pnlPct)
                }
            }
        }
    }

    // Proporção de moedas em cada veredito: barra e contagem com ícone.
    private var verdictBar: some View {
        let total = max(carteira.cards.count, 1)
        return VStack(spacing: 8) {
            GeometryReader { geo in
                HStack(spacing: 3) {
                    ForEach(Verdict.allCases, id: \.self) { v in
                        let n = carteira.count(v)
                        if n > 0 {
                            Capsule().fill(v.color)
                                .frame(width: max(0, (geo.size.width - 6) * Double(n) / Double(total)))
                        }
                    }
                }
            }
            .frame(height: 6)
            .accessibilityHidden(true)
            HStack {
                ForEach(Verdict.allCases, id: \.self) { v in
                    Label("\(carteira.count(v)) \(v.rawValue)", systemImage: v.symbol)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(v.color)
                    if v != Verdict.allCases.last { Spacer(minLength: 4) }
                }
            }
            .accessibilityElement(children: .combine)
        }
        .padding(12)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var list: some View {
        let rows = Array(carteira.cards.prefix(maxRows))
        let hidden = carteira.cards.count - rows.count
        return VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { i, card in
                Row(card: card).rise(i + 2, still: reduceMotion)
            }
            if hidden > 0 {
                Button("Mais \(hidden) no dashboard", action: openDashboard)
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 6) {
            if carteira.offline {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                Text("Quilate desligado. Tento de novo a cada 30 s.")
            } else if let at = carteira.updatedAt {
                Image(systemName: "arrow.clockwise")
                Text("Atualizado às \(at.formatted(Date.FormatStyle(date: .omitted, time: .shortened, locale: ptBR)))")
            }
            Spacer(minLength: 8)
            if let ai = carteira.aiState {
                Circle().fill(ai == .ok ? Color.green : ai.color).frame(width: 6, height: 6).accessibilityHidden(true)
                Text(carteira.costs.map { "\(ai.label) · \(money($0.spentMonthUsd, "USD")) de \(money($0.budgetUsd, "USD"))" } ?? ai.label)
                    .foregroundStyle(ai == .ok ? .secondary : ai.color)
            }
        }
        .font(.system(size: 10.5))
        .foregroundStyle(.secondary)
        .lineLimit(1)
        .padding(.top, 10)
        .overlay(alignment: .top) { Rectangle().fill(Color.white.opacity(0.07)).frame(height: 1) }
    }
}

extension Color {
    static let violet = Color(red: 0.655, green: 0.545, blue: 0.98)
}

extension View {
    // Entrada escalonada das partes do painel aberto: sobe 8 pt e aparece, 40 ms entre uma e outra.
    func rise(_ index: Int, still: Bool) -> some View { modifier(Rise(index: index, still: still)) }
}

struct Rise: ViewModifier {
    let index: Int
    let still: Bool
    @State private var shown = false

    func body(content: Content) -> some View {
        content
            .opacity(shown || still ? 1 : 0)
            .offset(y: shown || still ? 0 : 8)
            .onAppear {
                guard !still else { return }
                withAnimation(.spring(response: 0.4, dampingFraction: 0.85).delay(0.06 + 0.04 * Double(index))) { shown = true }
            }
    }
}

// Anel cônico girando, recortado na borda do painel.
struct SairRing: View {
    let shape: UnevenRoundedRectangle
    let still: Bool
    @State private var angle = 0.0

    var body: some View {
        // Color.clear dá ao anel o tamanho do painel; o gradiente gira por baixo e a máscara mostra só a borda.
        Color.clear
            .overlay {
                AngularGradient(colors: [.clear, .clear, Color(red: 0.98, green: 0.44, blue: 0.52), .clear], center: .center)
                    .frame(width: 600, height: 600)
                    .rotationEffect(.degrees(angle))
            }
            .mask(shape.stroke(lineWidth: 2))
            .allowsHitTesting(false)
            .accessibilityHidden(true)
            .onAppear {
                guard !still else { return }
                withAnimation(.linear(duration: 3).repeatForever(autoreverses: false)) { angle = 360 }
            }
    }
}

// Linha do patrimônio com área por baixo. A linha se desenha ao abrir o painel.
struct Spark: View {
    let values: [Double]
    let still: Bool
    @State private var drawn = 0.0

    var body: some View {
        GeometryReader { geo in
            let pts = sparkline(values, width: geo.size.width, height: geo.size.height)
            let line = Path { p in p.addLines(pts) }
            let up = (values.last ?? 0) >= (values.first ?? 0)
            ZStack {
                Path { p in
                    p.addLines(pts)
                    p.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height))
                    p.addLine(to: CGPoint(x: 0, y: geo.size.height))
                    p.closeSubpath()
                }
                .fill(LinearGradient(colors: [Color.violet.opacity(0.28), .clear], startPoint: .top, endPoint: .bottom))
                .opacity(drawn)
                line.trim(from: 0, to: drawn)
                    .stroke(up ? Color.violet : Color.red, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            }
        }
        .onAppear {
            if still { drawn = 1 } else { withAnimation(.easeOut(duration: 1.2).delay(0.15)) { drawn = 1 } }
        }
    }
}

// Círculo com a inicial, na cor estável da moeda (a mesma regra do dashboard).
struct Monogram: View {
    let symbol: String
    var size: CGFloat = 26

    var body: some View {
        Text(symbol.prefix(1))
            .font(.system(size: size * 0.5, weight: .bold, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(coinColor(symbol), in: Circle())
            .accessibilityHidden(true)
    }
}

struct Chip: View {
    let label: String
    let usd: Double
    let pct: Double?

    var body: some View {
        HStack(spacing: 4) {
            Arrow(value: usd)
            Text(label)
            Text(pct.map { "\(money(usd, "USD", sign: true)) (\(QuilateNotch.pct($0)))" } ?? money(usd, "USD", sign: true))
                .fontWeight(.semibold)
                .monospacedDigit()
        }
        .font(.system(size: 11))
        .lineLimit(1)
        .fixedSize()
        .foregroundStyle(gainColor(usd))
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(gainColor(usd).opacity(0.13), in: Capsule())
        .accessibilityElement(children: .combine)
    }
}

struct Row: View {
    let card: Card

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: card.verdict.symbol)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(card.verdict.color)
                .frame(width: 26, height: 26)
                .background(card.verdict.color.opacity(0.14), in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text(card.symbol).font(.system(size: 13, weight: .semibold))
                Text(card.verdict.rawValue)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(card.verdict.color)
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 1) {
                Text(money(card.priceUsd, "USD"))
                    .font(.system(size: 12, weight: .medium))
                    .contentTransition(.numericText())
                Text(card.pnlUsd.map { money($0, "USD", sign: true) } ?? "sem custo")
                    .font(.system(size: 11))
                    .foregroundStyle(card.pnlUsd.map(gainColor) ?? .secondary)
            }
            .monospacedDigit()
            Pill(change: card.change24h)
                .frame(width: 72, alignment: .trailing)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(card.symbol), \(card.verdict.rawValue)")
    }
}

struct Arrow: View {
    let value: Double

    var body: some View {
        Image(systemName: value > 0 ? "arrowtriangle.up.fill" : value < 0 ? "arrowtriangle.down.fill" : "minus")
            .font(.system(size: 7, weight: .bold))
            .accessibilityHidden(true)
    }
}

// Variação de 24 h: seta e número além da cor.
struct Pill: View {
    let change: Double?

    var body: some View {
        HStack(spacing: 3) {
            if let change {
                Arrow(value: change)
                Text(pct(abs(change), sign: false))
            } else {
                Text("—")
            }
        }
        .font(.system(size: 11, weight: .semibold))
        .monospacedDigit()
        .foregroundStyle(change.map(gainColor) ?? .secondary)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background((change.map(gainColor) ?? .secondary).opacity(0.16), in: Capsule())
        .accessibilityLabel(change.map { "Variação \(pct($0))" } ?? "Sem variação")
    }
}
