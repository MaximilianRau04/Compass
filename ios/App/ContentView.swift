import SwiftUI

@MainActor
struct ContentView: View {
    @Environment(\.scenePhase) private var scenePhase

    @State private var serverUrl = Settings.shared.serverUrl
    @State private var token = Settings.shared.token
    @State private var days = Settings.shared.initialDays
    @State private var message: String?
    @State private var busy = false
    @State private var confirmReset = false
    @State private var last = LastSync.now()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("https://compass.example", text: $serverUrl)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Token (HEALTH_TOKEN)", text: $token)
                    Button("Save and test", action: saveAndTest)
                } header: {
                    Text("Compass")
                } footer: {
                    Text("The dashboard address, without /api. Connect your VPN first if the server is only reachable there.")
                }

                Section {
                    Button("Grant access", action: grantAccess)
                } header: {
                    Text("Apple Health")
                } footer: {
                    Text("Allow all types. iOS does not tell the app what was denied; denied types simply stay empty in Compass.")
                }

                Section {
                    Stepper(value: $days, in: 7...365, step: 7) {
                        Text("First sync reads \(days) days")
                    }
                    .onChange(of: days) { Settings.shared.initialDays = $0 }
                    Button("Sync now", action: syncNow)
                    Button("Read again", role: .destructive) { confirmReset = true }
                } header: {
                    Text("Sync")
                } footer: {
                    Text("Syncs in the background when Apple Health gets new data and about every hour, whenever iOS allows it, and each time you open the app.")
                }

                Section("Last sync") {
                    if let message { Text(message) }
                    Text(last.text).foregroundStyle(last.failed ? .red : .secondary)
                }
            }
            .navigationTitle("Compass Bridge")
            .disabled(busy)
            .overlay { if busy { ProgressView() } }
            .confirmationDialog("Read the last \(days) days again?", isPresented: $confirmReset, titleVisibility: .visible) {
                Button("Read again", role: .destructive) {
                    Settings.shared.resetSync()
                    syncNow()
                }
            } message: {
                Text("Compass stores nothing twice.")
            }
        }
        .onChange(of: scenePhase) { phase in
            guard phase == .active, Settings.shared.configured else { return }
            Task {
                _ = try? await Syncer.shared.sync()
                last = LastSync.now()
            }
        }
    }

    private func run(_ work: @escaping () async throws -> String) {
        busy = true
        message = nil
        Task {
            do {
                message = try await work()
            } catch {
                message = Syncer.describe(error)
            }
            last = LastSync.now()
            busy = false
        }
    }

    private func saveAndTest() {
        Settings.shared.serverUrl = serverUrl
        Settings.shared.token = token
        serverUrl = Settings.shared.serverUrl
        run {
            guard let api = Api(Settings.shared) else { throw SyncError.notConfigured }
            _ = try await api.status()
            Background.observeHealth()
            return String(localized: "Connected.")
        }
    }

    private func grantAccess() {
        run {
            try await HealthReader.requestAccess()
            Background.observeHealth()
            return String(localized: "Done. Now tap Sync now.")
        }
    }

    private func syncNow() {
        run { try await Syncer.shared.sync() }
    }
}

/// The result of the last run as the app shows it.
struct LastSync {
    var text: String
    var failed: Bool

    static func now() -> LastSync {
        let settings = Settings.shared
        if let error = settings.lastError {
            return LastSync(text: error, failed: true)
        }
        guard let at = settings.lastSyncAt else {
            return LastSync(text: String(localized: "Not synced yet."), failed: false)
        }
        let when = at.formatted(date: .abbreviated, time: .shortened)
        return LastSync(text: "\(when): \(settings.lastResult ?? "")", failed: false)
    }
}
