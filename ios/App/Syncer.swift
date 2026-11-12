import BridgeCore
import Foundation
import HealthKit

/// One sync run: read what changed in Apple Health since the last run and post it to Compass.
///
/// Each type has its own HKQueryAnchor. The first run (and every run after "Read again") reads the
/// last `Settings.initialDays` days; later runs only get what was added or deleted since. An anchor
/// moves on only after the server accepted the batch, and the import is idempotent, so a run that
/// breaks off just sends some records again next time.
///
/// Sleep is the exception: HealthKit stores one sample per phase, Compass a night. Every run reads
/// the phases of the last `sleepDays` days again, groups them into nights and sends them with a
/// snapshot, so a night that changed or was deleted arrives as such.
actor Syncer {
    static let shared = Syncer()

    static let limit = 2000
    static let sleepDays = 3

    private var running: Task<String, Error>?

    /// Runs a sync, or waits for the one already running (the observer queries of several types
    /// fire at once).
    func sync() async throws -> String {
        if let running { return try await running.value }
        let task = Task { try await run() }
        running = task
        defer { running = nil }
        do {
            let result = try await task.value
            record(result: result, error: nil)
            return result
        } catch {
            record(result: nil, error: Self.describe(error))
            throw error
        }
    }

    private func record(result: String?, error: String?) {
        let settings = Settings.shared
        if let result {
            settings.lastResult = result
            settings.lastSyncAt = Date()
        }
        settings.lastError = error
    }

    static func describe(_ error: Error) -> String {
        if let error = error as? HKError, error.code == .errorDatabaseInaccessible {
            // Apple Health is encrypted while the phone is locked.
            return String(localized: "Apple Health is locked until the phone is unlocked; the next sync catches up.")
        }
        return error.localizedDescription
    }

    private func run() async throws -> String {
        let settings = Settings.shared
        guard let api = Api(settings) else {
            throw SyncError.notConfigured
        }
        guard HealthReader.available else { throw SyncError.noHealthData }
        let device = await Api.device
        let since = settings.since ?? Date(timeIntervalSinceNow: -Double(settings.initialDays) * 86400)
        settings.since = since

        var sent = 0
        var deleted = 0
        func send(_ changes: HealthReader.Changes) async throws {
            guard !changes.records.isEmpty || !changes.deleted.isEmpty else { return }
            let payload = Payload(device: device, appVersion: Api.appVersion, records: changes.records, deleted: changes.deleted)
            _ = try await api.send(payload)
            sent += changes.records.count
            deleted += changes.deleted.count
        }

        for kind in QuantityKind.allCases {
            var anchor = settings.anchor(kind.rawValue)
            while true {
                try Task.checkCancellation()
                let changes = try await HealthReader.changes(kind, since: since, anchor: anchor, limit: Self.limit)
                try await send(changes)
                settings.setAnchor(changes.anchor, kind.rawValue)
                anchor = changes.anchor
                if changes.count < Self.limit { break }
            }
        }

        var anchor = settings.anchor("workout")
        while true {
            try Task.checkCancellation()
            let changes = try await HealthReader.workoutChanges(since: since, anchor: anchor, limit: Self.limit)
            try await send(changes)
            settings.setAnchor(changes.anchor, "workout")
            anchor = changes.anchor
            if changes.count < Self.limit { break }
        }

        // Noon, so the window never cuts a night in two.
        let recent = Calendar.current.date(byAdding: .day, value: -Self.sleepDays, to: Date()) ?? since
        let windowDay = settings.sleepRead ? max(recent, since) : since
        let window = Calendar.current.date(bySettingHour: 12, minute: 0, second: 0, of: windowDay) ?? windowDay
        let nights = try await HealthReader.nights(since: window)
        let snapshot = Snapshot(type: "sleep", since: window, ids: nights.map(\.id), prefix: RecordId.nightPrefix)
        _ = try await api.send(Payload(device: device, appVersion: Api.appVersion, records: nights, snapshots: [snapshot]))
        settings.sleepRead = true
        sent += nights.count

        return String(localized: "\(sent) records sent, \(deleted) deletions")
    }
}

enum SyncError: LocalizedError {
    case notConfigured
    case noHealthData

    var errorDescription: String? {
        switch self {
        case .notConfigured: return String(localized: "Enter the server address and the token first.")
        case .noHealthData: return String(localized: "Apple Health is not available on this device.")
        }
    }
}
