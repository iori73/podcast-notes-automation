import Foundation

/// サーバ側 JobStore の 1 レコード。
struct Job: Codable, Identifiable, Hashable {
    enum Kind: String, Codable, Hashable {
        /// Spotify URL からノートを生成する（process_unified.py）
        case episode
        /// 自由文の依頼を claude に投げる
        case ask
    }

    enum Status: String, Codable, Hashable {
        case queued, running, succeeded, failed, cancelled

        var label: String {
            switch self {
            case .queued: "待機中"
            case .running: "処理中"
            case .succeeded: "完了"
            case .failed: "失敗"
            case .cancelled: "中止"
            }
        }

        var isTerminal: Bool {
            switch self {
            case .succeeded, .failed, .cancelled: true
            case .queued, .running: false
            }
        }
    }

    let id: String
    let kind: Kind
    let status: Status
    let createdAt: Date
    let startedAt: Date?
    let finishedAt: Date?
    let title: String?
    let spotifyUrl: String?
    let prompt: String?
    let notionUrl: String?
    let error: String?
    let resultText: String?
    let language: String?
    let llmBackend: String?

    var notionURL: URL? { notionUrl.flatMap(URL.init(string:)) }

    /// 一覧に出す見出し。title が無ければ依頼内容や URL から作る。
    var displayTitle: String {
        if let title, !title.isEmpty { return title }
        if let prompt, !prompt.isEmpty { return prompt }
        if let spotifyUrl, !spotifyUrl.isEmpty { return spotifyUrl }
        return kind == .episode ? "エピソード" : "依頼"
    }

    /// 開始からの経過。実行中は現在時刻まで、終了後は終了時刻まで。
    var elapsed: TimeInterval? {
        guard let startedAt else { return nil }
        return (finishedAt ?? Date()).timeIntervalSince(startedAt)
    }
}

/// 新規ジョブの投入内容。
struct JobRequest: Encodable {
    var kind: Job.Kind?
    var title: String?
    var spotifyUrl: String?
    var prompt: String?
    var language: String?
    var llmBackend: String?
    var noVerify: Bool?
    var noNotion: Bool?
}

struct JobList: Decodable {
    let jobs: [Job]
}

struct JobLogChunk: Decodable {
    let offset: Int
    let nextOffset: Int
    let chunk: String
}

struct CancelResponse: Decodable {
    let cancelled: Bool
    let job: Job?
}
