from pathlib import Path
from collections import Counter

def write_editorial_report(articles, events, ranked, directory=None):
    from ..paths import ENGINE_OUTPUT
    directory = directory or ENGINE_OUTPUT
    path=Path(directory); path.mkdir(parents=True,exist_ok=True); counts=Counter(a.content_genre for a in articles); eligible=Counter(e.content_genre for e in ranked); excluded=Counter(e.content_genre for e in events if e not in ranked); lines=["# EDITORIAL REPORT", "", "## Genre distribution", ""]
    lines += [f"- {k}: {v}" for k,v in sorted(counts.items())] + ["", "## Eligible by genre", ""] + [f"- {k}: {v}" for k,v in sorted(eligible.items())] + ["", "## Excluded by genre", ""] + [f"- {k}: {v}" for k,v in sorted(excluded.items())] + ["", "## Examples", ""]
    for genre in sorted(counts): lines.append(f"- {genre}: {next((a.title for a in articles if a.content_genre==genre), '')}")
    (path/"editorial_report.md").write_text("\n".join(lines),encoding="utf-8")

