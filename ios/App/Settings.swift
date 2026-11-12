import Foundation
import HealthKit
import Security

/// What the app keeps: server and token (the token in the keychain), how far back the first sync
/// reads, the HealthKit anchors per type and the result of the last run.
final class Settings {
    static let shared = Settings()

    private let defaults = UserDefaults.standard

    /// "https://compass.example" without a trailing slash or /api, as typed into the app.
    var serverUrl: String {
        get { defaults.string(forKey: "serverUrl") ?? "" }
        set {
            var url = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
            while url.hasSuffix("/") { url.removeLast() }
            if url.hasSuffix("/api") { url.removeLast(4) }
            defaults.set(url, forKey: "serverUrl")
        }
    }

    var token: String {
        get { Keychain.read() ?? "" }
        set { Keychain.write(newValue.trimmingCharacters(in: .whitespacesAndNewlines)) }
    }

    var configured: Bool { URL(string: serverUrl)?.scheme != nil && !token.isEmpty }

    /// Days the first sync (and "Read again") reads.
    var initialDays: Int {
        get { defaults.object(forKey: "initialDays") as? Int ?? 30 }
        set { defaults.set(newValue, forKey: "initialDays") }
    }

    /// Start of the range the anchored queries cover, fixed at the first sync: the anchors only
    /// make sense together with the same predicate.
    var since: Date? {
        get { defaults.object(forKey: "since") as? Date }
        set { defaults.set(newValue, forKey: "since") }
    }

    /// Whether the sleep of the whole range was sent once; afterwards only the last days are.
    var sleepRead: Bool {
        get { defaults.bool(forKey: "sleepRead") }
        set { defaults.set(newValue, forKey: "sleepRead") }
    }

    func anchor(_ key: String) -> HKQueryAnchor? {
        guard let data = defaults.data(forKey: "anchor.\(key)") else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    func setAnchor(_ anchor: HKQueryAnchor, _ key: String) {
        let data = try? NSKeyedArchiver.archivedData(withRootObject: anchor, requiringSecureCoding: true)
        defaults.set(data, forKey: "anchor.\(key)")
    }

    /// Forget how far the app got: the next sync reads the whole range again. The server import is
    /// idempotent, so nothing is stored twice.
    func resetSync() {
        for key in defaults.dictionaryRepresentation().keys where key.hasPrefix("anchor.") {
            defaults.removeObject(forKey: key)
        }
        since = nil
        sleepRead = false
    }

    var lastSyncAt: Date? {
        get { defaults.object(forKey: "lastSyncAt") as? Date }
        set { defaults.set(newValue, forKey: "lastSyncAt") }
    }

    var lastResult: String? {
        get { defaults.string(forKey: "lastResult") }
        set { defaults.set(newValue, forKey: "lastResult") }
    }

    var lastError: String? {
        get { defaults.string(forKey: "lastError") }
        set { defaults.set(newValue, forKey: "lastError") }
    }
}

/// The token in the keychain, readable after the first unlock so background syncs can use it.
enum Keychain {
    private static let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "com.raudev.compass.bridge",
        kSecAttrAccount as String: "token",
    ]

    static func read() -> String? {
        var item: CFTypeRef?
        var search = query
        search[kSecReturnData as String] = true
        search[kSecMatchLimit as String] = kSecMatchLimitOne
        guard SecItemCopyMatching(search as CFDictionary, &item) == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    static func write(_ value: String) {
        SecItemDelete(query as CFDictionary)
        guard !value.isEmpty else { return }
        var item = query
        item[kSecValueData as String] = Data(value.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(item as CFDictionary, nil)
    }
}
