// swift-tools-version:6.0
// SPDX-License-Identifier: AGPL-3.0-or-later
import PackageDescription

let package = Package(
    name: "QuilateNotch",
    platforms: [.macOS(.v15)],
    targets: [
        .executableTarget(name: "QuilateNotch"),
        .testTarget(name: "QuilateNotchTests", dependencies: ["QuilateNotch"]),
    ]
)
