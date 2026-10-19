import ActivityKit
import Foundation
import React
import WidgetKit

/// The app's side of the widgets and Live Activities (src/services/iosWidgets.ts):
/// - setData: the JSON the widgets show, into the App Group, then a widget reload;
/// - startMatch / endMatch: a game's activity started from the app (iOS 16.2+);
/// - observeLiveActivities: reports the push-to-start token (iOS 17.2+) and each activity's update token as events,
///   so the server can start and update them (backend/src/newzi_backend/live_activities.py).
@objc(NewziWidgets)
class NewziWidgets: RCTEventEmitter {
  private static let appGroup = "group.app.newzi.ios"
  private var hasListeners = false
  private var observing = false
  private var watched = Set<String>()

  override static func requiresMainQueueSetup() -> Bool { false }
  override func supportedEvents() -> [String]! { ["liveActivityToken", "liveActivityStartToken"] }
  override func startObserving() { hasListeners = true }
  override func stopObserving() { hasListeners = false }

  private func emit(_ name: String, _ body: [String: Any]) {
    if hasListeners { sendEvent(withName: name, body: body) }
  }

  @objc func setData(_ json: String) {
    UserDefaults(suiteName: NewziWidgets.appGroup)?.set(json, forKey: "newzi.widget")
    WidgetCenter.shared.reloadAllTimelines()
  }

  @objc func liveActivitiesEnabled(_ resolve: RCTPromiseResolveBlock, rejecter reject: RCTPromiseRejectBlock) {
    if #available(iOS 16.2, *) { resolve(ActivityAuthorizationInfo().areActivitiesEnabled) } else { resolve(false) }
  }

  @objc func observeLiveActivities() {
    guard #available(iOS 16.2, *), !observing else { return }
    observing = true
    for activity in Activity<MatchActivityAttributes>.activities { watch(activity) }
    Task { for await activity in Activity<MatchActivityAttributes>.activityUpdates { self.watch(activity) } }
    if #available(iOS 17.2, *) {
      Task { for await token in Activity<MatchActivityAttributes>.pushToStartTokenUpdates { self.emit("liveActivityStartToken", ["token": token.hexString]) } }
    }
  }

  @available(iOS 16.2, *)
  private func watch(_ activity: Activity<MatchActivityAttributes>) {
    guard watched.insert(activity.id).inserted else { return }
    let matchId = activity.attributes.matchId
    Task {
      for await token in activity.pushTokenUpdates { self.emit("liveActivityToken", ["token": token.hexString, "matchId": matchId]) }
    }
  }

  /// ``json``: {"attributes": MatchActivityAttributes, "state": ContentState}. Resolves false where unsupported.
  @objc func startMatch(_ json: String, resolver resolve: @escaping RCTPromiseResolveBlock, rejecter reject: @escaping RCTPromiseRejectBlock) {
    guard #available(iOS 16.2, *) else { resolve(false); return }
    struct Request: Decodable { let attributes: MatchActivityAttributes; let state: MatchActivityAttributes.ContentState }
    guard let data = json.data(using: .utf8), let request = try? JSONDecoder().decode(Request.self, from: data) else {
      reject("LIVE_ACTIVITY_INVALID", "invalid activity", nil); return
    }
    if let running = Activity<MatchActivityAttributes>.activities.first(where: { $0.attributes.matchId == request.attributes.matchId }) {
      Task { await running.update(ActivityContent(state: request.state, staleDate: nil)) }
      resolve(true); return
    }
    do {
      let activity = try Activity.request(attributes: request.attributes, content: ActivityContent(state: request.state, staleDate: nil), pushType: .token)
      watch(activity)
      resolve(true)
    } catch {
      reject("LIVE_ACTIVITY_FAILED", error.localizedDescription, error)
    }
  }

  @objc func endMatch(_ matchId: NSNumber) {
    guard #available(iOS 16.2, *) else { return }
    for activity in Activity<MatchActivityAttributes>.activities where activity.attributes.matchId == matchId.intValue {
      Task { await activity.end(nil, dismissalPolicy: .default) }
    }
  }
}

extension Data {
  var hexString: String { map { String(format: "%02x", $0) }.joined() }
}
