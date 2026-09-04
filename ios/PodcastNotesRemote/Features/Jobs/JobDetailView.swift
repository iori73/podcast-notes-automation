import SwiftUI

struct JobDetailView: View {
    @State private var model: JobDetailModel
    @State private var showLog = false
    @Environment(JobsModel.self) private var jobs

    init(job: Job) {
        _model = State(initialValue: JobDetailModel(job: job))
    }

    private var job: Job { model.job }

    var body: some View {
        List {
            Section {
                LabeledContent("状態") {
                    StatusBadge(status: job.status)
                }
                if let elapsed = job.elapsed {
                    LabeledContent("経過", value: Self.durationText(elapsed))
                }
                LabeledContent("受付", value: job.createdAt.formatted(date: .abbreviated, time: .shortened))
            }

            if let url = job.notionURL {
                Section("Notion") {
                    Link(destination: url) {
                        Label("ページを開く", systemImage: "arrow.up.forward.square")
                    }
                }
            }

            if let spotify = job.spotifyUrl, let url = URL(string: spotify) {
                Section("エピソード") {
                    Link(destination: url) {
                        Label(spotify, systemImage: "music.note")
                            .lineLimit(2)
                    }
                }
            }

            if let prompt = job.prompt, !prompt.isEmpty {
                Section("依頼内容") {
                    Text(prompt)
                }
            }

            if let error = job.error, !error.isEmpty {
                Section("エラー") {
                    Text(error)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(.red)
                }
            }

            Section {
                DisclosureGroup("ログ", isExpanded: $showLog) {
                    if model.log.isEmpty {
                        Text("まだ出力はありません")
                            .foregroundStyle(.secondary)
                            .font(.footnote)
                    } else {
                        // 末尾が知りたいので新しい方から見せる
                        Text(Self.tail(model.log))
                            .font(.system(.caption2, design: .monospaced))
                            .textSelection(.enabled)
                    }
                }
            }

            if !job.status.isTerminal {
                Section {
                    Button("このジョブを中止", role: .destructive) {
                        Task {
                            await model.cancelJob()
                            await jobs.refresh()
                        }
                    }
                }
            }
        }
        .navigationTitle(job.kind == .episode ? "ノート生成" : "依頼")
        .navigationBarTitleDisplayMode(.inline)
        .task { model.start() }
        .onDisappear { model.stop() }
    }

    /// ログ全文はモバイルでは長すぎるので末尾だけ出す。
    private static func tail(_ text: String, limit: Int = 6_000) -> String {
        text.count <= limit ? text : "…（省略）\n" + String(text.suffix(limit))
    }

    private static func durationText(_ seconds: TimeInterval) -> String {
        let total = Int(seconds)
        let minutes = total / 60
        return minutes < 1 ? "\(total) 秒" : "\(minutes) 分 \(total % 60) 秒"
    }
}
