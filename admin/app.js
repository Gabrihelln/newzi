// Analytics Newzi: the read-only panel of painel.newzi.app. Plain JavaScript, no build step; the API lives on the
// same host under /api/v1/admin and keeps the session in an HttpOnly cookie.
"use strict";

const API = "/api/v1/admin";
const $ = (selector) => document.querySelector(selector);
const content = $("#content");

const TITLES = {
  overview: "Visão geral", users: "Usuários", user: "Usuário", retention: "Retenção", briefings: "Briefing e áudio",
  content: "Conteúdo", notifications: "Notificações", subscriptions: "Assinaturas", football: "Esportes", system: "Sistema",
  premium: "Dar Premium", push: "Enviar push",
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

// Changes carry the panel's own header (the API refuses them without it) and return the API's error message.
async function send(method, path, body) {
  const response = await fetch(API + path, {
    method, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Newzi-Panel": "1" },
    body: JSON.stringify(body || {}),
  });
  if (response.status === 401) { showLogin(); throw new Error("Sessão encerrada. Entre de novo."); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(ERRORS[data.error?.message] || data.error?.message || `Erro ${response.status}`);
  return data;
}
// The API speaks English; the panel shows these in Portuguese.
const ERRORS = {
  "the end date must not come before the start date": "A data final não pode ser antes da inicial.",
  "the end date must come after the start date": "A data final precisa ser depois da inicial.",
  "the end date is already past": "A data final já passou.",
  "inform at least one e-mail": "Informe pelo menos um e-mail.",
  "dates must be YYYY-MM-DD": "Preencha as duas datas.",
  "title and body are required": "Preencha o título e o texto.",
  "scheduled_for is in the past": "O horário agendado já passou.",
  "type ENVIAR to confirm": "Digite ENVIAR para confirmar.",
  "url must be an https address": "O link precisa começar com https://",
  "image must be an https address": "A imagem precisa ser um link https://",
  "only a scheduled campaign can be changed": "Esse envio já saiu ou foi cancelado.",
  "only a scheduled campaign can be cancelled": "Esse envio já saiu ou foi cancelado.",
  "only a scheduled campaign can be sent": "Esse envio já saiu ou foi cancelado.",
  "grant not found or already ended": "Esse Premium já foi retirado.",
};
function flash(text, level = "ok") {
  const box = document.getElementById("flash");
  if (!box) return;
  box.className = `alert ${level}`;
  box.textContent = text;
  box.hidden = false;
  box.scrollIntoView({ block: "nearest" });
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
      ${panel("Plano", facts([["Plano", plan.tier === "premium" ? `Premium${plan.source === "courtesy" ? " (painel)" : ""}` : "Básico"],
        ["Período", esc(plan.period || "—")], ["Loja", esc(d.store_subscription?.store || "—")], ["Início na loja", when(d.store_subscription?.started_at)],
        ["Vence", when(plan.expires_at)], ["Renova", plan.will_renew ? "sim" : "não"]])
        + `<p><a class="button" href="#/premium?email=${encodeURIComponent(u.email)}">Dar Premium</a></p>`)}
      ${panel("Preferências", facts([["Tópicos", esc((p.topics || []).join(", ") || "—")], ["Horário", esc(p.briefing_time || "—")],
        ["Tamanho", esc(p.briefing_size ?? "—")], ["Duração", esc(p.briefing_length || "—")], ["Voz", esc(p.audio_voice_id || "—")],
        ["Áudio", p.audio_enabled ? "sim" : "não"], ["Abrangência", esc(p.country_scope || "—")],
        ["Extras", esc(d.briefing_slots.map((s) => `${s.delivery_time}${s.theme ? " " + s.theme : ""}${s.enabled ? "" : " (off)"}`).join(", ") || "—")]]))}
      ${panel("Uso", facts([["Dias de uso", `${num(d.activity.length)}${d.activity.length ? ` (último ${day(d.activity[0])})` : ""}`],
        ["Salvos", num(d.counts.saved_stories)], ["Briefings salvos", num(d.counts.saved_briefings)], ["Coleções", num(d.counts.collections)],
        ["Alertas", esc(d.keyword_alerts.join(", ") || "—")], ["Histórias seguidas", num(d.counts.followed_stories)],
        ["Times", esc(d.favorite_teams.join(", ") || "—")], ["Avaliações", num(d.counts.feedback)]]))}
    </div>
    ${d.grants.length ? panel("Premium dado pelo painel", grantsTable(d.grants, false)) : ""}
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
      { title: "push_por_tipo" }), 'ANNOUNCEMENT e PROMOTION são os enviados pelo painel (<a href="#/push">Enviar push</a>). Aberturas dos pushes chegam com a versão 1.1 do app.')}
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
    <p class="muted">${flags}.</p>
    ${salesBlock(d.sales)}
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

