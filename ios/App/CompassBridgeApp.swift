import SwiftUI
import UIKit

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // iOS may launch the app in the background for HealthKit or the refresh task; both need
        // their handlers before launching ends.
        Background.register()
        Background.observeHealth()
        Background.schedule()
        return true
    }
}

@main
struct CompassBridgeApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
