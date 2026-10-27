// Analytics Newzi: the read-only panel of painel.newzi.app. Plain JavaScript, no build step; the API lives on the
// same host under /api/v1/admin and keeps the session in an HttpOnly cookie.
"use strict";

const API = "/api/v1/admin";
const $ = (selector) => document.querySelector(selector);
const content = $("#content");

const TITLES = {
  overview: "Visão geral", users: "Usuários", user: "Usuário", retention: "Retenção", briefings: "Briefing e áudio",
  content: "Conteúdo", notifications: "Notificações", subscriptions: "Assinaturas", football: "Esportes", system: "Sistema",
};
// Screens whose numbers depend on the period selector.
const WITH_PERIOD = new Set(["overview", "briefings", "content", "notifications", "subscriptions", "football"]);

// ------------------------------------------------------------------ helpers
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const num = (value) => (value === null || value === undefined ? "—" : Number(value).toLocaleString("pt-BR"));
const pct = (part, total) => (total ? `${Math.round((100 * part) / total)}%` : "—");
function when(value) {
  if (!value) return "—";
  const date = new Date(value);
  return isNaN(date) ? esc(value) : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
const day = (value) => (value ? value.split("-").reverse().join("/") : "—");
function bytes(value) {
  if (value === null || value === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}
const PLAN = { basic: "Básico", premium: "Premium", premium_manual: "Premium (painel)" };
const PLATFORM = { ANDROID: "Android", IOS: "iPhone" };

async function api(path) {
  const response = await fetch(API + path, { credentials: "same-origin" });
  if (response.status === 401) { showLogin(); throw new Error("signed out"); }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function card(label, value, hint) {
  return `<div class="card"><div class="label">${esc(label)}</div><div class="value">${value}</div>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
}
function panel(title, body, note) {
  return `<section class="panel"><h3>${esc(title)}</h3>${note ? `<p class="note">${note}</p>` : ""}${body}</section>`;
}
// rows: array of arrays of already-escaped cells; options.click: per-row data-href.
function table(headers, rows, options = {}) {
  if (!rows.length) return `<p class="muted">${options.empty || "Nada no período."}</p>`;
  const head = headers.map((h) => `<th>${esc(h)}</th>`).join("");
  const body = rows.map((cells, index) => {
    const href = options.links ? options.links[index] : null;
    return `<tr${href ? ` class="click" data-href="${esc(href)}"` : ""}>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table data-title="${esc(options.title || "")}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
// Vertical bars over days: [{day, value}].
function bars(series) {
  if (!series.length) return "";
  const width = 600, height = 160, bottom = 18, max = Math.max(1, ...series.map((p) => p.value));
  const step = width / series.length, barWidth = Math.max(1, step * 0.7);
  const rects = series.map((point, i) => {
    const h = ((height - bottom - 8) * point.value) / max;
    return `<rect class="bar" x="${(i * step + (step - barWidth) / 2).toFixed(1)}" y="${(height - bottom - h).toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}" rx="2"><title>${esc(day(point.day))}: ${num(point.value)}</title></rect>`;
  }).join("");
  const labels = [0, Math.floor(series.length / 2), series.length - 1].filter((v, i, a) => a.indexOf(v) === i)
    .map((i) => `<text class="axis" x="${(i * step + step / 2).toFixed(1)}" y="${height - 4}" text-anchor="middle">${esc(day(series[i].day).slice(0, 5))}</text>`).join("");
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img">`
    + `<line class="grid-line" x1="0" x2="${width}" y1="${height - bottom}" y2="${height - bottom}"/>${rects}${labels}`
    + `<text class="axis" x="2" y="10">máx. ${num(max)}</text></svg>`;
}
// Horizontal bars: [[label, value]].
function hbars(items) {
  if (!items.length) return `<p class="muted">Sem dados.</p>`;
  const max = Math.max(1, ...items.map(([, v]) => v));
  return items.map(([label, value]) =>
    `<div class="hbar"><span title="${esc(label)}">${esc(label)}</span><div class="track"><div class="fill" data-width="${(100 * value) / max}"></div></div><b>${num(value)}</b></div>`).join("");
}
// Widths are set through the CSSOM (allowed by the CSP) instead of inline style attributes.
function applyWidths() {
  content.querySelectorAll("[data-width]").forEach((el) => { el.style.width = `${el.dataset.width}%`; });
}
const statusPill = (status) => {
  const tone = { READY: "ok", SENT: "ok", OK: "ok", COMPLETED: "ok", FAILED: "error", BROKEN: "error", FAILING: "error",
    DEGRADED: "warn", SILENT: "warn", PENDING: "", RUNNING: "", CANCELLED: "warn" }[status] ?? "";
  return `<span class="pill ${tone}">${esc(status ?? "—")}</span>`;
};
const entries = (object) => Object.entries(object || {}).sort((a, b) => b[1] - a[1]);
const activityNote = (since) => since
  ? `Usuários ativos contam a partir de ${day(since)}, quando o painel começou a registrar o uso.`
  : "Usuários ativos começam a ser contados a partir da publicação do painel.";

// ------------------------------------------------------------------ screens
const screens = {};

screens.overview = async (period) => {
  const d = await api(`/overview?days=${period}`);
  const alerts = d.alerts.length
    ? d.alerts.map((a) => `<div class="alert ${esc(a.level)}">${esc(a.text)}</div>`).join("")
    : `<div class="alert ok">Tudo funcionando: nenhum aviso agora.</div>`;
  const devices = d.devices.map((r) => `${esc(PLATFORM[r.platform] || r.platform)}: ${num(r.n)}`).join(" · ") || "—";
  const b = d.briefings;
  return `<div class="alerts">${alerts}</div>
    <div class="grid">
      ${card("Ativos hoje", num(d.dau))}${card("Ativos 7 dias", num(d.wau))}${card("Ativos 30 dias", num(d.mau))}
      ${card("Contas", num(d.users_total), `${num(d.signups)} novas no período`)}
      ${card("Premium", num(d.plans.premium), `${num(d.plans.paid)} pagos · ${num(d.plans.manual)} pelo painel`)}
      ${card("Aparelhos com push", num(d.devices.reduce((s, r) => s + r.n, 0)), devices)}
      ${card("Briefings entregues", num(b.delivered), `${num(b.with_audio)} com áudio`)}
      ${card("Áudio ouvido", pct(b.listened, b.with_audio), `${num(b.completed)} até o fim`)}
      ${card("Pushes enviados", num(d.pushes.SENT || 0), `${num(d.pushes.FAILED || 0)} falharam`)}
    </div>
    <div class="cols">
      ${panel("Usuários ativos por dia", bars(d.series.active), activityNote(d.since_activity))}
      ${panel("Cadastros por dia", bars(d.series.signups))}
    </div>`;
};

let usersQuery = { query: "", plan: "", page: 1 };
screens.users = async () => {
  const q = new URLSearchParams({ query: usersQuery.query, plan: usersQuery.plan, page: usersQuery.page });
  const d = await api(`/users?${q}`);
  const rows = d.users.map((u) => [esc(u.email), esc(u.display_name), `<span class="pill">${esc(PLAN[u.plan])}</span>`,
    esc(PLATFORM[u.platform] || u.platform || "—"), esc(u.app_version || "—"), when(u.created_at), day(u.last_active), num(u.active_days)]);
  const pages = Math.max(1, Math.ceil(d.total / d.per_page));
  return panel(`${num(d.total)} contas`, `
    <form class="search" id="users-search">
      <input name="query" placeholder="Buscar por e-mail, nome ou ID" value="${esc(usersQuery.query)}">
      <select name="plan">
        ${[["", "Todos os planos"], ["basic", "Básico"], ["premium", "Premium"], ["premium_manual", "Premium (painel)"]]
          .map(([v, l]) => `<option value="${v}"${usersQuery.plan === v ? " selected" : ""}>${l}</option>`).join("")}
      </select>
      <button type="submit">Buscar</button>
    </form><br>
    ${table(["E-mail", "Nome", "Plano", "Aparelho", "Versão", "Cadastro", "Último uso", "Dias de uso"], rows,
      { links: d.users.map((u) => `#/users/${encodeURIComponent(u.id)}`), title: "usuarios", empty: "Nenhuma conta encontrada." })}
    <div class="pager">
      <button class="ghost" data-page="${d.page - 1}"${d.page <= 1 ? " disabled" : ""}>Anterior</button>
      <span class="muted">Página ${d.page} de ${pages}</span>
      <button class="ghost" data-page="${d.page + 1}"${d.page >= pages ? " disabled" : ""}>Próxima</button>
    </div>`);
};

screens.user = async (_period, id) => {
  const d = await api(`/users/${encodeURIComponent(id)}`);
  const u = d.user, p = d.preferences || {}, plan = d.plan;
  const facts = (pairs) => `<dl class="facts">${pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
  const settings = Object.entries(d.notification_settings).filter(([k]) => k.endsWith("_enabled"))
    .map(([k, v]) => `${esc(k.replace("_enabled", ""))}: ${v ? "sim" : "não"}`).join(" · ");
  return `<p><a href="#/users">← Usuários</a></p>
    <div class="cols">
      ${panel("Conta", facts([["E-mail", esc(u.email)], ["Nome", esc(u.display_name)], ["ID", esc(u.id)], ["Cadastro", when(u.created_at)],
        ["Status", esc(u.status)], ["Onboarding", esc(u.onboarding_status)], ["Idioma", esc(u.language)], ["Fuso", esc(u.timezone)]]))}
      ${panel("Plano", facts([["Plano", plan.tier === "premium" ? `Premium${plan.store === "manual" ? " (painel)" : ""}` : "Básico"],
        ["Período", esc(plan.period || "—")], ["Origem", esc(plan.store || "—")], ["Início", when(plan.started_at)],
        ["Vence", when(plan.expires_at)], ["Renova", plan.will_renew ? "sim" : "não"]]))}
      ${panel("Preferências", facts([["Tópicos", esc((p.topics || []).join(", ") || "—")], ["Horário", esc(p.briefing_time || "—")],
        ["Tamanho", esc(p.briefing_size ?? "—")], ["Duração", esc(p.briefing_length || "—")], ["Voz", esc(p.audio_voice_id || "—")],
        ["Áudio", p.audio_enabled ? "sim" : "não"], ["Abrangência", esc(p.country_scope || "—")],
        ["Extras", esc(d.briefing_slots.map((s) => `${s.delivery_time}${s.theme ? " " + s.theme : ""}${s.enabled ? "" : " (off)"}`).join(", ") || "—")]]))}
      ${panel("Uso", facts([["Dias de uso", `${num(d.activity.length)}${d.activity.length ? ` (último ${day(d.activity[0])})` : ""}`],
        ["Salvos", num(d.counts.saved_stories)], ["Briefings salvos", num(d.counts.saved_briefings)], ["Coleções", num(d.counts.collections)],
        ["Alertas", esc(d.keyword_alerts.join(", ") || "—")], ["Histórias seguidas", num(d.counts.followed_stories)],
        ["Times", esc(d.favorite_teams.join(", ") || "—")], ["Avaliações", num(d.counts.feedback)]]))}
    </div>
    ${panel("Aparelhos", table(["Plataforma", "Versão", "Idioma", "Push", "Desde", "Visto por último", "Inválido desde"],
      d.devices.map((r) => [esc(PLATFORM[r.platform] || r.platform), esc(r.app_version || "—"), esc(r.locale || "—"), r.enabled ? "ativo" : "desligado",
        when(r.created_at), when(r.last_seen_at), when(r.invalidated_at)]), { empty: "Nenhum aparelho registrado.", title: "aparelhos" }),
      settings ? `Notificações: ${settings}` : "")}
    ${panel("Briefings recebidos", table(["Dia", "Tipo", "Horário", "Status", "Áudio", "Voz", "Ouviu", "Erro"],
      d.deliveries.map((r) => [day(r.local_date), esc(r.kind + (r.theme ? ` · ${r.theme}` : "")), esc(r.delivery_time), statusPill(r.status),
        statusPill(r.audio_status), esc(r.selected_voice_id || "—"),
        r.completed_at ? "até o fim" : r.progress_seconds ? pct(r.progress_seconds, r.duration_seconds) : "—", esc(r.generation_error_code || "")]),
      { empty: "Nenhum briefing ainda.", title: "briefings" }))}
    ${panel("Notificações recebidas", table(["Tipo", "Status", "Agendada", "Erro"],
      d.notifications.map((r) => [esc(r.notification_type), statusPill(r.status), when(r.scheduled_for), esc(r.last_error || "")]),
      { empty: "Nenhuma notificação ainda.", title: "notificacoes" }))}`;
};

screens.retention = async () => {
  const d = await api("/retention?weeks=12");
  const rate = (hit, due) => (due ? `${pct(hit, due)} <span class="muted">(${hit}/${due})</span>` : "—");
  return `${panel("Coortes semanais de cadastro", table(["Semana", "Cadastros", "Voltou no D1", "Voltou no D7", "Voltou no D30"],
      d.cohorts.map((c) => [day(c.week), num(c.users), rate(c.d1, c.d1_due), rate(c.d7, c.d7_due), rate(c.d30, c.d30_due)]),
      { title: "coortes", empty: "Sem cadastros nas últimas semanas." }),
    `${activityNote(d.since_activity)} "Voltou" = usou o app no dia ou nos dois dias seguintes.`)}
    ${panel("Em risco: sem usar há mais de 7 dias", table(["E-mail", "Último uso"],
      d.at_risk.map((r) => [esc(r.email), day(r.last_active)]), { links: d.at_risk.map((r) => `#/users/${encodeURIComponent(r.id)}`), title: "em_risco", empty: "Ninguém em risco." }))}`;
};

screens.briefings = async (period) => {
  const d = await api(`/briefings?days=${period}`);
  const totals = d.per_day.reduce((s, r) => { for (const k in r) if (k !== "day") s[k] = (s[k] || 0) + r[k]; return s; }, {});
  return `<div class="grid">
      ${card("Briefings", num(totals.total), `${num(totals.ready)} prontos`)}
      ${card("Com áudio", pct(totals.audio_ready, totals.total), `${num(totals.audio_failed)} áudios falharam`)}
      ${card("Ouvidos", pct(totals.listened, totals.audio_ready), `${num(totals.listened)} começaram`)}
      ${card("Até o fim", pct(totals.completed, totals.listened), `${num(totals.completed)} terminaram`)}
    </div>
    <div class="cols">
      ${panel("Briefings por dia", bars(d.per_day.map((r) => ({ day: r.day, value: r.total }))))}
      ${panel("Onde param de ouvir", hbars(d.stop_points.map((s) => [`${s.decile}–${s.decile + 10}%`, s.n])), "Entre quem começou e não terminou.")}
    </div>
    <div class="cols">
      ${panel("Tipos", hbars(entries(d.kinds)))}
      ${panel("Vozes", hbars(entries(d.voices)))}
      ${panel("Jobs de geração", hbars(entries(d.generation_jobs)))}
      ${panel("Jobs de áudio", hbars(entries(d.audio_jobs)))}
    </div>
    ${panel("Por dia", table(["Dia", "Total", "Prontos", "Áudio pronto", "Áudio falhou", "Ouvidos", "Até o fim"],
      d.per_day.slice().reverse().map((r) => [day(r.day), num(r.total), num(r.ready), num(r.audio_ready), num(r.audio_failed), num(r.listened), num(r.completed)]),
      { title: "briefings_por_dia" }))}
    <div class="cols">
      ${panel("Erros de geração", table(["Código", "Vezes"], d.errors.map(([c, n]) => [esc(c), num(n)]), { empty: "Nenhum erro.", title: "erros" }))}
      ${panel("Trocas de voz", table(["Motivo", "Vezes"], d.voice_fallbacks.map(([c, n]) => [esc(c), num(n)]), { empty: "Nenhuma troca.", title: "trocas_voz" }))}
      ${panel("Tempo das fases do áudio", table(["Fase", "Média", "Vezes"], d.audio_phases.map((r) => [esc(r.phase), `${(r.avg_ms / 1000).toFixed(1)} s`, num(r.n)]), { title: "fases_audio" }))}
      ${panel("Resumo na hora (Gerar agora)", hbars(d.on_demand.map((r) => [r.status, r.n])))}
    </div>`;
};

screens.content = async (period) => {
  const d = await api(`/content?days=${Math.min(period, 30)}`);
  const s = d.sources;
  return `<div class="grid">
      ${card("Matérias no índice", num(d.articles_total))}
      ${Object.entries(s.by_status).map(([k, v]) => card(`Fontes ${k}`, num(v))).join("")}
    </div>
    ${s.error ? `<div class="alert warn">Saúde das fontes indisponível: ${esc(s.error)}</div>` : ""}
    <div class="cols">
      ${panel("Matérias novas por dia", bars(d.indexed_per_day))}
      ${panel("Tópicos mais seguidos", hbars(d.topics_followed.map((t) => [t.name, t.users])))}
    </div>
    ${panel("Fontes que precisam de atenção", table(["Fonte", "Status", "Diagnóstico", "Falhas seguidas", "Último sucesso", "24 h", "7 dias"],
      s.attention.map((r) => [esc(r.name || r.id), statusPill(r.status), esc(r.diagnosis || "—"), num(r.consecutive_failures),
        when(r.last_success_at), num(r.articles_24h), num(r.articles_7d)]), { empty: "Todas as fontes estão OK.", title: "fontes" }))}
    ${panel("Últimas coletas", table(["Início", "Status", "Fontes", "Novas", "Atualizadas"],
      d.runs.map((r) => [when(r.started_at), statusPill(r.status), `${num(r.sources_successful)}/${num(r.sources_attempted)}`,
        num(r.articles_new), num(r.articles_updated)]), { title: "coletas" }))}
    ${panel("Avaliações das notícias", hbars(d.ratings.map((r) => [`${r.rating} ★`, r.n])))}`;
};

screens.notifications = async (period) => {
  const d = await api(`/notifications?days=${period}`);
  const total = d.settings.total || 0;
  const optins = Object.entries(d.settings).filter(([k]) => k !== "total").map(([k, v]) => [k.replace("_enabled", ""), v || 0]);
  return `<div class="cols">
      ${panel("Aparelhos", table(["Plataforma", "Ativos", "Inválidos", "Total"],
        d.devices.map((r) => [esc(PLATFORM[r.platform] || r.platform), num(r.active), num(r.invalidated), num(r.total)]), { title: "aparelhos" }))}
      ${panel(`Opções ligadas (de ${num(total)} contas com ajustes)`, hbars(optins))}
    </div>
    ${panel("Pushes enviados por dia", bars(d.sent_per_day))}
    ${panel("Por tipo", table(["Tipo", "Enviados", "Falharam", "Cancelados", "Pendentes"],
      Object.entries(d.by_type).map(([t, s]) => [esc(t), num(s.SENT || 0), num(s.FAILED || 0), num(s.CANCELLED || 0), num((s.PENDING || 0) + (s.RUNNING || 0))]),
      { title: "push_por_tipo" }), "Aberturas dos pushes chegam com a versão 1.1 do app.")}
    ${panel("Motivos de falha", table(["Erro", "Vezes"], d.errors.map((r) => [esc(r.last_error || "—"), num(r.n)]), { empty: "Nenhuma falha.", title: "falhas_push" }))}`;
};

screens.subscriptions = async (period) => {
  const d = await api(`/subscriptions?days=${period}`);
  const flags = `Vendas ${d.billing.enabled ? "ligadas" : "desligadas"} (BILLING_ENABLED) · Limites do Premium ${d.billing.enforced ? "aplicados" : "desligados"} (PREMIUM_ENFORCED)`;
  return `<div class="grid">
      ${card("Premium agora", num(d.plans.premium), `${num(d.plans.paid)} pagos · ${num(d.plans.manual)} pelo painel`)}
      ${card("Mensal", num(d.plans.monthly))}${card("Anual", num(d.plans.annual))}
      ${card("Conversão", pct(d.conversion.paid, d.conversion.users), "pagantes ÷ contas")}
      ${card("Renovação desligada", num(d.renewal_off), "vão acabar no vencimento")}
    </div>
    <p class="muted">${flags}. Receita detalhada (testes grátis, reembolsos, MRR) vem do RevenueCat na etapa 3.</p>
    <div class="cols">
      ${panel("Novas assinaturas por dia", bars(d.started_per_day))}
      ${panel("Por status (pagas)", hbars(entries(d.by_status)))}
      ${panel("Por loja (ativas)", hbars(entries(d.by_store)))}
    </div>
    ${panel("Assinaturas", table(["E-mail", "Origem", "Plano", "Status", "Início", "Vence", "Renova"],
      d.subscriptions.map((r) => [esc(r.email || r.user_id), esc(r.store), esc(r.period), r.active ? statusPill(r.status) : `<span class="muted">${esc(r.status)} (vencida)</span>`,
        when(r.started_at), when(r.expires_at), r.auto_renew ? "sim" : "não"]),
      { links: d.subscriptions.map((r) => `#/users/${encodeURIComponent(r.user_id)}`), title: "assinaturas", empty: "Nenhuma assinatura ainda." }))}`;
};

screens.football = async (period) => {
  const d = await api(`/football?days=${period}`);
  return `<div class="grid">
      ${card("Usuários com time", num(d.users_with_teams))}
      ${card("Jogos seguidos", num(d.followed_matches), "no período")}
      ${card("Placar ao vivo (iPhone)", num(d.live_activities), "no período")}
    </div>
    <div class="cols">
      ${panel("Times favoritos", hbars(d.teams.map((t) => [t.name, t.users])))}
      ${panel("Áudios de jogo", hbars(d.match_audio.map((r) => [r.status, r.n])))}
      ${panel("Alertas de time", table(["Tipo", "Status", "Vezes"], d.team_pushes.map((r) => [esc(r.notification_type), statusPill(r.status), num(r.n)]), { title: "alertas_time" }))}
    </div>`;
};

screens.system = async () => {
  const d = await api("/system");
  const disk = d.disk ? `${bytes(d.disk.used)} de ${bytes(d.disk.total)} (${d.disk.percent}%)` : "—";
  const backup = d.backup ? (d.backup.latest ? `${when(d.backup.at)} · ${bytes(d.backup.size)} · ${num(d.backup.count)} cópias` : "nenhuma cópia encontrada") : "pasta sem acesso";
  return `<div class="grid">
      ${card("Fila de geração", num(d.queues.generation))}${card("Fila de áudio", num(d.queues.audio))}
      ${card("Fila de push", num(d.queues.notifications))}${card("Gerar agora em andamento", num(d.queues.on_demand))}
    </div>
    <div class="cols">
      ${panel("Servidor", `<dl class="facts"><dt>Disco</dt><dd>${disk}</dd><dt>Banco</dt><dd>${esc(d.database.dialect)} · ${bytes(d.database.size)}</dd>
        <dt>Migrações</dt><dd>${esc(d.database.migrations.join(", "))}</dd><dt>Último backup</dt><dd>${backup}</dd>
        <dt>Última coleta</dt><dd>${when(d.last_ingestion.started_at)} ${d.last_ingestion.status ? statusPill(d.last_ingestion.status) : ""}</dd></dl>`)}
      ${panel("Configuração", `<dl class="facts">${Object.entries(d.settings).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v ?? "—")}</dd>`).join("")}</dl>`)}
    </div>
    ${panel("Workers", table(["Worker", "Papéis", "Último ciclo", "Último sucesso", "Ciclo", "Ciclos", "Erro"],
      d.workers.map((w) => [esc(w.worker_id), esc(w.roles), when(w.last_cycle_at), when(w.last_success_at), `${num(w.cycle_ms)} ms`, num(w.cycles),
        `<span class="wrap">${esc(w.last_error || "")}</span>`]), { empty: "Nenhum worker ativo nas últimas 24 h.", title: "workers" }))}
    ${panel("Acessos ao painel", table(["Quando", "Endereço", "Resultado"],
      d.logins.map((r) => [when(r.created_at), esc(r.client || "—"), r.ok ? statusPill("OK") : statusPill("FAILED")]), { title: "acessos" }))}`;
};

// ------------------------------------------------------------------ routing
function route() {
  const [, screen = "overview", id] = location.hash.replace(/^#/, "").split("/");
  return screen === "users" && id ? { screen: "user", id: decodeURIComponent(id) } : { screen: screens[screen] ? screen : "overview" };
}

let rendering = 0;
async function render() {
  const { screen, id } = route();
  const ticket = ++rendering;
  $("#title").textContent = TITLES[screen];
  $("#period").hidden = !WITH_PERIOD.has(screen);
  document.querySelectorAll(".sidebar a").forEach((a) => a.classList.toggle("active", a.dataset.screen === (screen === "user" ? "users" : screen)));
  content.innerHTML = `<div class="loading">Carregando…</div>`;
  try {
    const html = await screens[screen](Number($("#period").value), id);
    if (ticket !== rendering) return;
    content.innerHTML = html;
    applyWidths();
  } catch (error) {
    if (ticket === rendering && error.message !== "signed out") {
      content.innerHTML = `<div class="alert error">Não foi possível carregar: ${esc(error.message)}</div>`;
    }
  }
}

content.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-href]");
  if (row) { location.hash = row.dataset.href; return; }
  const page = event.target.closest("button[data-page]");
  if (page) { usersQuery.page = Number(page.dataset.page); render(); }
});
content.addEventListener("submit", (event) => {
  if (event.target.id !== "users-search") return;
  event.preventDefault();
  const form = new FormData(event.target);
  usersQuery = { query: form.get("query").trim(), plan: form.get("plan"), page: 1 };
  render();
});

function exportCsv() {
  const tables = content.querySelectorAll("table");
  if (!tables.length) return;
  const cell = (text) => `"${text.replace(/\s+/g, " ").trim().replace(/"/g, '""')}"`;
  const lines = [];
  tables.forEach((t, i) => {
    if (i) lines.push("");
    lines.push(cell(t.dataset.title || `tabela_${i + 1}`));
    t.querySelectorAll("tr").forEach((tr) => lines.push([...tr.children].map((c) => cell(c.textContent)).join(";")));
  });
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `newzi-${route().screen}-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// ------------------------------------------------------------------ session
function showLogin() {
  $("#app").hidden = true;
  $("#login").hidden = false;
  $("#login-email").focus();
}
function showApp() {
  $("#login").hidden = true;
  $("#app").hidden = false;
  render();
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = $("#login-error"), button = event.target.querySelector("button");
  error.hidden = true;
  button.disabled = true;
  try {
    const response = await fetch(`${API}/login`, {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("#login-email").value, password: $("#login-password").value }),
    });
    if (response.ok) { $("#login-password").value = ""; showApp(); return; }
    error.textContent = response.status === 429 ? "Muitas tentativas erradas. Espere 15 minutos e tente de novo."
      : response.status === 401 ? "E-mail ou senha incorretos." : `Erro ${response.status}.`;
    error.hidden = false;
  } catch {
    error.textContent = "Sem conexão com o servidor.";
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});

$("#logout").addEventListener("click", async () => {
  await fetch(`${API}/logout`, { method: "POST", credentials: "same-origin" }).catch(() => {});
  showLogin();
});
$("#period").addEventListener("change", render);
$("#refresh").addEventListener("click", render);
$("#export").addEventListener("click", exportCsv);
window.addEventListener("hashchange", () => { if (!$("#app").hidden) render(); });

fetch(`${API}/session`, { credentials: "same-origin" })
  .then((response) => (response.ok ? showApp() : showLogin()))
  .catch(showLogin);
