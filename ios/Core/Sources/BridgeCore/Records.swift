import Foundation

/// A value in the `data` object of a record. Only what the records need.
public enum JSONValue: Encodable, Equatable {
    case number(Double)
    case int(Int)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .number(let value): try container.encode(value)
        case .int(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        }
    }
}

/// One record as `POST /api/ingest/health` takes it: `{id, type, source, start, end?, data}`, the
/// same contract as the Android bridge (android/README.md, "Data contract").
public struct Record: Encodable, Equatable {
    public var id: String
    public var type: String
    public var source: String
    public var start: Date
    public var end: Date?
    public var data: [String: JSONValue]

    public init(id: String, type: String, source: String, start: Date, end: Date?, data: [String: JSONValue]) {
        self.id = id
        self.type = type
        self.source = String(source.prefix(200))
        self.start = start
        // Instant records (weight, resting heart rate) have no end.
        self.end = end.flatMap { $0 > start ? $0 : nil }
        self.data = data
    }

    enum CodingKeys: String, CodingKey {
        case id, type, source, start, end, data
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(type, forKey: .type)
        try container.encode(source, forKey: .source)
        try container.encode(ISOTime.string(start), forKey: .start)
        if let end { try container.encode(ISOTime.string(end), forKey: .end) }
        try container.encode(data, forKey: .data)
    }
}

/// Every record of one type that Apple Health has from `since` on; records of that type in Compass
/// that start in this range and are not listed are gone.
public struct Snapshot: Encodable, Equatable {
    public var type: String
    public var since: Date
    public var ids: [String]
    /// Only records whose id starts with this, so the records of other bridges stay.
    public var prefix: String?

    public init(type: String, since: Date, ids: [String], prefix: String? = nil) {
        self.type = type
        self.since = since
        self.ids = ids
        self.prefix = prefix
    }

    enum CodingKeys: String, CodingKey { case type, since, ids, prefix }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encode(ISOTime.string(since), forKey: .since)
        try container.encode(ids, forKey: .ids)
        try container.encodeIfPresent(prefix, forKey: .prefix)
    }
}

public struct Payload: Encodable {
    public var device: String
    public var appVersion: String
    public var records: [Record]
    public var deleted: [String]
    public var snapshots: [Snapshot]

    public init(device: String, appVersion: String, records: [Record] = [], deleted: [String] = [], snapshots: [Snapshot] = []) {
        self.device = String(device.prefix(120))
        self.appVersion = String(appVersion.prefix(40))
        self.records = records
        self.deleted = deleted
        self.snapshots = snapshots
    }

    enum CodingKeys: String, CodingKey {
        case device, records, deleted, snapshots
        case appVersion = "app_version"
    }

    public var isEmpty: Bool { records.isEmpty && deleted.isEmpty && snapshots.isEmpty }

    public func json() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(self)
    }
}

/// UTC times as the API expects them: "2026-11-11T22:00:00Z".
public enum ISOTime {
    private static let formatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    public static func string(_ date: Date) -> String { formatter.string(from: date) }
}

/// Record ids from HealthKit: the sample UUID, prefixed so they never collide with Health Connect ids.
public enum RecordId {
    public static func sample(_ uuid: UUID) -> String { "hk:\(uuid.uuidString.lowercased())" }

    /// The total_calories record that goes with an active energy sample.
    public static func total(_ uuid: UUID) -> String { "hk:total:\(uuid.uuidString.lowercased())" }

    /// Prefix of the night ids, for the sleep snapshot.
    public static let nightPrefix = "hk:sleep:"

    /// A night has no HealthKit id of its own: source and day of waking up.
    public static func night(source: String, wakeDay: String) -> String { "\(nightPrefix)\(fnv1a(source)):\(wakeDay)" }

    /// FNV-1a, 64 bit: stable across launches and platforms (Swift's hashValue is not).
    static func fnv1a(_ text: String) -> String {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in text.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x0000_0100_0000_01b3
        }
        let hex = String(hash, radix: 16)
        return String(repeating: "0", count: 16 - hex.count) + hex
    }
}