// ------------------------------------------------------------------ sales (Assinaturas)
const SALES = {
  trial_started: "Testes grátis iniciados", trial_converted: "Testes convertidos", trial_cancelled: "Testes cancelados",
  new_paid: "Novas assinaturas pagas", renewal: "Renovações", cancellation: "Cancelamentos (renovação desligada)",
  uncancellation: "Renovação religada", refund: "Reembolsos", expiration: "Expiradas", billing_issue: "Falhas de cobrança",
  product_change: "Trocas de plano",
};
const money = (amounts) => Object.entries(amounts || {})
  .map(([c, v]) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: c })).join(" + ") || "—";

function salesBlock(s) {
  if (!s) return "";
  const t = s.totals, tc = s.trial_conversion, o = s.overview;
  const overview = !o.configured
    ? `<p class="muted">Para ver MRR, assinantes ativos e receita dos últimos 28 dias direto do RevenueCat, configure a chave da API v2 (etapa 3 do documento).</p>`
    : o.error ? `<div class="alert warn">Não foi possível ler o RevenueCat: ${esc(o.error)}.</div>`
    : `<div class="grid">${o.metrics.map((m) => card(m.name, m.unit === "$" ? money({ BRL: m.value }) : num(m.value), esc(m.description || ""))).join("")}</div>
       <p class="muted">Lido do RevenueCat em ${when(o.fetched_at)} (guardado por 10 min).</p>`;
  const since = s.since_events ? `Eventos de venda registrados desde ${when(s.since_events)}.`
    : "Nenhum evento de venda recebido ainda: os números aparecem conforme o RevenueCat avisar compras, renovações e cancelamentos.";
  return `${panel("RevenueCat agora", overview)}
    <div class="grid">
      ${card("Receita bruta", money(s.revenue), `no período · líquido estimado ${money(s.net_estimate)}`)}
      ${card("Testes grátis", num(tc.started), `${num(tc.converted)} convertidos (${pct(tc.converted, tc.started)})`)}
      ${card("Novas pagas", num(t.new_paid || 0), `${num(t.renewal || 0)} renovações`)}
      ${card("Cancelamentos", num(t.cancellation || 0), `${num(t.refund || 0)} reembolsos`)}
    </div>
    <p class="muted">${since} Compras de teste (sandbox) ficam de fora.</p>
    <div class="cols">
      ${panel("Eventos no período", hbars(Object.entries(t).sort((a, b) => b[1] - a[1]).map(([k, v]) => [SALES[k] || k, v])))}
      ${panel("Receita por dia", bars(s.per_day.map((r) => ({ day: r.day, value: Object.values(r.revenue).reduce((a, b) => a + b, 0) }))))}
    </div>
    ${panel("Últimos eventos de venda", table(["Quando", "Evento", "Conta", "Produto", "Loja", "Valor"],
      s.events.map((e) => [when(e.event_at), esc(SALES[e.kind] || e.type), esc(e.email || "—"), esc(e.product_id || "—"), esc(e.store || "—"),
        e.price_local != null ? money({ [e.currency || "USD"]: e.price_local }) : e.price_usd != null ? money({ USD: e.price_usd }) : "—"]),
      { title: "eventos_venda", empty: "Nenhum evento no período." }))}`;
}

