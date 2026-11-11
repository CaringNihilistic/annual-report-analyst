"use strict";

// Chat front end for POST /ask: a sidebar of saved chats and a centred conversation.
// No framework, no build step. Chats are kept in this browser's localStorage only.
// Safety: answer text comes from PDFs and an LLM, so it is only ever inserted with
// textContent / text nodes, never innerHTML.

const SUGGESTIONS = [
  "What was TCS's consolidated revenue from operations in FY2025?",
  "Which of the five companies had the highest consolidated revenue in FY2026?",
  "How did Infosys's operating margin change from fiscal 2025 to fiscal 2026?",
  "Rank the five companies by attrition in FY2026.",
  "How does HCLTech describe its AI positioning in its FY2026 Directors' Report?",
  "What dividends did TCS declare for FY2025?",
];
const STORE_KEY = "ragg-chats-v1";
const MAX_CHATS = 30;
const LOGO = '<svg viewBox="0 0 32 32"><path d="M9 22V10h3v12zm5 0v-7h3v7zm5 0V13h3v9z" fill="currentColor"/></svg>';
const ICON = {
  copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 15V6a2 2 0 012-2h9" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  trash: '<svg viewBox="0 0 24 24" width="16" height="16"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
};

const $ = (sel) => document.querySelector(sel);
const app = $(".app");
const main = $("#main");
const thread = $("#thread");
const form = $("#form");
const input = $("#q");
const send = $("#send");
const isPhone = () => window.matchMedia("(max-width: 768px)").matches;

let busy = false;
let chats = loadChats(); // [{id, title, turns: [{q, a}]}], newest first
let current = null; // id of the open chat, or null for a new one

// --- Storage ---------------------------------------------------------------------

function loadChats() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || []; } catch { return []; }
}
function saveChats() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(chats.slice(0, MAX_CHATS))); } catch { /* private mode */ }
}
const chatById = (id) => chats.find((c) => c.id === id);

// --- Small helpers ---------------------------------------------------------------

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}
// Only for our own constant SVG icons above, never for answer text.
function icon(svg) { const span = el("span"); span.innerHTML = svg; return span.firstChild; }

function citeLabel(c) { return `${c.company_name || c.company} · FY${c.fiscal_year} · p.${c.page}`; }
function scrollDown() { thread.scrollTop = thread.scrollHeight; }
function setEmpty(on) { main.classList.toggle("is-empty", on); }

// --- Sidebar ---------------------------------------------------------------------

function renderChatList() {
  const list = $("#chat-list");
  list.replaceChildren();
  $("#no-chats").hidden = chats.length > 0;
  for (const chat of chats) {
    const li = el("li", "chat-item" + (chat.id === current ? " active" : ""));
    const open = el("button", "open", chat.title);
    open.type = "button";
    open.title = chat.title;
    open.addEventListener("click", () => openChat(chat.id));
    const del = el("button", "del");
    del.type = "button";
    del.setAttribute("aria-label", `Delete chat: ${chat.title}`);
    del.append(icon(ICON.trash));
    del.addEventListener("click", () => deleteChat(chat.id));
    li.append(open, del);
    list.append(li);
  }
}

function openSide() {
  if (isPhone()) { app.classList.add("side-open"); $("#scrim").hidden = false; }
  else app.classList.remove("side-collapsed");
}
function closeSide() {
  if (isPhone()) { app.classList.remove("side-open"); $("#scrim").hidden = true; }
  else app.classList.add("side-collapsed");
}

function newChat() {
  current = null;
  thread.replaceChildren();
  setEmpty(true);
  renderChatList();
  if (isPhone()) closeSide();
  input.focus();
}

function openChat(id) {
  const chat = chatById(id);
  if (!chat) return newChat();
  current = id;
  thread.replaceChildren();
  for (const t of chat.turns) { addUser(t.q); thread.append(renderBot(t.a)); }
  setEmpty(chat.turns.length === 0);
  renderChatList();
  if (isPhone()) closeSide();
  scrollDown();
}

function deleteChat(id) {
  chats = chats.filter((c) => c.id !== id);
  saveChats();
  if (id === current) newChat(); else renderChatList();
}

// --- Messages --------------------------------------------------------------------

function addUser(text) {
  const row = el("div", "turn msg-user");
  row.append(el("div", "bubble", text));
  thread.append(row);
}

function botShell(extraClass = "") {
  const row = el("div", "turn msg-bot " + extraClass);
  const avatar = el("div", "avatar");
  avatar.append(icon(LOGO));
  const body = el("div", "bot-body");
  row.append(avatar, body);
  return { row, body };
}

// "… ₹2,55,324 crore [1]." -> text nodes plus citation markers; **bold** -> <strong>.
function answerBody(text, citations) {
  const body = el("div", "answer-text");
  const byN = new Map(citations.map((c) => [c.n, c]));
  for (const part of text.split(/(\[\d+\]|\*\*[^*]+\*\*)/)) {
    if (!part) continue;
    const ref = part.match(/^\[(\d+)\]$/);
    const bold = part.match(/^\*\*([^*]+)\*\*$/);
    if (ref && byN.has(Number(ref[1]))) {
      const sup = el("span", "ref", ref[1]);
      sup.dataset.n = ref[1];
      sup.title = citeLabel(byN.get(Number(ref[1])));
      sup.tabIndex = 0;
      body.append(sup);
    } else if (bold) body.append(el("strong", null, bold[1]));
    else body.append(document.createTextNode(part));
  }
  return body;
}

