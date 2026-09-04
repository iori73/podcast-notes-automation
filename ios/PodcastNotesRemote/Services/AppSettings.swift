import Foundation
import Observation

/// 接続先とデフォルト実行オプション。トークンは Keychain、それ以外は UserDefaults。
@Observable
final class AppSettings {
    static let shared = AppSettings()

    private enum Key {
        static let serverURL = "serverURL"
        static let language = "defaultLanguage"
        static let llmBackend = "defaultLLMBackend"
        static let skipVerify = "defaultSkipVerify"
    }

    private let defaults: UserDefaults
    private let keychain: KeychainStore

    var serverURLString: String {
        didSet { defaults.set(serverURLString, forKey: Key.serverURL) }
    }

    /// 空文字は「サーバ既定に任せる」。
    var defaultLanguage: String {
        didSet { defaults.set(defaultLanguage, forKey: Key.language) }
    }

    var defaultLLMBackend: String {
        didSet { defaults.set(defaultLLMBackend, forKey: Key.llmBackend) }
    }

    var skipVerify: Bool {
        didSet { defaults.set(skipVerify, forKey: Key.skipVerify) }
    }

    var token: String {
        didSet { keychain.set(token, for: "apiToken") }
    }

    init(defaults: UserDefaults = .standard, keychain: KeychainStore = .init()) {
        self.defaults = defaults
        self.keychain = keychain
        serverURLString = defaults.string(forKey: Key.serverURL) ?? ""
        defaultLanguage = defaults.string(forKey: Key.language) ?? ""
        defaultLLMBackend = defaults.string(forKey: Key.llmBackend) ?? ""
        skipVerify = defaults.bool(forKey: Key.skipVerify)
        token = keychain.get("apiToken") ?? ""
    }

    /// 末尾スラッシュや scheme 省略を吸収して正規化した接続先。
    var serverURL: URL? {
        let trimmed = serverURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let withScheme = trimmed.contains("://") ? trimmed : "http://\(trimmed)"
        guard var components = URLComponents(string: withScheme) else { return nil }
        components.path = components.path.hasSuffix("/")
            ? String(components.path.dropLast())
            : components.path
        return components.url
    }

    var isConfigured: Bool {
        serverURL != nil && !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

/// トークン保存用の最小限の Keychain ラッパー。
struct KeychainStore {
    private let service = "com.iorikawano.podcastnotesremote"

    func set(_ value: String, for account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        guard !value.isEmpty, let data = value.data(using: .utf8) else { return }
        var attributes = query
        attributes[kSecValueData as String] = data
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(attributes as CFDictionary, nil)
    }

    func get(_ account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