// ------------------------------------------------------------------ Dar Premium
const REASONS = { cortesia: "Cortesia", parceria: "Parceria", suporte: "Suporte", teste: "Teste", outro: "Outro" };
const GRANT_STATUS = { ativo: "ok", agendado: "", encerrado: "warn", retirado: "error" };
const ymd = (date) => date.toLocaleDateString("sv-SE");            // YYYY-MM-DD in the browser's (owner's) time zone
const plusDays = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return ymd(d); };
// A grant ends at the start of the day after its last day; the form and the tables show that last day.
const lastDay = (iso) => { const d = new Date(iso); d.setMinutes(d.getMinutes() - 1); return ymd(d); };
const firstDay = (iso) => ymd(new Date(iso));

function grantsTable(grants, actions = true) {
  return table(["Conta", "Status", "De", "Até", "Motivo", "Observação", "Dado em", ...(actions ? [""] : [])],
    grants.map((g) => [esc(g.email || g.user_id), `<span class="pill ${GRANT_STATUS[g.status]}">${esc(g.status)}</span>`, day(firstDay(g.starts_at)),
      day(lastDay(g.ends_at)), esc(REASONS[g.reason] || g.reason), `<span class="wrap">${esc(g.note || "")}</span>`, when(g.created_at),
      ...(actions ? [g.status === "ativo" || g.status === "agendado"
        ? `<button class="ghost small" data-action="grant-edit" data-id="${esc(g.id)}">Alterar</button> <button class="ghost small danger" data-action="grant-revoke" data-id="${esc(g.id)}">Retirar</button>`
        : ""] : [])]),
    { title: "premium_dado", empty: "Nenhum Premium dado pelo painel ainda." });
}

let grantsCache = [];
screens.premium = async () => {
  const d = await api("/premium-grants");
  grantsCache = d.grants;
  const prefill = new URLSearchParams(location.hash.split("?")[1] || "").get("email") || "";
  const labels = { ativo: "Ativos", agendado: "Agendados", encerrado: "Encerrados", retirado: "Retirados" };
  return `<div id="flash" class="alert" hidden></div>
    ${panel("Dar Premium", `
    <form id="grant-form" class="form">
      <input type="hidden" name="id">
      <label class="wide">E-mails <span class="muted">(um ou vários, separados por vírgula ou linha)</span>
        <textarea name="emails" rows="2" required placeholder="pessoa@email.com">${esc(prefill)}</textarea></label>
      <label>Data inicial <input type="date" name="start_day" value="${plusDays(0)}" required></label>
      <label>Data final <input type="date" name="end_day" value="${plusDays(30)}" required></label>
      <label>Motivo <select name="reason">${d.reasons.map((r) => `<option value="${r}">${REASONS[r] || r}</option>`).join("")}</select></label>
      <label class="wide">Observação <input name="note" maxlength="300" placeholder="Ex.: parceria com fulano, compensação por um erro..."></label>
      <p class="wide muted">Vale do início do primeiro dia até o fim do último (horário de Brasília); data inicial no futuro deixa agendado.
        Não mexe em assinatura da loja: se a pessoa assinar, as duas convivem e o app mostra a da loja.</p>
      <div class="wide actions"><button type="submit" id="grant-submit">Dar Premium</button>
        <button type="button" class="ghost" data-action="grant-cancel-edit" hidden>Cancelar alteração</button></div>
    </form>`)}
    <div class="grid">${Object.entries(d.counts).map(([k, v]) => card(labels[k] || k, num(v))).join("")}</div>
    ${panel("Premium dado pelo painel", grantsTable(d.grants))}`;
};

async function submitGrant(form) {
  const f = new FormData(form);
  const body = { start_day: f.get("start_day"), end_day: f.get("end_day"), reason: f.get("reason"), note: f.get("note") };
  const id = f.get("id");
  if (id) {
    await send("PUT", `/premium-grants/${encodeURIComponent(id)}`, body);
    await render(); flash("Premium alterado.");
    return;
  }
  const emails = f.get("emails");
  if (!confirm(`Dar Premium de ${day(body.start_day)} a ${day(body.end_day)} para:\n\n${emails}`)) return;
  const result = await send("POST", "/premium-grants", { ...body, emails });
  await render();
  const given = result.given.map((g) => g.email).join(", ");
  flash(`Premium dado para ${given || "ninguém"}.${result.missing.length ? ` Sem conta no Newzi: ${result.missing.join(", ")}.` : ""}`,
    result.missing.length ? "warn" : "ok");
}