function linkHighlights(scope) {
  // Hovering a [n] marker lights up its source chip, and the other way round.
  const toggle = (n, on) => scope.querySelectorAll(`[data-n="${n}"]`).forEach((x) => x.classList.toggle("lit", on));
  scope.querySelectorAll("[data-n]").forEach((node) => {
    const n = node.dataset.n;
    ["mouseenter", "focus"].forEach((ev) => node.addEventListener(ev, () => toggle(n, true)));
    ["mouseleave", "blur"].forEach((ev) => node.addEventListener(ev, () => toggle(n, false)));
  });
}

function renderBot(data) {
  const { row, body } = botShell(data.refused ? "refused" : "");
  if (data.refused) body.append(el("div", "badge", "Not answered"));
  body.append(answerBody(data.answer || "", data.citations || []));

  if (data.citations && data.citations.length) {
    const sources = el("div", "sources");
    sources.setAttribute("aria-label", "Sources");
    for (const c of data.citations) {
      const chip = el("span", "source");
      chip.dataset.n = String(c.n);
      chip.append(el("b", null, String(c.n)), document.createTextNode(citeLabel(c)));
      sources.append(chip);
    }
    body.append(sources);
  }

  const actions = el("div", "actions");
  const copy = el("button");
  copy.type = "button";
  copy.title = "Copy answer and sources";
  copy.setAttribute("aria-label", "Copy");
  copy.append(icon(ICON.copy));
  copy.addEventListener("click", async () => {
    const text = [data.answer, ...(data.citations || []).map((c) => `[${c.n}] ${citeLabel(c)}`)].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      copy.replaceChildren(icon(ICON.check));
      setTimeout(() => copy.replaceChildren(icon(ICON.copy)), 1500);
    } catch { /* clipboard blocked */ }
  });
  const source = data.refused ? "" : data.model ? data.model.replace(/^openai\//, "") : "figures table";
  const bits = [source, data.seconds != null ? `${data.seconds.toFixed(1)} s` : "", data.cached ? "cached" : ""];
  actions.append(copy, el("span", "info", bits.filter(Boolean).join(" · ")));
  body.append(actions);

  linkHighlights(body);
  return row;
}

function renderPending() {
  const { row, body } = botShell();
  const line = el("div", "thinking");
  const label = el("span", null, "Searching the reports…");
  line.append(el("span", "pulse"), label);
  const hint = el("div", "hint");
  body.append(line, hint);
  return { row, label, hint };
}

function renderError(question, message) {
  const { row, body } = botShell();
  body.append(el("div", "error-text", `Something went wrong: ${message}`));
  const retry = el("button", "retry", "Try again");
  retry.type = "button";
  retry.addEventListener("click", () => { row.remove(); ask(question, { echo: false }); });
  body.append(retry);
  return row;
}

// --- Asking ----------------------------------------------------------------------

function setBusy(on) { busy = on; updateSend(); }
function updateSend() { send.disabled = busy || input.value.trim().length < 3; }

async function ask(question, { echo = true } = {}) {
  question = question.trim();
  if (question.length < 3 || busy) return;

  if (!current) {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    const title = question.length > 48 ? question.slice(0, 46) + "…" : question;
    chats.unshift({ id, title, turns: [] });
    current = id;
    saveChats();
    renderChatList();
  }
  const chatId = current;
  setEmpty(false);
  if (echo) addUser(question);
  const pending = renderPending();
  thread.append(pending.row);
  scrollDown();
  setBusy(true);

  const started = performance.now();
  const tick = setInterval(() => {
    const s = Math.round((performance.now() - started) / 1000);
    pending.label.textContent = `Searching the reports… ${s} s`;
    if (s === 6) pending.hint.textContent =
      "Questions about the report text are re-ranked on a small CPU server and can take 30–40 s. " +
      "Figures and comparisons are near-instant.";
  }, 1000);

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail
        : res.status === 422 ? "questions must be 3–500 characters" : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    data.seconds = (performance.now() - started) / 1000;
    const chat = chatById(chatId);
    if (chat) { chat.turns.push({ q: question, a: data }); saveChats(); }
    if (current === chatId) pending.row.replaceWith(renderBot(data));
  } catch (err) {
    if (current === chatId) pending.row.replaceWith(renderError(question, err.message || "network error"));
  } finally {
    clearInterval(tick);
    setBusy(false);
    scrollDown();
    input.focus();
  }
}

// --- Wiring ----------------------------------------------------------------------

function autosize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 200) + "px";
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value;
  if (busy || q.trim().length < 3) return;
  input.value = "";
  autosize();
  updateSend();
  ask(q);
});
input.addEventListener("input", () => { autosize(); updateSend(); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
});

for (const q of SUGGESTIONS) {
  const b = el("button", "suggestion", q);
  b.type = "button";
  b.addEventListener("click", () => ask(q));
  $("#suggestions").append(b);
}

$("#new-chat").addEventListener("click", newChat);
$("#new-chat-top").addEventListener("click", newChat);
$("#open-side").addEventListener("click", openSide);
$("#close-side").addEventListener("click", closeSide);
$("#scrim").addEventListener("click", closeSide);

async function checkHealth() {
  const status = $("#status");
  try {
    const res = await fetch("/health", { cache: "no-store" });
    status.dataset.state = res.ok ? "ok" : "down";
    status.lastElementChild.textContent = res.ok ? "Online" : "Database offline";
  } catch {
    status.dataset.state = "down";
    status.lastElementChild.textContent = "Offline";
  }
}

renderChatList();
updateSend();
checkHealth();
setInterval(checkHealth, 30000);
input.focus();
