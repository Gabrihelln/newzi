import Foundation
import SwiftUI
import WidgetKit

/// What the app shares with its widgets: written by the app (src/services/iosWidgets.ts, through the NewziWidgets
/// native module) into the App Group as JSON, read here on every timeline refresh.
enum NewziShared {
  static let appGroup = "group.app.newzi.ios"
  static let dataKey = "newzi.widget"
  static let blue = Color(red: 0.12, green: 0.50, blue: 0.92)
  static let ink = Color(red: 0.06, green: 0.10, blue: 0.25)
}

struct WidgetStory: Codable, Hashable, Identifiable {
  let id: String
  let title: String
  let topic: String?
  let source: String?
}

struct WidgetBriefing: Codable {
  let title: String
  let next: String
  let headlines: [WidgetStory]
}

struct WidgetTopic: Codable, Identifiable {
  let id: String
  let name: String
  let headlines: [WidgetStory]
}

struct WidgetMatch: Codable {
  let id: Int
  let home: String
  let away: String
  let homeTla: String
  let awayTla: String
  let homeGoals: Int?
  let awayGoals: Int?
  /// SCHEDULED, LIVE or FINISHED.
  let status: String
  let kickoff: Double
  let competition: String
}

struct WidgetTeam: Codable, Identifiable {
  let id: Int
  let name: String
  let tla: String
  let match: WidgetMatch?
}

struct WidgetPayload: Codable {
  let updatedAt: Double
  let premium: Bool
  let briefing: WidgetBriefing?
  let topics: [WidgetTopic]
  let teams: [WidgetTeam]

  static func load() -> WidgetPayload? {
    guard let json = UserDefaults(suiteName: NewziShared.appGroup)?.string(forKey: NewziShared.dataKey),
          let data = json.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(WidgetPayload.self, from: data)
  }

  /// Shown in the widget gallery and before the app has written anything.
  static let sample = WidgetPayload(
    updatedAt: Date().timeIntervalSince1970, premium: true,
    briefing: WidgetBriefing(title: "Seu resumo diário", next: "Amanhã às 06:00", headlines: [
      WidgetStory(id: "1", title: "Banco Central mantém os juros e sinaliza cortes no próximo ano", topic: "Economia", source: nil),
      WidgetStory(id: "2", title: "Nova missão espacial parte rumo à Lua com tripulação internacional", topic: "Ciência", source: nil),
      WidgetStory(id: "3", title: "Seleção vence e garante vaga na próxima fase", topic: "Esportes", source: nil),
    ]),
    topics: [WidgetTopic(id: "SPORTS", name: "Esportes", headlines: [
      WidgetStory(id: "3", title: "Seleção vence e garante vaga na próxima fase", topic: "Esportes", source: nil),
    ])],
    teams: [WidgetTeam(id: 1, name: "Flamengo", tla: "FLA", match: WidgetMatch(
      id: 1, home: "Flamengo", away: "Palmeiras", homeTla: "FLA", awayTla: "PAL", homeGoals: 1, awayGoals: 0,
      status: "LIVE", kickoff: Date().timeIntervalSince1970 - 1800, competition: "Brasileirão"))])
}

struct WidgetEntry: TimelineEntry {
  let date: Date
  let payload: WidgetPayload?
}

enum DeepLink {
  static let briefing = URL(string: "newzi://briefing")!
  static let football = URL(string: "newzi://football")!
  static let premium = URL(string: "newzi://premium")!
  static func story(_ id: String) -> URL { URL(string: "newzi://story/\(id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id)")! }
}

extension View {
  /// iOS 17 draws the widget background itself (containerBackground); before, a plain background.
  @ViewBuilder func widgetBackground(_ color: Color) -> some View {
    if #available(iOS 17.0, *) {
      containerBackground(color, for: .widget)
    } else {
      background(color)
    }
  }
}

/// The brand line on top of every widget.
struct WidgetBrand: View {
  var label: String? = nil
  var body: some View {
    HStack(spacing: 6) {
      Text("NEWZI").font(.system(size: 11, weight: .heavy)).foregroundColor(NewziShared.blue).tracking(1.2)
      if let label { Text(label).font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary).lineLimit(1) }
      Spacer(minLength: 0)
    }
  }
}

/// A larger size or a Premium widget for an account without Premium: what it would show, and where to get it.
struct PremiumLockedView: View {
  let title: String
  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      WidgetBrand(label: "Premium")
      Spacer(minLength: 0)
      Image(systemName: "lock.fill").foregroundColor(NewziShared.blue)
      Text(title).font(.system(size: 15, weight: .bold)).foregroundColor(.primary).lineLimit(2)
      Text("Disponível no Newzi Premium.").font(.system(size: 12)).foregroundColor(.secondary).lineLimit(2)
      Spacer(minLength: 0)
    }
    .widgetURL(DeepLink.premium)
  }
}

/// One headline line: the topic in blue, the title below.
struct HeadlineRow: View {
  let story: WidgetStory
  var lines = 2
  var body: some View {
    Link(destination: DeepLink.story(story.id)) {
      VStack(alignment: .leading, spacing: 1) {
        if let topic = story.topic { Text(topic.uppercased()).font(.system(size: 9, weight: .heavy)).foregroundColor(NewziShared.blue).lineLimit(1) }
        Text(story.title).font(.system(size: 13, weight: .semibold)).foregroundColor(.primary).lineLimit(lines)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }
}

/// A game's line: both teams, the score (or kickoff time) and how it is going.
struct MatchLine: View {
  let match: WidgetMatch
  var body: some View {
    let kickoff = Date(timeIntervalSince1970: match.kickoff)
    VStack(alignment: .leading, spacing: 4) {
      Text(match.competition).font(.system(size: 10, weight: .bold)).foregroundColor(.secondary).lineLimit(1)
      HStack(spacing: 6) {
        Text(match.homeTla).font(.system(size: 17, weight: .heavy))
        if match.status == "SCHEDULED" {
          Text("x").font(.system(size: 13)).foregroundColor(.secondary)
        } else {
          Text("\(match.homeGoals ?? 0) x \(match.awayGoals ?? 0)").font(.system(size: 17, weight: .heavy)).foregroundColor(NewziShared.blue)
        }
        Text(match.awayTla).font(.system(size: 17, weight: .heavy))
      }
      Group {
        switch match.status {
        case "LIVE": Text("Ao vivo").foregroundColor(.red)
        case "FINISHED": Text("Fim de jogo").foregroundColor(.secondary)
        default: Text(kickoff, format: .dateTime.weekday(.abbreviated).hour().minute()).foregroundColor(.secondary)
        }
      }
      .font(.system(size: 11, weight: .semibold))
    }
  }
}