function editGrant(id) {
  const g = grantsCache.find((item) => item.id === id);
  const form = document.getElementById("grant-form");
  if (!g || !form) return;
  form.elements.id.value = g.id;
  form.emails.value = g.email || g.user_id;
  form.emails.disabled = true;
  form.start_day.value = firstDay(g.starts_at);
  form.end_day.value = lastDay(g.ends_at);
  form.reason.value = g.reason;
  form.note.value = g.note || "";
  document.getElementById("grant-submit").textContent = "Salvar alteração";
  form.querySelector('[data-action="grant-cancel-edit"]').hidden = false;
  form.scrollIntoView({ behavior: "smooth" });
}

// ------------------------------------------------------------------ Enviar push
const SCREEN_NAMES = { Subscription: "Tela de assinatura (Premium)", NotificationSettings: "Ajustes de notificação",
  ContentPreferences: "Preferências de conteúdo", DailyBriefing: "Resumo diário", Football: "Esportes", History: "Histórico" };
const SEGMENT_NAMES = { all: "Todos", premium_now: "Premium agora", not_premium: "Sem Premium agora", never_premium: "Nunca foi Premium",
  ever_premium: "Já foi Premium", ex_premium: "Ex-Premium (venceu ou cancelou)" };
const CAMPAIGN_STATUS = { SCHEDULED: ["agendado", ""], SENDING: ["enviando", "warn"], SENT: ["enviado", "ok"], CANCELLED: ["cancelado", "error"] };
let pushCache = { campaigns: [] };

function audienceText(a) {
  if (a.emails?.length) return `${a.emails.length} e-mail(s): ${a.emails.slice(0, 3).join(", ")}${a.emails.length > 3 ? "…" : ""}`;
  const parts = [SEGMENT_NAMES[a.segment || "all"]];
  if (a.platform) parts.push(PLATFORM[a.platform]);
  if (a.topic) parts.push(`tópico ${pushCache.topics?.find((t) => t.code === a.topic)?.name || a.topic}`);
  if (a.team_id) parts.push(`time ${pushCache.teams?.find((t) => t.id === a.team_id)?.name || a.team_id}`);
  if (a.language) parts.push(`idioma ${a.language}`);
  if (a.inactive_days) parts.push(`sem usar há ${a.inactive_days}+ dias`);
  return parts.join(" · ");
}
function targetText(t) {
  if (t.screen) return SCREEN_NAMES[t.screen] || t.screen;
  if (t.story_id) return `Notícia ${t.story_id}`;
  if (t.url) return t.url;
  return "Abrir o app";
}

