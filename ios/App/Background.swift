import BackgroundTasks
import Foundation
import HealthKit

/// Syncs without the app open. Two ways, because iOS decides when either runs:
/// - HealthKit background delivery: an observer query per type wakes the app when new data is
///   written (at most hourly here). It has to be set up again at every launch.
/// - An app refresh task about every hour, as a fallback.
/// Opening the app always syncs, so it catches up when iOS let it sleep.
enum Background {
    static let refreshId = "com.raudev.compass.bridge.refresh"

    /// At launch, before the app finishes launching (iOS requires that for the task handler).
    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: refreshId, using: nil) { task in
            guard let task = task as? BGAppRefreshTask else { return }
            handle(task)
        }
    }

    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: refreshId)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func handle(_ task: BGAppRefreshTask) {
        schedule()
        let work = Task {
            do {
                _ = try await Syncer.shared.sync()
                task.setTaskCompleted(success: true)
            } catch {
                task.setTaskCompleted(success: false)
            }
        }
        task.expirationHandler = { work.cancel() }
    }

    private static var observing = false

    /// Observer queries with background delivery for every type. Needs read access, so it runs
    /// again after "Grant access".
    static func observeHealth() {
        guard HealthReader.available, Settings.shared.configured, !observing else { return }
        observing = true
        for type in HealthReader.sampleTypes {
            let query = HKObserverQuery(sampleType: type, predicate: nil) { _, completion, error in
                guard error == nil else {
                    completion()
                    return
                }
                Task {
                    _ = try? await Syncer.shared.sync()
                    completion()
                }
            }
            HealthReader.store.execute(query)
            HealthReader.store.enableBackgroundDelivery(for: type, frequency: .hourly) { _, _ in }
        }
    }
}
