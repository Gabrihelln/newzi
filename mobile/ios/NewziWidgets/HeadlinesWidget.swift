import SwiftUI
import WidgetKit

struct HeadlinesProvider: TimelineProvider {
  func placeholder(in context: Context) -> WidgetEntry { WidgetEntry(date: Date(), payload: .sample) }

  func getSnapshot(in context: Context, completion: @escaping (WidgetEntry) -> Void) {
    completion(WidgetEntry(date: Date(), payload: context.isPreview ? .sample : (WidgetPayload.load() ?? .sample)))
  }

  func getTimeline(in context: Context, completion: @escaping (Timeline<WidgetEntry>) -> Void) {
    // The app reloads the widgets whenever it has new headlines; this is only a fallback refresh.
    let entry = WidgetEntry(date: Date(), payload: WidgetPayload.load())
    completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(30 * 60))))
  }
}

/// "Destaques do dia": the briefing's headlines. Small is for everyone; medium and large are Premium.
struct HeadlinesWidget: Widget {
  let kind = "NewziHeadlines"

  var body: some WidgetConfiguration {
    StaticConfiguration(kind: kind, provider: HeadlinesProvider()) { entry in
      HeadlinesView(entry: entry)
    }
    .configurationDisplayName("Destaques do dia")
    .description("As principais notícias do seu resumo. Tamanhos médio e grande com o Premium.")
    .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
  }
}

struct HeadlinesView: View {
  @Environment(\.widgetFamily) var family
  let entry: WidgetEntry

  var body: some View {
    content
      .padding(family == .systemSmall ? 0 : 2)
      .widgetBackground(Color(UIColor.systemBackground))
  }

  @ViewBuilder var content: some View {
    if let payload = entry.payload, let briefing = payload.briefing {
      if family != .systemSmall && !payload.premium {
        PremiumLockedView(title: "Mais notícias em tamanhos maiores")
      } else {
        switch family {
        case .systemSmall: small(briefing)
        case .systemLarge: list(briefing, count: 6)
        default: list(briefing, count: 3)
        }
      }
    } else {
      VStack(alignment: .leading, spacing: 6) {
        WidgetBrand()
        Spacer(minLength: 0)
        Text("Abra o Newzi para ver os destaques do dia.").font(.system(size: 13, weight: .semibold)).foregroundColor(.primary)
        Spacer(minLength: 0)
      }
      .widgetURL(DeepLink.briefing)
    }
  }

  func small(_ briefing: WidgetBriefing) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      WidgetBrand()
      Spacer(minLength: 0)
      if let first = briefing.headlines.first {
        if let topic = first.topic { Text(topic.uppercased()).font(.system(size: 9, weight: .heavy)).foregroundColor(NewziShared.blue).lineLimit(1) }
        Text(first.title).font(.system(size: 14, weight: .bold)).foregroundColor(.primary).lineLimit(4)
      }
      Spacer(minLength: 0)
      Text(briefing.next).font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary).lineLimit(1)
    }
    .widgetURL(briefing.headlines.first.map { DeepLink.story($0.id) } ?? DeepLink.briefing)
  }

  func list(_ briefing: WidgetBriefing, count: Int) -> some View {
    VStack(alignment: .leading, spacing: 7) {
      WidgetBrand(label: briefing.title)
      ForEach(briefing.headlines.prefix(count)) { story in HeadlineRow(story: story, lines: count > 3 ? 2 : 1) }
      Spacer(minLength: 0)
      Link(destination: DeepLink.briefing) {
        HStack(spacing: 4) {
          Image(systemName: "play.circle.fill").foregroundColor(NewziShared.blue)
          Text("Ouvir o resumo · \(briefing.next)").font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary).lineLimit(1)
        }
      }
    }
  }
}
