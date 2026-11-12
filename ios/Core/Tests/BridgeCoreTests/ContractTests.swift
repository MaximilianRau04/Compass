import Foundation
import XCTest

@testable import BridgeCore

/// The records of BridgeCore must match backend/tests/fixtures/healthkit_records.json, which the
/// backend test suite ingests (test_healthkit_contract.py). After changing the mapping on purpose,
/// run with UPDATE_CONTRACT=1 to rewrite the fixture, then run the backend tests.
final class ContractTests: XCTestCase {
    static let watch = "com.apple.health.watch"
    static let phone = "com.apple.health.iphone"

    static func time(_ text: String) -> Date {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: text)!
    }

    static func uuid(_ n: Int) -> UUID {
        UUID(uuidString: String(format: "00000000-0000-0000-0000-%012x", n))!
    }

    static var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    /// In bed 20:45 to 05:00 UTC, from 21:00: 150 core, 60 deep, 15 awake, 90 REM, 150 core.
    static func night(source: String = watch, day: String = "2026-10-17") -> [SleepSegment] {
        let bed = time("\(day)T20:45:00Z")
        var out = [SleepSegment(start: bed, end: bed.addingTimeInterval(495 * 60), value: .inBed, source: source)]
        var cursor = time("\(day)T21:00:00Z")
        for (value, minutes) in [(SleepValue.light, 150), (.deep, 60), (.awake, 15), (.rem, 90), (.light, 150)] {
            let end = cursor.addingTimeInterval(Double(minutes) * 60)
            out.append(SleepSegment(start: cursor, end: end, value: value, source: source))
            cursor = end
        }
        return out
    }

    static func contractRecords() -> [Record] {
        let t = time
        var records = Sleep.nights(night(), calendar: utc)
        func add(_ kind: QuantityKind, _ n: Int, _ source: String, _ start: String, _ end: String?, _ value: Double, food: String? = nil) {
            records += kind.records(uuid: uuid(n), source: source, start: t(start), end: t(end ?? start), value: value, food: food)
        }
        add(.steps, 1, phone, "2026-10-17T21:00:00Z", "2026-10-17T21:10:00Z", 1234)
        add(.heartRate, 2, watch, "2026-10-17T21:00:00Z", nil, 58)
        add(.restingHeartRate, 3, watch, "2026-10-18T06:00:00Z", nil, 52)
        add(.heartRateVariability, 4, watch, "2026-10-18T03:00:00Z", nil, 48.5)
        add(.oxygenSaturation, 5, watch, "2026-10-18T03:00:00Z", nil, 0.97)
        add(.respiratoryRate, 6, watch, "2026-10-18T03:00:00Z", nil, 14.5)
        add(.distance, 7, watch, "2026-10-18T07:00:00Z", "2026-10-18T07:30:00Z", 1200.5)
        add(.activeEnergy, 8, watch, "2026-10-18T07:00:00Z", "2026-10-18T08:00:00Z", 300)
        add(.basalEnergy, 9, watch, "2026-10-18T07:00:00Z", "2026-10-18T08:00:00Z", 1600)
        add(.weight, 10, "com.withings.wiScaleNG", "2026-10-18T05:30:00Z", nil, 78.7)
        add(.dietaryEnergy, 11, "com.myfitnesspal.mfp", "2026-10-18T11:30:00Z", nil, 650, food: "Pasta")
        add(.protein, 12, "com.myfitnesspal.mfp", "2026-10-18T11:30:00Z", nil, 40, food: "Pasta")
        records.append(Workout.record(
            uuid: uuid(13), source: watch, start: t("2026-10-18T16:00:00Z"), end: t("2026-10-18T17:15:00Z"),
            exercise: "strength_training", activityType: 50, title: nil
        ))
        return records
    }

    static var fixture: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("../../backend/tests/fixtures/healthkit_records.json")
            .standardizedFileURL
    }

    func testRecordsMatchTheBackendFixture() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        let encoded = try encoder.encode(Self.contractRecords())
        if ProcessInfo.processInfo.environment["UPDATE_CONTRACT"] == "1" {
            try encoded.write(to: Self.fixture)
            return
        }
        let expected = try JSONDecoder().decode(Canonical.self, from: Data(contentsOf: Self.fixture))
        let actual = try JSONDecoder().decode(Canonical.self, from: encoded)
        XCTAssertEqual(actual, expected)
    }

    func testPayloadUsesTheApiFieldNames() throws {
        let payload = Payload(
            device: "iPhone", appVersion: "0.1.0",
            deleted: ["hk:x"],
            snapshots: [Snapshot(type: "sleep", since: Self.time("2026-10-15T12:00:00Z"), ids: ["a"])]
        )
        guard case .object(let json) = try JSONDecoder().decode(Canonical.self, from: payload.json()) else {
            return XCTFail("not an object")
        }
        XCTAssertEqual(json["app_version"], .string("0.1.0"))
        XCTAssertEqual(json["deleted"], .array([.string("hk:x")]))
        XCTAssertEqual(json["snapshots"], .array([.object([
            "type": .string("sleep"),
            "since": .string("2026-10-15T12:00:00Z"),
            "ids": .array([.string("a")]),
        ])]))
    }
}