screens.push = async () => {
  const d = await api("/push");
  pushCache = d;
  const options = (pairs, selected = "") => pairs.map(([v, l]) => `<option value="${esc(v)}"${String(v) === String(selected) ? " selected" : ""}>${esc(l)}</option>`).join("");
  const rows = d.campaigns.map((c) => {
    const [label, tone] = CAMPAIGN_STATUS[c.status] || [c.status, ""];
    const r = c.results;
    const result = r ? `${num(r.sent)} enviados${r.failed ? ` · ${num(r.failed)} falharam` : ""}${r.pending ? ` · ${num(r.pending)} na fila` : ""}` : "—";
    const actions = [`<button class="ghost small" data-action="push-copy" data-id="${esc(c.id)}">Duplicar</button>`];
    if (c.status === "SCHEDULED") actions.unshift(
      `<button class="ghost small" data-action="push-edit" data-id="${esc(c.id)}">Editar</button>`,
      `<button class="ghost small" data-action="push-send" data-id="${esc(c.id)}">Enviar agora</button>`,
      `<button class="ghost small danger" data-action="push-cancel" data-id="${esc(c.id)}">Cancelar</button>`);
    return [when(c.scheduled_for), c.kind === "PROMOTION" ? "Promoção" : "Aviso",
      `<span class="wrap"><b>${esc(c.title)}</b><br><span class="muted">${esc(c.body)}</span></span>`,
      `<span class="wrap">${esc(audienceText(c.audience))}</span>`, esc(targetText(c.target)), `<span class="pill ${tone}">${label}</span>`,
      c.devices != null ? `${num(c.users)} pessoas · ${num(c.devices)} aparelhos` : "—", result, actions.join(" ")];
  });
  return `<div id="flash" class="alert" hidden></div>
    <div class="push-layout">
    ${panel("Novo envio", `
    <form id="push-form" class="form">
      <input type="hidden" name="id">
      <label>Tipo <select name="kind">${options([["announcement", "Aviso (novidades, atualizações)"], ["promotion", "Promoção (ofertas, desconto)"]])}</select></label>
      <label>Quando <select name="when">${options([["now", "Agora"], ["later", "Agendar"]])}</select></label>
      <label class="later" hidden>Data e hora <input type="datetime-local" name="scheduled_for"></label>
      <label class="wide">Título <span class="muted counter" data-for="title"></span><input name="title" maxlength="65" required></label>
      <label class="wide">Texto <span class="muted counter" data-for="body"></span><textarea name="body" rows="3" maxlength="240" required></textarea></label>
      <label>Ao tocar, abrir <select name="target">${options([["", "O app (início)"], ["screen", "Uma tela do app"], ["story_id", "Uma notícia"], ["url", "Um link"]])}</select></label>
      <label class="target-screen" hidden>Tela <select name="screen">${options(d.screens.map((x) => [x, SCREEN_NAMES[x] || x]), "Subscription")}</select></label>
      <label class="target-story" hidden>ID da notícia <input name="story_id"></label>
      <label class="target-url" hidden>Link <input name="url" placeholder="https://"></label>
      <label class="wide">Imagem <span class="muted">(opcional, aparece no Android)</span><input name="image" placeholder="https://.../imagem.jpg"></label>
      <fieldset class="wide"><legend>Para quem</legend>
        <div class="form">
          <label>Público <select name="segment">${options(d.segments.map((x) => [x, SEGMENT_NAMES[x]]))}</select></label>
          <label>Aparelho <select name="platform">${options([["", "Android e iPhone"], ["ANDROID", "Só Android"], ["IOS", "Só iPhone"]])}</select></label>
          <label>Segue o tópico <select name="topic">${options([["", "Qualquer"], ...d.topics.map((t) => [t.code, t.name])])}</select></label>
          <label>Torce para <select name="team_id">${options([["", "Qualquer"], ...d.teams.map((t) => [t.id, `${t.name} (${t.users})`])])}</select></label>
          <label>Idioma <select name="language">${options([["", "Qualquer"], ["pt", "Português"], ["en", "Inglês"]])}</select></label>
          <label>Sem usar o app há <input type="number" name="inactive_days" min="1" placeholder="dias (opcional)"></label>
          <label class="wide">Ou só estes e-mails <span class="muted">(ignora os filtros acima; bom para testar no seu celular)</span>
            <textarea name="emails" rows="2" placeholder="seu@email.com"></textarea></label>
        </div>
      </fieldset>
      <div class="wide actions"><button type="button" class="ghost" data-action="push-preview">Ver quantos recebem</button>
        <span id="push-count" class="muted"></span></div>
      <label>Para confirmar, digite ENVIAR <input name="confirm" autocomplete="off" placeholder="ENVIAR"></label>
      <div class="wide actions"><button type="submit" id="push-submit">Enviar agora</button>
        <button type="button" class="ghost" data-action="push-reset">Limpar</button></div>
    </form>`)}
    ${panel("Prévia", `<div class="phone"><div class="notif"><img src="img/icon.svg" alt="" width="36" height="36"><div class="notif-text">
      <div class="notif-app">Newzi · agora</div><div class="notif-title" id="preview-title">Título</div>
      <div class="notif-body" id="preview-body">Texto da notificação</div></div></div></div>
      <p class="muted">No Android chega pelo canal <b id="preview-channel">Novidades do Newzi</b>. Quem desligou as notificações no app ou no aparelho não recebe.</p>`)}
    </div>
    ${panel("Envios", table(["Quando", "Tipo", "Mensagem", "Público", "Ao tocar", "Status", "Alcance", "Resultado", ""], rows,
      { title: "envios_push", empty: "Nenhum envio pelo painel ainda." }),
      "Promoções seguem a regra 4.5.4 da Apple: hoje a permissão de notificações do aparelho vale como consentimento.")}`;
};

