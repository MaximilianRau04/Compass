import Foundation

/// HealthKit stores sleep as one sample per phase (HKCategoryValueSleepAnalysis); Compass wants a
/// night with its stages (the `sleep` record of the Health Connect contract). The phases of one
/// source are grouped into nights: a new night starts after a gap of more than `gap`.
public enum SleepValue: String {
    case inBed = "in_bed"
    case sleeping
    case awake
    case light
    case deep
    case rem

    /// HKCategoryValueSleepAnalysis raw values: inBed 0, asleepUnspecified 1, awake 2,
    /// asleepCore 3, asleepDeep 4, asleepREM 5.
    public init?(healthKit raw: Int) {
        switch raw {
        case 0: self = .inBed
        case 1: self = .sleeping
        case 2: self = .awake
        case 3: self = .light
        case 4: self = .deep
        case 5: self = .rem
        default: return nil
        }
    }
}

public struct SleepSegment: Equatable {
    public var start: Date
    public var end: Date
    public var value: SleepValue
    public var source: String

    public init(start: Date, end: Date, value: SleepValue, source: String) {
        self.start = start
        self.end = end
        self.value = value
        self.source = source
    }
}

public enum Sleep {
    public static let gap: TimeInterval = 2 * 60 * 60

    /// The nights in `segments` as `sleep` records. `calendar` gives the day of waking up (the
    /// phone's time zone), which together with the source makes the record id.
    public static func nights(_ segments: [SleepSegment], calendar: Calendar = .current) -> [Record] {
        let valid = segments.filter { $0.end > $0.start }
        var nights: [[SleepSegment]] = []
        for (_, ofSource) in Dictionary(grouping: valid, by: \.source).sorted(by: { $0.key < $1.key }) {
            var current: [SleepSegment] = []
            var currentEnd = Date.distantPast
            for segment in ofSource.sorted(by: { ($0.start, $0.end) < ($1.start, $1.end) }) {
                if !current.isEmpty, segment.start.timeIntervalSince(currentEnd) > gap {
                    nights.append(current)
                    current = []
                }
                current.append(segment)
                currentEnd = current.count == 1 ? segment.end : max(currentEnd, segment.end)
            }
            if !current.isEmpty { nights.append(current) }
        }
        return nights.compactMap { record($0, calendar: calendar) }
    }

    static func record(_ night: [SleepSegment], calendar: Calendar) -> Record? {
        guard let first = night.first, let start = night.map(\.start).min(), let end = night.map(\.end).max() else {
            return nil
        }
        let wake = calendar.dateComponents([.year, .month, .day], from: end)
        let wakeDay = String(format: "%04d-%02d-%02d", wake.year ?? 0, wake.month ?? 0, wake.day ?? 0)
        return Record(
            id: RecordId.night(source: first.source, wakeDay: wakeDay),
            type: "sleep",
            source: first.source,
            start: start,
            end: end,
            data: ["stages": .array(stages(night).map { stage in
                .object([
                    "start": .string(ISOTime.string(stage.start)),
                    "end": .string(ISOTime.string(stage.end)),
                    "stage": .string(stage.value.rawValue),
                ])
            })]
        )
    }

    /// The phases of a night, plus the time in bed that no phase covers as awake_in_bed (the stage
    /// Health Connect uses for it).
    static func stages(_ night: [SleepSegment]) -> [(start: Date, end: Date, value: StageName)] {
        let phases = night.filter { $0.value != .inBed }.sorted { ($0.start, $0.end) < ($1.start, $1.end) }
        guard !phases.isEmpty, let windowStart = night.map(\.start).min(), let windowEnd = night.map(\.end).max() else {
            return []
        }
        var out: [(start: Date, end: Date, value: StageName)] = []
        var coveredUntil = windowStart
        for phase in phases {
            if phase.start > coveredUntil { out.append((coveredUntil, phase.start, .awakeInBed)) }
            out.append((phase.start, phase.end, StageName(phase.value)))
            coveredUntil = max(coveredUntil, phase.end)
        }
        if windowEnd > coveredUntil { out.append((coveredUntil, windowEnd, .awakeInBed)) }
        return out.sorted { $0.start < $1.start }
    }
}

/// Stage names of the `sleep` record (app.ingestion.healthconnect in the backend).
public enum StageName: String {
    case sleeping, awake, light, deep, rem
    case awakeInBed = "awake_in_bed"

    init(_ value: SleepValue) {
        switch value {
        case .inBed: self = .awakeInBed
        case .sleeping: self = .sleeping
        case .awake: self = .awake
        case .light: self = .light
        case .deep: self = .deep
        case .rem: self = .rem
        }
    }
}
