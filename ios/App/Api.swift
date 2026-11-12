import BridgeCore
import Foundation
import UIKit

/// Client for /api/ingest/health on the user's own Compass.
struct Api {
    let baseUrl: String
    let token: String

    init?(_ settings: Settings) {
        guard settings.configured else { return nil }
        baseUrl = settings.serverUrl
        token = settings.token
    }

    struct Status: Decodable {
        let ok: Bool
        let last_success_at: String?
    }

    struct Result: Decodable {
        let received: Int
        let created: Int
        let updated: Int
        let deleted: Int
    }

    enum Failure: LocalizedError {
        case unauthorized
        case ingestOff
        case tooLarge
        case http(Int)
        case badUrl

        var errorDescription: String? {
            switch self {
            case .unauthorized: return String(localized: "The token is not valid (HEALTH_TOKEN on the server).")
            case .ingestOff: return String(localized: "Ingest is not active on the server (HEALTH_TOKEN missing).")
            case .tooLarge: return String(localized: "The server refused a batch as too large.")
            case .http(let code): return String(localized: "The server answered \(code).")
            case .badUrl: return String(localized: "The server address is not valid.")
            }
        }
    }

    /// Token check for "Save and test".
    func status() async throws -> Status {
        let (data, _) = try await request("GET", body: nil)
        return try JSONDecoder().decode(Status.self, from: data)
    }

    func send(_ payload: Payload) async throws -> Result {
        let (data, _) = try await request("POST", body: try payload.json())
        return try JSONDecoder().decode(Result.self, from: data)
    }

    private func request(_ method: String, body: Data?) async throws -> (Data, HTTPURLResponse) {
        guard let url = URL(string: "\(baseUrl)/api/ingest/health") else { throw Failure.badUrl }
        var request = URLRequest(url: url, timeoutInterval: 60)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw Failure.http(0) }
        switch http.statusCode {
        case 200..<300: return (data, http)
        case 401: throw Failure.unauthorized
        case 503: throw Failure.ingestOff
        case 413: throw Failure.tooLarge
        default: throw Failure.http(http.statusCode)
        }
    }

    /// "iPhone, iOS 18.1": the device as the Health tab in Compass shows it.
    @MainActor static var device: String {
        "\(UIDevice.current.model), iOS \(UIDevice.current.systemVersion)"
    }

    static var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    }
}
