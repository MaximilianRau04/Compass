// swift-tools-version:5.9
// The part of the iOS bridge without HealthKit: records, JSON and grouping sleep into nights.
// Builds and tests on macOS and Linux (`swift test`), so the data contract can be checked anywhere.
import PackageDescription

let package = Package(
    name: "BridgeCore",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [.library(name: "BridgeCore", targets: ["BridgeCore"])],
    targets: [
        .target(name: "BridgeCore"),
        .testTarget(name: "BridgeCoreTests", dependencies: ["BridgeCore"]),
    ]
)
