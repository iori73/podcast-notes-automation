import SwiftUI

struct SettingsView: View {
    @Environment(AppSettings.self) private var settings

    @State private var connectionState: ConnectionState = .unknown

    enum ConnectionState {
        case unknown, checking, ok, failed(String)
    }

    var body: some View {
        @Bindable var settings = settings

        NavigationStack {
            Form {
                Section {
                    TextField("192.168.1.10:8765 または mac.tailnet.ts.net:8765",
                              text: $settings.serverURLString)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)

                    SecureField("トークン", text: $settings.token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button("接続を確認") { checkConnection() }
                        .disabled(settings.serverURL == nil)

                    connectionStatusRow
                } header: {
                    Text("接続先の Mac")
                } footer: {
                    Text("config/config.yaml の remote: に書いたホスト・ポート・トークンと合わせてください。外出先から使うには Tailscale などで Mac に届く必要があります。")
                }

                Section {
                    Picker("言語", selection: $settings.defaultLanguage) {
                        Text("自動判定").tag("")
                        Text("日本語").tag("ja")
                        Text("英語").tag("en")
                    }
                    Picker("要約エンジン", selection: $settings.defaultLLMBackend) {
                        Text("サーバ既定").tag("")
                        Text("Gemini").tag("gemini")
                        Text("LM Studio").tag("lmstudio")
                    }
                    Toggle("検証をスキップ", isOn: $settings.skipVerify)
                } header: {
                    Text("実行オプションの既定値")
                } footer: {
                    Text("検証をスキップすると LLM の呼び出しが 1 回減ります。Gemini の無料枠が厳しいときに。")
                }
            }
            .navigationTitle("設定")
        }
    }

    @ViewBuilder
    private var connectionStatusRow: some View {
        switch connectionState {
        case .unknown:
            EmptyView()
        case .checking:
            HStack {
                ProgressView()
                Text("確認中…").foregroundStyle(.secondary)
            }
        case .ok:
            Label("接続できました", systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .failed(let message):
            Label(message, systemImage: "xmark.circle.fill")
                .foregroundStyle(.red)
                .font(.footnote)
        }
    }

    private func checkConnection() {
        connectionState = .checking
        Task {
            do {
                // health は認証不要なので、まず疎通、続けてトークンを試す
                _ = try await APIClient().health()
                _ = try await APIClient().listJobs(limit: 1)
                connectionState = .ok
            } catch {
                let message = (error as? APIError)?.errorDescription ?? error.localizedDescription
                connectionState = .failed(message)
            }
        }
    }
}