function pushBody(form) {
  const f = new FormData(form);
  const target = {};
  const kind = f.get("target");
  if (kind === "screen") target.screen = f.get("screen");
  if (kind === "story_id") target.story_id = f.get("story_id").trim();
  if (kind === "url") target.url = f.get("url").trim();
  if (f.get("image").trim()) target.image = f.get("image").trim();
  const audience = { segment: f.get("segment") };
  for (const key of ["platform", "topic", "language"]) if (f.get(key)) audience[key] = f.get(key);
  if (f.get("team_id")) audience.team_id = Number(f.get("team_id"));
  if (f.get("inactive_days")) audience.inactive_days = Number(f.get("inactive_days"));
  if (f.get("emails").trim()) audience.emails = f.get("emails");
  const body = { kind: f.get("kind"), title: f.get("title").trim(), body: f.get("body").trim(), target, audience, confirm: f.get("confirm") };
  if (f.get("when") === "later") {
    if (!f.get("scheduled_for")) throw new Error("Escolha a data e a hora do envio.");
    body.scheduled_for = new Date(f.get("scheduled_for")).toISOString();
  }
  return body;
}

function syncPushForm(form) {
  if (!form) return;
  const kind = form.target.value;
  form.querySelector(".target-screen").hidden = kind !== "screen";
  form.querySelector(".target-story").hidden = kind !== "story_id";
  form.querySelector(".target-url").hidden = kind !== "url";
  form.querySelector(".later").hidden = form.when.value !== "later";
  document.getElementById("push-submit").textContent = form.elements.id.value ? "Salvar alteração" : form.when.value === "later" ? "Agendar" : "Enviar agora";
  document.getElementById("preview-title").textContent = form.title.value || "Título";
  document.getElementById("preview-body").textContent = form.body.value || "Texto da notificação";
  document.getElementById("preview-channel").textContent = form.kind.value === "promotion" ? "Ofertas e promoções" : "Novidades do Newzi";
  form.querySelectorAll(".counter").forEach((el) => { const field = form[el.dataset.for]; el.textContent = `${field.value.length}/${field.maxLength}`; });
}

function fillPushForm(c, editing) {
  const form = document.getElementById("push-form");
  if (!form || !c) return;
  form.reset();
  form.elements.id.value = editing ? c.id : "";
  form.kind.value = c.kind === "PROMOTION" ? "promotion" : "announcement";
  form.title.value = c.title;
  form.body.value = c.body;
  const t = c.target || {};
  form.target.value = t.screen ? "screen" : t.story_id ? "story_id" : t.url ? "url" : "";
  if (t.screen) form.screen.value = t.screen;
  form.story_id.value = t.story_id || "";
  form.url.value = t.url || "";
  form.image.value = t.image || "";
  const a = c.audience || {};
  form.segment.value = a.segment || "all";
  form.platform.value = a.platform || "";
  form.topic.value = a.topic || "";
  form.team_id.value = a.team_id || "";
  form.language.value = a.language || "";
  form.inactive_days.value = a.inactive_days || "";
  form.emails.value = (a.emails || []).join(", ");
  if (editing) {
    form.when.value = "later";
    const local = new Date(c.scheduled_for);
    local.setMinutes(local.getMinutes() - local.getTimezoneOffset());
    form.scheduled_for.value = local.toISOString().slice(0, 16);
  }
  syncPushForm(form);
  form.scrollIntoView({ behavior: "smooth" });
}