/// JSON compared by value: 97 and 97.0 are the same number, key order does not matter.
indirect enum Canonical: Decodable, Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([Canonical])
    case object([String: Canonical])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([Canonical].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: Canonical].self))
        }
    }
}

final class SleepTests: XCTestCase {
    func testPhasesOfOneSourceBecomeOneNightPerWakeDay() {
        let calendar = ContractTests.utc
        let segments = ContractTests.night() + ContractTests.night(day: "2026-10-18")
        let nights = Sleep.nights(segments.shuffled(), calendar: calendar)
        XCTAssertEqual(nights.count, 2)
        XCTAssertEqual(Set(nights.map(\.id)).count, 2)
        XCTAssertTrue(nights.allSatisfy { $0.id.hasSuffix("2026-10-18") || $0.id.hasSuffix("2026-10-19") })
    }

    func testSourcesStayApart() {
        let segments = ContractTests.night() + ContractTests.night(source: ContractTests.phone)
        XCTAssertEqual(Sleep.nights(segments, calendar: ContractTests.utc).count, 2)
    }

    func testTheSameNightKeepsItsId() {
        let calendar = ContractTests.utc
        let full = Sleep.nights(ContractTests.night(), calendar: calendar)
        let part = Sleep.nights(Array(ContractTests.night().prefix(3)), calendar: calendar)
        XCTAssertEqual(full.first?.id, part.first?.id)
    }

    func testOnlyInBedHasNoStages() {
        let bed = ContractTests.night().first!
        let night = Sleep.nights([bed], calendar: ContractTests.utc).first
        XCTAssertEqual(night?.data["stages"], .array([]))
    }

    func testHealthKitValues() {
        XCTAssertEqual(SleepValue(healthKit: 3), .light)
        XCTAssertEqual(SleepValue(healthKit: 5), .rem)
        XCTAssertNil(SleepValue(healthKit: 9))
    }
}

final class MappingTests: XCTestCase {
    func testActiveEnergyIsDeletedWithItsTotal() {
        let id = ContractTests.uuid(8)
        XCTAssertEqual(QuantityKind.activeEnergy.recordIds(id).count, 2)
        XCTAssertEqual(QuantityKind.steps.recordIds(id), [RecordId.sample(id)])
    }

    func testRecordIdsFitTheApi() {
        let night = RecordId.night(source: String(repeating: "x", count: 200), wakeDay: "2026-10-18")
        XCTAssertLessThanOrEqual(night.count, 64)
        XCTAssertLessThanOrEqual(RecordId.total(UUID()).count, 64)
    }
}
