import AppIntents
import SwiftUI
import WidgetKit

// Premium widgets the reader configures (iOS 17): one topic's headlines, or one favourite team's game.
// The choices come from what the app shared (the reader's topics and favourite teams).

@available(iOS 17.0, *)
struct TopicEntity: AppEntity {
  let id: String
  let name: String
  static var typeDisplayRepresentation: TypeDisplayRepresentation = "Assunto"
  static var defaultQuery = TopicQuery()
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
}

@available(iOS 17.0, *)
struct TopicQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [TopicEntity] { all().filter { identifiers.contains($0.id) } }
  func suggestedEntities() async throws -> [TopicEntity] { all() }
  func defaultResult() async -> TopicEntity? { all().first }
  private func all() -> [TopicEntity] { (WidgetPayload.load()?.topics ?? []).map { TopicEntity(id: $0.id, name: $0.name) } }
}

@available(iOS 17.0, *)
struct TopicIntent: WidgetConfigurationIntent {
  static var title: LocalizedStringResource = "Assunto"
  static var description = IntentDescription("Escolha o assunto do widget.")
  @Parameter(title: "Assunto") var topic: TopicEntity?
}

@available(iOS 17.0, *)
struct TopicEntry: TimelineEntry {
  let date: Date
  let payload: WidgetPayload?
  let topicId: String?
}

@available(iOS 17.0, *)
struct TopicProvider: AppIntentTimelineProvider {
  func placeholder(in context: Context) -> TopicEntry { TopicEntry(date: Date(), payload: .sample, topicId: "SPORTS") }
  func snapshot(for configuration: TopicIntent, in context: Context) async -> TopicEntry {
    TopicEntry(date: Date(), payload: context.isPreview ? .sample : WidgetPayload.load(), topicId: configuration.topic?.id ?? "SPORTS")
  }
  func timeline(for configuration: TopicIntent, in context: Context) async -> Timeline<TopicEntry> {
    let payload = WidgetPayload.load()
    let entry = TopicEntry(date: Date(), payload: payload, topicId: configuration.topic?.id ?? payload?.topics.first?.id)
    return Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(30 * 60)))
  }
}

@available(iOS 17.0, *)
struct TopicWidget: Widget {
  let kind = "NewziTopic"
  var body: some WidgetConfiguration {
    AppIntentConfiguration(kind: kind, intent: TopicIntent.self, provider: TopicProvider()) { entry in
      TopicWidgetView(entry: entry)
    }
    .configurationDisplayName("Seu assunto")
    .description("As últimas notícias de um assunto que você escolhe. Recurso Premium.")
    .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
  }
}

@available(iOS 17.0, *)
struct TopicWidgetView: View {
  @Environment(\.widgetFamily) var family
  let entry: TopicEntry
  var body: some View {
    Group {
      if let payload = entry.payload, payload.premium {
        if let topic = payload.topics.first(where: { $0.id == entry.topicId }) ?? payload.topics.first {
          VStack(alignment: .leading, spacing: 7) {
            WidgetBrand(label: topic.name)
            ForEach(topic.headlines.prefix(family == .systemLarge ? 6 : family == .systemMedium ? 3 : 2)) { story in
              HeadlineRow(story: story, lines: family == .systemSmall ? 3 : 2)
            }
            Spacer(minLength: 0)
          }
        } else {
          Text("Escolha um assunto segurando o widget.").font(.system(size: 13, weight: .semibold))
        }
      } else {
        PremiumLockedView(title: "Widget por assunto")
      }
    }
    .widgetBackground(Color(UIColor.systemBackground))
  }
}

@available(iOS 17.0, *)
struct TeamEntity: AppEntity {
  let id: Int
  let name: String
  static var typeDisplayRepresentation: TypeDisplayRepresentation = "Time"
  static var defaultQuery = TeamQuery()
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
}

@available(iOS 17.0, *)
struct TeamQuery: EntityQuery {
  func entities(for identifiers: [Int]) async throws -> [TeamEntity] { all().filter { identifiers.contains($0.id) } }
  func suggestedEntities() async throws -> [TeamEntity] { all() }
  func defaultResult() async -> TeamEntity? { all().first }
  private func all() -> [TeamEntity] { (WidgetPayload.load()?.teams ?? []).map { TeamEntity(id: $0.id, name: $0.name) } }
}

@available(iOS 17.0, *)
struct TeamIntent: WidgetConfigurationIntent {
  static var title: LocalizedStringResource = "Time"
  static var description = IntentDescription("Escolha o time do widget.")
  @Parameter(title: "Time") var team: TeamEntity?
}

@available(iOS 17.0, *)
struct TeamEntry: TimelineEntry {
  let date: Date
  let payload: WidgetPayload?
  let teamId: Int?
}

@available(iOS 17.0, *)
struct TeamProvider: AppIntentTimelineProvider {
  func placeholder(in context: Context) -> TeamEntry { TeamEntry(date: Date(), payload: .sample, teamId: 1) }
  func snapshot(for configuration: TeamIntent, in context: Context) async -> TeamEntry {
    TeamEntry(date: Date(), payload: context.isPreview ? .sample : WidgetPayload.load(), teamId: configuration.team?.id)
  }
  func timeline(for configuration: TeamIntent, in context: Context) async -> Timeline<TeamEntry> {
    let payload = WidgetPayload.load()
    let entry = TeamEntry(date: Date(), payload: payload, teamId: configuration.team?.id ?? payload?.teams.first?.id)
    // A live game is refreshed more often (the app also reloads the widget when the score changes).
    let live = payload?.teams.contains { $0.match?.status == "LIVE" } ?? false
    return Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(live ? 5 * 60 : 30 * 60)))
  }
}

@available(iOS 17.0, *)
struct TeamWidget: Widget {
  let kind = "NewziTeam"
  var body: some WidgetConfiguration {
    AppIntentConfiguration(kind: kind, intent: TeamIntent.self, provider: TeamProvider()) { entry in
      TeamWidgetView(entry: entry)
    }
    .configurationDisplayName("Meu time")
    .description("O próximo jogo ou o placar ao vivo do seu time. Recurso Premium.")
    .supportedFamilies([.systemSmall, .systemMedium])
  }
}

@available(iOS 17.0, *)
struct TeamWidgetView: View {
  let entry: TeamEntry
  var body: some View {
    Group {
      if let payload = entry.payload, payload.premium {
        if let team = payload.teams.first(where: { $0.id == entry.teamId }) ?? payload.teams.first {
          VStack(alignment: .leading, spacing: 6) {
            WidgetBrand(label: team.name)
            Spacer(minLength: 0)
            if let match = team.match { MatchLine(match: match) } else { Text("Sem jogos nos próximos dias.").font(.system(size: 13, weight: .semibold)).foregroundColor(.secondary) }
            Spacer(minLength: 0)
          }
          .widgetURL(DeepLink.football)
        } else {
          Text("Escolha um time favorito no app (Esportes).").font(.system(size: 13, weight: .semibold))
        }
      } else {
        PremiumLockedView(title: "Widget do seu time")
      }
    }
    .widgetBackground(Color(UIColor.systemBackground))
  }
}
