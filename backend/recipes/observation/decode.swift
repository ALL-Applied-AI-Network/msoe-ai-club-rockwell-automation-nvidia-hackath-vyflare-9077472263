// Native acquisition matches the development decoder: 4 fps JPEG event images,
// original presentation times, and lossless three-frame appearance samples.
import Foundation
import AVFoundation
import AppKit
import CoreImage

struct Record: Codable {
    let id: String
    let requested_seconds: Double
    let actual_seconds: Double
    let width: Int
    let height: Int
}
struct Task: Codable { let id: String; let seconds: Double }
struct Window: Codable { let id: String; let lower: Double; let upper: Double }
func run() throws {
let args = CommandLine.arguments
let mode = args[1], source = URL(fileURLWithPath: args[2]), root = URL(fileURLWithPath: args[3])
let asset = AVURLAsset(url: source)
guard let track = asset.tracks(withMediaType: .video).first,
      track.naturalSize == CGSize(width: 640, height: 480),
      track.preferredTransform == .identity,
      CMTimeGetSeconds(asset.duration).isFinite,
      CMTimeGetSeconds(asset.duration) > 0,
      CMTimeGetSeconds(asset.duration) <= 1800 else {
    throw NSError(domain: "Unsupported recording geometry or duration", code: 2)
}
var records = [Record]()
func save(_ image: CGImage, _ id: String, _ requested: Double, _ actual: Double, _ png: Bool) throws {
    guard image.width == 640 && image.height == 480 else { throw NSError(domain: "Unsupported frame geometry", code: 3) }
    let bitmap = NSBitmapImageRep(cgImage: image)
    let data = bitmap.representation(using: png ? .png : .jpeg, properties: png ? [:] : [.compressionFactor: 0.92])!
    try data.write(to: root.appendingPathComponent(id + (png ? ".png" : ".jpg")))
    records.append(Record(id: id, requested_seconds: requested, actual_seconds: actual, width: image.width, height: image.height))
}
if mode == "events" {
    let reader = try AVAssetReader(asset: asset)
    let output = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
    output.alwaysCopiesSampleData = false; reader.add(output)
    guard reader.startReading() else { throw reader.error! }
    let context = CIContext()
    var target = 0.0
    while let sample = output.copyNextSampleBuffer() {
        let seconds = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
        if seconds + 0.00001 < target { continue }
        try autoreleasepool {
            let pixel = CMSampleBufferGetImageBuffer(sample)!
            let image = CIImage(cvPixelBuffer: pixel)
            try save(context.createCGImage(image, from: image.extent)!, String(format: "event_%07.2f", target), target, seconds, false)
        }
        target += 0.25
        if records.count > 7200 { throw NSError(domain: "Frame budget exceeded", code: 4) }
    }
    if reader.status != .completed { throw reader.error ?? NSError(domain: "decoder", code: 1) }
} else if mode == "windows" {
    let windows = try JSONDecoder().decode([Window].self, from: Data(contentsOf: root.appendingPathComponent("tasks.json")))
    guard windows.count <= 300 && windows.allSatisfy({ $0.lower.isFinite && $0.upper.isFinite && $0.lower >= 0 && $0.upper > $0.lower }),
          windows.reduce(0.0, { $0 + $1.upper - $1.lower }) <= 300.000001 else {
        throw NSError(domain: "Native timing resource budget exceeded", code: 6)
    }
    let context = CIContext()
    for window in windows {
        let reader = try AVAssetReader(asset: asset)
        reader.timeRange = CMTimeRange(start: CMTime(seconds: max(0,window.lower-0.05), preferredTimescale: 30000),
            duration: CMTime(seconds: window.upper-window.lower+0.1, preferredTimescale: 30000))
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        output.alwaysCopiesSampleData = false; reader.add(output)
        guard reader.startReading() else { throw reader.error! }
        var count = 0
        while let sample = output.copyNextSampleBuffer() {
            let seconds = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
            if seconds + 0.000001 < window.lower || seconds - 0.000001 > window.upper { continue }
            try autoreleasepool {
                let pixel = CMSampleBufferGetImageBuffer(sample)!
                let image = CIImage(cvPixelBuffer: pixel)
                try save(context.createCGImage(image, from: image.extent)!, String(format: "%@_%04d",window.id,count), seconds, seconds, true)
            }
            count += 1
            if records.count > 9600 { throw NSError(domain: "Native timing frame budget exceeded", code: 7) }
        }
        if reader.status == .failed { throw reader.error ?? NSError(domain: "decoder", code: 1) }
    }
} else if mode == "color" {
    let tasks = try JSONDecoder().decode([Task].self, from: Data(contentsOf: root.appendingPathComponent("tasks.json")))
    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.requestedTimeToleranceBefore = .zero; generator.requestedTimeToleranceAfter = .zero
    for task in tasks {
        var actual = CMTime.zero
        let image = try generator.copyCGImage(at: CMTime(seconds: task.seconds, preferredTimescale: 30000), actualTime: &actual)
        try save(image, task.id, task.seconds, CMTimeGetSeconds(actual), true)
    }
} else { throw NSError(domain: "Unsupported decoder mode", code: 5) }
let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
try encoder.encode(records).write(to: root.appendingPathComponent("manifest.json"))

}
do { try run() } catch {
    fputs("Native video decoding failed: \(error)\n", stderr)
    exit(1)
}
