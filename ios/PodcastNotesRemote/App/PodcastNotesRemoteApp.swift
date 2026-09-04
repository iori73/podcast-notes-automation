import SwiftUI

@main
struct PodcastNotesRemoteApp: App {
    @State private var settings = AppSettings.shared
    @State private var jobs = JobsModel()
    /// podcastnotes://submit?url=... で外から流し込まれた URL
    @State private var incomingURL: String?

    var body: some Scene {
        WindowGroup {
            RootView(incomingURL: $incomingURL)
                .environment(settings)
                .environment(jobs)
                .onOpenURL { url in
                    incomingURL = Self.spotifyURL(from: url)
                }
        }
    }

    /// podcastnotes://submit?url=<encoded> から Spotify URL を取り出す。
    static func spotifyURL(from url: URL) -> String? {
        guard url.scheme == "podcastnotes",
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let value = components.queryItems?.first(where: { $0.name == "url" })?.value,
              !value.isEmpty
        else { return nil }
        return value
    }
}
