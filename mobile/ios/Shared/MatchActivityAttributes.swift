import ActivityKit
import Foundation

/// A football game on the lock screen and in the Dynamic Island (Premium). Shared by the app, which starts and
/// watches activities, and the widget extension, which draws them. The server starts and updates them with the same
/// JSON names (backend/src/newzi_backend/live_activities.py): keep both in step.
@available(iOS 16.1, *)
struct MatchActivityAttributes: ActivityAttributes {
  public struct ContentState: Codable, Hashable {
    var homeGoals: Int
    var awayGoals: Int
    /// SCHEDULED, LIVE or FINISHED.
    var status: String
    /// Seconds since 1970 of the last change.
    var updatedAt: Double
  }

  var matchId: Int
  var home: String
  var away: String
  var homeTla: String
  var awayTla: String
  var competition: String
  /// Kickoff, in seconds since 1970.
  var kickoff: Double
}
