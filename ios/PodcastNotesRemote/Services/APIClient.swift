import Foundation

enum APIError: LocalizedError {
    case notConfigured
    case unauthorized
    case server(String)
    case transport(Error)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            "設定でサーバの URL とトークンを入力してください。"
        case .unauthorized:
            "トークンが正しくありません。設定を確認してください。"
        case .server(let message):
            message
        case .transport:
            "Mac に接続できません。サーバが起動しているか、同じネットワーク（または Tailscale）に繋がっているか確認してください。"
        case .decoding:
            "サーバの応答を解釈できませんでした。"
        }
    }
}

/// ジョブサーバとの通信。
struct APIClient {
    private let settings: AppSettings
    private let session: URLSession

    init(settings: AppSettings = .shared) {
        self.settings = settings
        let configuration = URLSessionConfiguration.default
        // Whisper の実行を待つのはポーリング側なので、1 リクエストは短めに切る
        configuration.timeoutIntervalForRequest = 20
        configuration.waitsForConnectivity = false
        self.session = URLSession(configuration: configuration)
    }

    // MARK: - エンドポイント

    func health() async throws -> Bool {
        struct Health: Decodable { let ok: Bool }
        return try await send(path: "/v1/health", method: "GET", authorized: false, as: Health.self).ok
    }

    func listJobs(limit: Int = 50) async throws -> [Job] {
        try await send(path: "/v1/jobs?limit=\(limit)", method: "GET", as: JobList.self).jobs
    }

    func job(id: String) async throws -> Job {
        try await send(path: "/v1/jobs/\(id)", method: "GET", as: Job.self)
    }

    func log(id: String, offset: Int) async throws -> JobLogChunk {
        try await send(path: "/v1/jobs/\(id)/log?offset=\(offset)", method: "GET", as: JobLogChunk.self)
    }

    @discardableResult
    func cancel(id: String) async throws -> Bool {
        try await send(path: "/v1/jobs/\(id)/cancel", method: "POST", as: CancelResponse.self).cancelled
    }

    func submit(_ request: JobRequest) async throws -> Job {
        let body = try JSONCoding.encoder.encode(request)
        return try await send(path: "/v1/jobs", method: "POST", body: body, as: Job.self)
    }

    // MARK: - 共通処理

    private func send<T: Decodable>(
        path: String,
        method: String,
        body: Data? = nil,
        authorized: Bool = true,
        as type: T.Type
    ) async throws -> T {
        guard let base = settings.serverURL else { throw APIError.notConfigured }
        if authorized, settings.token.isEmpty { throw APIError.notConfigured }
        guard let url = URL(string: base.absoluteString + path) else { throw APIError.notConfigured }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        if body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if authorized {
            request.setValue("Bearer \(settings.token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport(error)
        }

        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            if status == 401 { throw APIError.unauthorized }
            throw APIError.server(Self.errorMessage(from: data) ?? "サーバエラー（HTTP \(status)）")
        }

        do {
            return try JSONCoding.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private static func errorMessage(from data: Data) -> String? {
        struct ErrorBody: Decodable { let error: String }
        return try? JSONDecoder().decode(ErrorBody.self, from: data).error
    }
}
