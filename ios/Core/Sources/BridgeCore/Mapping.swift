import Foundation

/// The HealthKit quantity types the bridge reads, each with the record it becomes. The app reads
/// the value in `unit` (an HKUnit unit string) and passes it to `records`.
public enum QuantityKind: String, CaseIterable {
    case steps
    case heartRate
    case restingHeartRate
    case heartRateVariability
    case oxygenSaturation
    case respiratoryRate
    case distance
    case activeEnergy
    case basalEnergy
    case weight
    case dietaryEnergy
    case protein
    case carbohydrates
    case fat
    case saturatedFat
    case fiber
    case sugar
    case sodium
    case potassium
    case calcium
    case iron

    /// The unit to read the quantity in, as `HKUnit(from:)` takes it.
    public var unit: String {
        switch self {
        case .steps: return "count"
        case .heartRate, .restingHeartRate, .respiratoryRate: return "count/min"
        case .heartRateVariability: return "ms"
        case .oxygenSaturation: return "%"
        case .distance: return "m"
        case .activeEnergy, .basalEnergy, .dietaryEnergy: return "kcal"
        case .weight: return "kg"
        case .protein, .carbohydrates, .fat, .saturatedFat, .fiber, .sugar: return "g"
        case .sodium, .potassium, .calcium, .iron: return "mg"
        }
    }

    /// The field of a `nutrition` record, for the nutrients.
    var nutritionField: String? {
        switch self {
        case .dietaryEnergy: return "energy_kcal"
        case .protein: return "protein_g"
        case .carbohydrates: return "carbs_g"
        case .fat: return "fat_g"
        case .saturatedFat: return "saturated_fat_g"
        case .fiber: return "fiber_g"
        case .sugar: return "sugar_g"
        case .sodium: return "sodium_mg"
        case .potassium: return "potassium_mg"
        case .calcium: return "calcium_mg"
        case .iron: return "iron_mg"
        default: return nil
        }
    }

    /// Ids of the records one sample becomes, for its deletion.
    public func recordIds(_ uuid: UUID) -> [String] {
        self == .activeEnergy ? [RecordId.sample(uuid), RecordId.total(uuid)] : [RecordId.sample(uuid)]
    }

    /// The records of one sample. `value` is in `unit`; `food` is HKMetadataKeyFoodType.
    public func records(uuid: UUID, source: String, start: Date, end: Date, value: Double, food: String? = nil) -> [Record] {
        let id = RecordId.sample(uuid)
        func one(_ type: String, _ data: [String: JSONValue], instant: Bool = false) -> [Record] {
            [Record(id: id, type: type, source: source, start: start, end: instant ? nil : end, data: data)]
        }
        if let field = nutritionField {
            // HealthKit has no meals; the meal is unknown, like a Health Connect record without one.
            var data: [String: JSONValue] = ["meal_type": .string("unknown"), field: .number(value)]
            if let food, !food.isEmpty { data["name"] = .string(String(food.prefix(200))) }
            return one("nutrition", data)
        }
        switch self {
        case .steps:
            return one("steps", ["count": .int(Int(value.rounded()))])
        case .heartRate:
            let sample: JSONValue = .object(["time": .string(ISOTime.string(start)), "bpm": .int(Int(value.rounded()))])
            return one("heart_rate", ["samples": .array([sample])])
        case .restingHeartRate:
            return one("resting_heart_rate", ["bpm": .int(Int(value.rounded()))], instant: true)
        case .heartRateVariability:
            // HealthKit measures SDNN; Health Connect sends RMSSD. Compass keeps them apart.
            return one("heart_rate_variability_sdnn", ["sdnn_ms": .number(value)], instant: true)
        case .oxygenSaturation:
            // HKUnit.percent() reads 97 % as 0.97.
            return one("oxygen_saturation", ["percent": .number((value * 1000).rounded() / 10)], instant: true)
        case .respiratoryRate:
            return one("respiratory_rate", ["rate": .number(value)], instant: true)
        case .distance:
            return one("distance", ["meters": .number(value)])
        case .activeEnergy:
            // Health Connect has the total burned per reading. Here a day's total is active plus
            // basal, so active energy is also sent as total_calories (under its own id).
            return one("active_calories", ["kcal": .number(value)]) + [
                Record(id: RecordId.total(uuid), type: "total_calories", source: source, start: start, end: end, data: ["kcal": .number(value)]),
            ]
        case .basalEnergy:
            return one("total_calories", ["kcal": .number(value)])
        case .weight:
            return one("weight", ["kg": .number((value * 100).rounded() / 100)], instant: true)
        default:
            return []
        }
    }
}

/// HKWorkout as an `exercise` record. `exercise` is one of the names in app.services.health
/// (strength_training, running, ...), chosen by the app from HKWorkoutActivityType.
public enum Workout {
    public static func record(uuid: UUID, source: String, start: Date, end: Date, exercise: String, activityType: UInt, title: String?) -> Record {
        var data: [String: JSONValue] = ["exercise": .string(exercise), "activity_type": .int(Int(activityType))]
        if let title, !title.isEmpty { data["title"] = .string(String(title.prefix(200))) }
        return Record(id: RecordId.sample(uuid), type: "exercise", source: source, start: start, end: end, data: data)
    }
}
