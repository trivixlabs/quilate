import SwiftUI

@main
struct QuilateNotchApp: App {
    @NSApplicationDelegateAdaptor private var delegate: AppDelegate

    // O notch é uma janela do AppKit; esta cena vazia só satisfaz o SwiftUI.
    var body: some Scene {
        Settings { EmptyView() }
            .commands { CommandGroup(replacing: .appSettings) {} }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let carteira = Carteira()
    private var notch: NotchPanel?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)  // sem ícone no Dock
        notch = NotchPanel(carteira: carteira)
        Task {
            while true {
                await carteira.refresh()
                try? await Task.sleep(for: .seconds(30))
            }
        }
        Task {
            while true {
                await carteira.refreshCosts()
                try? await Task.sleep(for: .seconds(300))
            }
        }
    }
}

@MainActor
func openDashboard() {
    NSWorkspace.shared.open(Backend.base)
}
