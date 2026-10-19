import ActivityKit
import SwiftUI
import WidgetKit

/// The score of a favourite team's game on the lock screen and in the Dynamic Island (Premium).
@available(iOS 16.1, *)
struct MatchLiveActivity: Widget {
  var body: some WidgetConfiguration {
    ActivityConfiguration(for: MatchActivityAttributes.self) { context in
      MatchLockScreenView(attributes: context.attributes, state: context.state)
        .activityBackgroundTint(Color(red: 0.04, green: 0.20, blue: 0.16))
        .activitySystemActionForegroundColor(.white)
        .widgetURL(DeepLink.football)
    } dynamicIsland: { context in
      DynamicIsland {
        DynamicIslandExpandedRegion(.leading) {
          TeamScore(tla: context.attributes.homeTla, goals: context.state.homeGoals, status: context.state.status)
        }
        DynamicIslandExpandedRegion(.trailing) {
          TeamScore(tla: context.attributes.awayTla, goals: context.state.awayGoals, status: context.state.status)
        }
        DynamicIslandExpandedRegion(.center) {
          Text(context.attributes.competition).font(.caption2.weight(.semibold)).foregroundColor(.secondary).lineLimit(1)
        }
        DynamicIslandExpandedRegion(.bottom) {
          MatchStatusText(attributes: context.attributes, state: context.state).font(.caption.weight(.semibold))
        }
      } compactLeading: {
        Text(context.state.status == "SCHEDULED" ? context.attributes.homeTla : "\(context.attributes.homeTla) \(context.state.homeGoals)")
          .font(.caption.weight(.heavy))
      } compactTrailing: {
        Text(context.state.status == "SCHEDULED" ? context.attributes.awayTla : "\(context.state.awayGoals) \(context.attributes.awayTla)")
          .font(.caption.weight(.heavy))
      } minimal: {
        Text(context.state.status == "SCHEDULED" ? "⚽︎" : "\(context.state.homeGoals)-\(context.state.awayGoals)").font(.caption2.weight(.heavy))
      }
      .widgetURL(DeepLink.football)
    }
  }
}

@available(iOS 16.1, *)
struct MatchLockScreenView: View {
  let attributes: MatchActivityAttributes
  let state: MatchActivityAttributes.ContentState
  var body: some View {
    VStack(spacing: 8) {
      HStack {
        Text("NEWZI").font(.system(size: 11, weight: .heavy)).tracking(1.2).foregroundColor(.white.opacity(0.8))
        Spacer()
        Text(attributes.competition).font(.system(size: 11, weight: .semibold)).foregroundColor(.white.opacity(0.8)).lineLimit(1)
      }
      HStack(alignment: .center) {
        side(name: attributes.home, tla: attributes.homeTla)
        Spacer()
        if state.status == "SCHEDULED" {
          Text(Date(timeIntervalSince1970: attributes.kickoff), style: .time).font(.system(size: 26, weight: .heavy)).foregroundColor(.white)
        } else {
          Text("\(state.homeGoals)  x  \(state.awayGoals)").font(.system(size: 30, weight: .heavy)).foregroundColor(.white).monospacedDigit()
        }
        Spacer()
        side(name: attributes.away, tla: attributes.awayTla)
      }
      MatchStatusText(attributes: attributes, state: state).font(.system(size: 12, weight: .semibold)).foregroundColor(.white.opacity(0.9))
    }
    .padding(16)
  }

  func side(name: String, tla: String) -> some View {
    VStack(spacing: 3) {
      Text(tla).font(.system(size: 18, weight: .heavy)).foregroundColor(.white)
      Text(name).font(.system(size: 11, weight: .medium)).foregroundColor(.white.opacity(0.8)).lineLimit(1)
    }
    .frame(width: 92)
  }
}

@available(iOS 16.1, *)
struct TeamScore: View {
  let tla: String
  let goals: Int
  let status: String
  var body: some View {
    VStack(spacing: 2) {
      Text(tla).font(.caption.weight(.heavy))
      Text(status == "SCHEDULED" ? "–" : "\(goals)").font(.title2.weight(.heavy)).monospacedDigit()
    }
    .padding(.horizontal, 6)
  }
}

@available(iOS 16.1, *)
struct MatchStatusText: View {
  let attributes: MatchActivityAttributes
  let state: MatchActivityAttributes.ContentState
  var body: some View {
    switch state.status {
    case "LIVE":
      HStack(spacing: 5) {
        Circle().fill(Color.red).frame(width: 7, height: 7)
        Text("Ao vivo · começou ") + Text(Date(timeIntervalSince1970: attributes.kickoff), style: .relative)
      }
    case "FINISHED":
      Text("Fim de jogo")
    default:
      Text("Começa em ") + Text(Date(timeIntervalSince1970: attributes.kickoff), style: .relative)
    }
  }
}
