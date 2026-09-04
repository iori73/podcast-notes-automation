import SwiftUI

/// Spotify URL と追加指示を投げる画面。
///
/// URL だけ → 今のフォーマットのノートを生成
/// URL + 追加指示 → 生成後に追加指示を続けて実行
/// 追加指示だけ → 既存ページなどに対する自由な依頼
struct SubmitView: View {
    @Binding var incomingURL: String?

    @Environment(AppSettings.self) private var settings
    @Environment(JobsModel.self) private var jobs

    @State private var spotifyURL = ""
    @State private var prompt = ""
    @State private var isSubmitting = false
    @State private var submittedJob: Job?
    @State private var errorMessage: String?

    private var trimmedURL: String {
        spotifyURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedPrompt: String {
        prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSubmit: Bool {
        settings.isConfigured && !isSubmitting && (!trimmedURL.isEmpty || !trimmedPrompt.isEmpty)
    }

    var body: some View {
        NavigationStack {
            Form {
                if !settings.isConfigured {
                    Section {
                        Label("設定でサーバの URL とトークンを入力してください。",
                              systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                    }
                }

                Section {
                    TextField("https://open.spotify.com/episode/…", text: $spotifyURL, axis: .vertical)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .lineLimit(1...3)

                    // PasteButton はタップ起点なので、貼り付け許可のバナーが出ない
                    PasteButton(payloadType: String.self) { strings in
                        guard let pasted = strings.first else { return }
                        Task { @MainActor in spotifyURL = pasted }
                    }
                    .labelStyle(.titleAndIcon)
                } header: {
                    Text("Spotify URL")
                } footer: {
                    Text("空のままにすると、下の依頼だけを実行します。")
                }

                Section {
                    TextField(
                        "例: この回で話されているすべての文様や家紋について、ビジュアルのリファレンス画像を Notion のページに入れて",
                        text: $prompt,
                        axis: .vertical
                    )
                    .lineLimit(3...10)
                } header: {
                    Text("追加の依頼（任意）")
                } footer: {
                    Text(promptFooter)
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            if isSubmitting { ProgressView().padding(.trailing, 4) }
                            Text(isSubmitting ? "送信中…" : "実行する")
                        }
                        .frame(maxWidth: .infinity, minHeight: 32)
                    }
                    .disabled(!canSubmit)
                }

                if let submittedJob {
                    Section("送信しました") {
                        NavigationLink(value: submittedJob) {
                            JobRow(job: submittedJob)
                        }
                        Text("処理には数分〜数十分かかります。アプリを閉じても Mac 側で続行します。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Podcast Notes")
            .navigationDestination(for: Job.self) { JobDetailView(job: $0) }
            .alert("送信できませんでした", isPresented: errorBinding) {
                Button("OK", role: .cancel) { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
            .onChange(of: incomingURL) { _, newValue in
                guard let newValue else { return }
                spotifyURL = newValue
                incomingURL = nil
            }
        }
    }

    private var promptFooter: String {
        if trimmedURL.isEmpty {
            "URL が空なので、この依頼だけを Mac 上の Claude Code が実行します。"
        } else {
            "ノート生成が終わったあと、続けてこの依頼を実行します。"
        }
    }

    private var errorBinding: Binding<Bool> {
        Binding(get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })
    }

    private func submit() {
        let request = JobRequest(
            kind: trimmedURL.isEmpty ? .ask : .episode,
            title: nil,
            spotifyUrl: trimmedURL.isEmpty ? nil : trimmedURL,
            prompt: trimmedPrompt.isEmpty ? nil : trimmedPrompt,
            language: settings.defaultLanguage.isEmpty ? nil : settings.defaultLanguage,
            llmBackend: settings.defaultLLMBackend.isEmpty ? nil : settings.defaultLLMBackend,
            noVerify: settings.skipVerify ? true : nil,
            noNotion: nil
        )

        isSubmitting = true
        Task {
            defer { isSubmitting = false }
            do {
                let job = try await jobs.submit(request)
                submittedJob = job
                spotifyURL = ""
                prompt = ""
                jobs.startPolling()
            } catch {
                errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
            }
        }
    }
}
