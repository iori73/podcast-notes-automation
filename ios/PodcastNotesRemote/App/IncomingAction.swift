import Foundation

/// 外部から URL スキームで流し込まれた指示。
///
///   podcastnotes://submit?url=<Spotify URL>
///   podcastnotes://configure?server=<host:port>&token=<token>
///
/// configure は、長いトークンを iPhone のキーボードで打つ手間をなくすためのもの。
/// Mac 側で `python3 server/app.py --setup-link` を実行すると、この形の URL が出る。
enum IncomingAction: Equatable {
    case submit(spotifyURL: String)
    case configure(server: String, token: String)

    static let scheme = "podcastnotes"

    init?(url: URL) {
        guard url.scheme == Self.scheme,
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else { return nil }

        // podcastnotes://submit → host が "submit"、podcastnotes:///submit → path
        let action = components.host ?? components.path.trimmingCharacters(in: ["/"])
        let items = components.queryItems ?? []
        func value(_ name: String) -> String? {
            items.first { $0.name == name }?.value.flatMap { $0.isEmpty ? nil : $0 }
        }

        switch action {
        case "submit":
            guard let url = value("url") else { return nil }
            self = .submit(spotifyURL: url)
        case "configure":
            guard let server = value("server"), let token = value("token") else { return nil }
            self = .configure(server: server, token: token)
        default:
            return nil
        }
    }
}
