import BridgeCore
import Foundation
import HealthKit

/// Reads Apple Health. Only reads: the app asks for no write access.
enum HealthReader {
    static let store = HKHealthStore()

    static let quantityIds: [QuantityKind: HKQuantityTypeIdentifier] = [
        .steps: .stepCount,
        .heartRate: .heartRate,
        .restingHeartRate: .restingHeartRate,
        .heartRateVariability: .heartRateVariabilitySDNN,
        .oxygenSaturation: .oxygenSaturation,
        .respiratoryRate: .respiratoryRate,
        .distance: .distanceWalkingRunning,
        .activeEnergy: .activeEnergyBurned,
        .basalEnergy: .basalEnergyBurned,
        .weight: .bodyMass,
        .dietaryEnergy: .dietaryEnergyConsumed,
        .protein: .dietaryProtein,
        .carbohydrates: .dietaryCarbohydrates,
        .fat: .dietaryFatTotal,
        .saturatedFat: .dietaryFatSaturated,
        .fiber: .dietaryFiber,
        .sugar: .dietarySugar,
        .sodium: .dietarySodium,
        .potassium: .dietaryPotassium,
        .calcium: .dietaryCalcium,
        .iron: .dietaryIron,
    ]

    static func quantityType(_ kind: QuantityKind) -> HKQuantityType {
        HKQuantityType(quantityIds[kind]!)
    }

    static let sleepType = HKCategoryType(.sleepAnalysis)
    static let workoutType = HKObjectType.workoutType()

    /// Everything the app reads, also what the observer queries watch.
    static var sampleTypes: [HKSampleType] {
        QuantityKind.allCases.map(quantityType) + [sleepType, workoutType]
    }

    static var available: Bool { HKHealthStore.isHealthDataAvailable() }

    /// Shows the Apple Health sheet. iOS never tells an app which read permissions were denied;
    /// denied types simply return nothing.
    static func requestAccess() async throws {
        try await store.requestAuthorization(toShare: [], read: Set(sampleTypes))
    }

    struct Changes {
        var records: [Record]
        var deleted: [String]
        var anchor: HKQueryAnchor
        /// Samples plus deletions this query returned, to know whether there is more.
        var count: Int
    }

    private static func source(_ sample: HKSample) -> String {
        sample.sourceRevision.source.bundleIdentifier
    }

    /// What changed for one quantity type since `anchor`, for samples from `since` on.
    static func changes(_ kind: QuantityKind, since: Date, anchor: HKQueryAnchor?, limit: Int) async throws -> Changes {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: nil)
        let descriptor = HKAnchoredObjectQueryDescriptor(
            predicates: [.quantitySample(type: quantityType(kind), predicate: predicate)],
            anchor: anchor,
            limit: limit
        )
        let result = try await descriptor.result(for: store)
        let unit = HKUnit(from: kind.unit)
        let records = result.addedSamples.flatMap { sample in
            kind.records(
                uuid: sample.uuid,
                source: source(sample),
                start: sample.startDate,
                end: sample.endDate,
                value: sample.quantity.doubleValue(for: unit),
                food: sample.metadata?[HKMetadataKeyFoodType] as? String
            )
        }
        return Changes(
            records: records,
            deleted: result.deletedObjects.flatMap { kind.recordIds($0.uuid) },
            anchor: result.newAnchor,
            count: result.addedSamples.count + result.deletedObjects.count
        )
    }

    static func workoutChanges(since: Date, anchor: HKQueryAnchor?, limit: Int) async throws -> Changes {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: nil)
        let descriptor = HKAnchoredObjectQueryDescriptor(
            predicates: [.workout(predicate)],
            anchor: anchor,
            limit: limit
        )
        let result = try await descriptor.result(for: store)
        let records = result.addedSamples.map { workout in
            Workout.record(
                uuid: workout.uuid,
                source: source(workout),
                start: workout.startDate,
                end: workout.endDate,
                exercise: exercise(workout),
                activityType: workout.workoutActivityType.rawValue,
                title: workout.metadata?[HKMetadataKeyWorkoutBrandName] as? String
            )
        }
        return Changes(
            records: records,
            deleted: result.deletedObjects.map { RecordId.sample($0.uuid) },
            anchor: result.newAnchor,
            count: result.addedSamples.count + result.deletedObjects.count
        )
    }

    /// The nights of every source with phases that start from `since` on.
    static func nights(since: Date) async throws -> [Record] {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: nil)
        let descriptor = HKSampleQueryDescriptor(
            predicates: [.categorySample(type: sleepType, predicate: predicate)],
            sortDescriptors: [SortDescriptor(\.startDate)]
        )
        let samples = try await descriptor.result(for: store)
        let segments = samples.compactMap { sample -> SleepSegment? in
            guard let value = SleepValue(healthKit: sample.value) else { return nil }
            return SleepSegment(start: sample.startDate, end: sample.endDate, value: value, source: source(sample))
        }
        return Sleep.nights(segments)
    }

    /// HKWorkoutActivityType as the exercise names of the backend (app.services.health). Strength
    /// training splits into push, pull and legs there; everything else counts as sport.
    static func exercise(_ workout: HKWorkout) -> String {
        let indoor = workout.metadata?[HKMetadataKeyIndoorWorkout] as? Bool ?? false
        switch workout.workoutActivityType {
        case .traditionalStrengthTraining, .functionalStrengthTraining: return "strength_training"
        case .coreTraining: return "calisthenics"
        case .highIntensityIntervalTraining, .crossTraining, .mixedCardio: return "hiit"
        case .running: return indoor ? "running_treadmill" : "running"
        case .walking: return "walking"
        case .hiking: return "hiking"
        case .cycling: return indoor ? "biking_stationary" : "biking"
        case .swimming:
            let location = (workout.metadata?[HKMetadataKeySwimmingLocationType] as? NSNumber)?.intValue
            return location == HKWorkoutSwimmingLocationType.openWater.rawValue ? "swimming_open_water" : "swimming_pool"
        case .elliptical: return "elliptical"
        case .rowing: return indoor ? "rowing_machine" : "rowing"
        case .stairClimbing, .stairs, .stepTraining: return "stair_climbing_machine"
        case .yoga: return "yoga"
        case .pilates: return "pilates"
        case .flexibility, .cooldown, .preparationAndRecovery: return "stretching"
        case .cardioDance, .socialDance, .barre: return "dancing"
        case .soccer: return "soccer"
        case .basketball: return "basketball"
        case .tennis: return "tennis"
        case .tableTennis: return "table_tennis"
        case .badminton: return "badminton"
        case .squash: return "squash"
        case .volleyball: return "volleyball"
        case .boxing, .kickboxing: return "boxing"
        case .martialArts: return "martial_arts"
        case .climbing: return "rock_climbing"
        case .other: return "other"
        // Not "type_<n>": the backend reads that as a Health Connect type number.
        default: return "hk_\(workout.workoutActivityType.rawValue)"
        }
    }
}