async function previewPush(form) {
  const out = document.getElementById("push-count");
  out.textContent = "Contando…";
  try {
    const p = await send("POST", "/push/preview", pushBody(form));
    out.innerHTML = `<b>${num(p.users_reachable)}</b> pessoas · <b>${num(p.devices)}</b> aparelhos (${num(p.by_platform.ANDROID)} Android, ${num(p.by_platform.IOS)} iPhone)`
      + (p.without_device ? ` · ${num(p.without_device)} da seleção sem aparelho com push` : "");
  } catch (error) { out.textContent = error.message; }
}

async function submitPush(form) {
  const body = pushBody(form);
  const id = form.elements.id.value;
  const result = id ? await send("PUT", `/push/${encodeURIComponent(id)}`, body) : await send("POST", "/push", body);
  await render();
  flash(result.status === "SCHEDULED" ? `Envio agendado para ${when(result.scheduled_for)}.`
    : `Enviando para ${num(result.users)} pessoas em ${num(result.devices)} aparelhos. O resultado aparece na lista em instantes (Atualizar).`);
}

// ------------------------------------------------------------------ routing
function route() {
  const [, screen = "overview", id] = location.hash.replace(/^#/, "").split("?")[0].split("/");
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
    syncPushForm(document.getElementById("push-form"));
  } catch (error) {
    if (ticket === rendering && error.message !== "signed out") {
      content.innerHTML = `<div class="alert error">Não foi possível carregar: ${esc(error.message)}</div>`;
    }
  }
}

const ACTIONS = {
  "grant-edit": (id) => editGrant(id),
  "grant-cancel-edit": () => render(),
  "grant-revoke": async (id) => {
    const g = grantsCache.find((item) => item.id === id);
    if (!confirm(`Retirar o Premium de ${g?.email || id} agora?`)) return;
    await send("POST", `/premium-grants/${encodeURIComponent(id)}/revoke`);
    await render(); flash("Premium retirado.");
  },
  "push-preview": () => previewPush(document.getElementById("push-form")),
  "push-reset": () => render(),
  "push-copy": (id) => fillPushForm(pushCache.campaigns.find((c) => c.id === id), false),
  "push-edit": (id) => fillPushForm(pushCache.campaigns.find((c) => c.id === id), true),
  "push-cancel": async (id) => {
    if (!confirm("Cancelar este envio agendado?")) return;
    await send("POST", `/push/${encodeURIComponent(id)}/cancel`);
    await render(); flash("Envio cancelado.");
  },
  "push-send": async (id) => {
    if (prompt("Enviar agora para o público deste envio? Digite ENVIAR para confirmar.")?.trim().toUpperCase() !== "ENVIAR") return;
    const c = await send("POST", `/push/${encodeURIComponent(id)}/send`, { confirm: "ENVIAR" });
    await render(); flash(`Enviando para ${num(c.users)} pessoas em ${num(c.devices)} aparelhos.`);
  },
};

content.addEventListener("click", async (event) => {
  const action = event.target.closest("[data-action]");
  if (action) {
    event.preventDefault();
    try { await ACTIONS[action.dataset.action]?.(action.dataset.id); } catch (error) { flash(error.message, "error"); }
    return;
  }
  const row = event.target.closest("tr[data-href]");
  if (row) { location.hash = row.dataset.href; return; }
  const page = event.target.closest("button[data-page]");
  if (page) { usersQuery.page = Number(page.dataset.page); render(); }
});
content.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  // getAttribute: the forms have a field named "id", which hides form.id.
  const formId = form.getAttribute("id");
  if (formId === "users-search") {
    const data = new FormData(form);
    usersQuery = { query: data.get("query").trim(), plan: data.get("plan"), page: 1 };
    render();
    return;
  }
  const submit = form.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    if (formId === "grant-form") await submitGrant(form);
    if (formId === "push-form") await submitPush(form);
  } catch (error) {
    flash(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});
content.addEventListener("input", (event) => syncPushForm(event.target.closest("#push-form")));
content.addEventListener("change", (event) => syncPushForm(event.target.closest("#push-form")));

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
