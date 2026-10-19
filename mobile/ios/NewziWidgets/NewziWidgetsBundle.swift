import SwiftUI
import WidgetKit

/// Newzi's widgets and the live game activity. The app shares their data through the App Group.
@main
struct NewziWidgetsBundle: WidgetBundle {
  var body: some Widget {
    HeadlinesWidget()
    if #available(iOS 17.0, *) {
      TopicWidget()
      TeamWidget()
    }
    MatchLiveActivity()
  }
}
