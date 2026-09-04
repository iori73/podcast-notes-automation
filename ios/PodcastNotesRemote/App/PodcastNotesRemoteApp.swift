import SwiftUI

@main
struct PodcastNotesRemoteApp: App {
    @State private var settings = AppSettings.shared
    @State private var jobs = JobsModel()
    /// URL スキームで外から流し込まれた URL（SubmitView が消費する）
    @State private var incomingURL: String?
    @State private var configuredMessage: String?

    var body: some Scene {
        WindowGroup {
            RootView(incomingURL: $incomingURL)
                .environment(settings)
                .environment(jobs)
                .onOpenURL(perform: handle)
                .alert("接続設定を読み込みました", isPresented: configuredBinding) {
                    Button("OK", role: .cancel) { configuredMessage = nil }
                } message: {
                    Text(configuredMessage ?? "")
                }
        }
    }

    private var configuredBinding: Binding<Bool> {
        Binding(get: { configuredMessage != nil }, set: { if !$0 { configuredMessage = nil } })
    }

    private func handle(_ url: URL) {
        switch IncomingAction(url: url) {
        case .submit(let spotifyURL):
            incomingURL = spotifyURL
        case .configure(let server, let token):
            settings.serverURLString = server
            settings.token = token
            configuredMessage = "接続先: \(server)"
            jobs.startPolling()
        case nil:
            break
        }
    }
}
