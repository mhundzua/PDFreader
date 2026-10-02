"use strict";

const FIELDS = ["contract", "serial", "date"];
const $ = (sel) => document.querySelector(sel);

const state = {
  queue: [],
  current: null,
  skipped: new Set(),
  items: [],
  cur: null, // { name, page, unit, top, bottom }
  busy: false,
  targetOk: false,
  loadToken: 0,
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Kļūda ${res.status}`);
  return data;
}

// --- datums: lietotājs raksta dd.mm.gggg, serveris saņem gggg-mm-dd ---------
function isoToLv(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return m ? `${m[3]}.${m[2]}.${m[1]}` : "";
}
function lvToIso(text) {
  const m = /^\s*(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{2}|\d{4})\.?\s*$/.exec(text || "");
  if (!m) return "";
  const year = m[3].length === 2 ? `20${m[3]}` : m[3];
  return `${year}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
}

// --- rinda (katrs ieraksts ir viena kvīts; failā var būt vairākas) ----------
async function refreshQueue() {
  let data;
  try {
    data = await api("/api/state");
  } catch (e) {
    $("#status").textContent = "Nav savienojuma ar rīku. Vai Start.command logs ir atvērts?";
    return;
  }
  state.items = data.queue;
  state.queue = data.queue.map((q) => q.key);
  state.settings = { inbox: data.inbox, output: data.output };
  $("#undo").disabled = !data.last;
  $("#undo").title = data.last
    ? `Atsaukt: ${data.last.target.split(/[\\/]/).slice(-2).join("/")}`
    : "Nav ko atsaukt";

  const list = $("#queue");
  list.innerHTML = "";
  for (const item of data.queue) {
    const li = document.createElement("li");
    li.dataset.key = item.key;
    li.className = (item.key === state.current ? "current " : "") + (item.ready ? "ready" : "");
    li.innerHTML = `<span class="dot">●</span><span></span>`;
    li.lastChild.textContent = item.label + (state.skipped.has(item.key) ? " (izlaists)" : "");
    li.title = item.ready ? "Nolasīts" : "Tiek nolasīts…";
    li.onclick = () => load(item.key);
    list.appendChild(li);
  }
  $("#queue-count").textContent = data.queue.length ? `(${data.queue.length})` : "";
  $("#queue-empty").hidden = data.queue.length > 0;
  const bad = data.unsupported || [];
  $("#unsupported").hidden = bad.length === 0;
  $("#unsupported").textContent = bad.length
    ? `${bad.length} faili netiek rādīti, jo nav atbalstīta veida (der PDF, JPG, PNG, HEIC): ${bad.slice(0, 5).join(", ")}${bad.length > 5 ? "…" : ""}`
    : "";

  if (state.current && !state.queue.includes(state.current)) {
    // Lapa pa to laiku nolasīta: tās vietā rindā tagad ir konkrētas kvītis.
    const [name, page] = state.current.split("|");
    const same = state.items.find((i) => i.name === name && String(i.page) === page);
    if (same && state.cur && same.name === state.cur.name) state.current = same.key;
    if (same && state.cur && state.cur.unit) {
      const exact = `${name}|${page}|${state.cur.unit}`;
      if (state.queue.includes(exact)) state.current = exact;
    }
    if (state.queue.includes(state.current)) {
      markCurrent();
      const item = state.items.find((i) => i.key === state.current);
      if (item) $("#doc-name").textContent = item.label;
    }
  }
  if (!state.current || !state.queue.includes(state.current)) {
    const next = pickNext(null);
    if (next) load(next);
    else showEmpty();
  }
}

function markCurrent() {
  document.querySelectorAll("#queue li").forEach((li) => {
    li.classList.toggle("current", li.dataset.key === state.current);
  });
}

function pickNext(after) {
  const q = state.queue;
  const start = after && q.includes(after) ? q.indexOf(after) + 1 : 0;
  const order = q.slice(start).concat(q.slice(0, start));
  return order.find((n) => n !== after && !state.skipped.has(n))
    || order.find((n) => n !== after)
    || null;
}

function showEmpty() {
  state.current = null;
  state.cur = null;
  $("#fields").hidden = true;
  $("#doc-name").textContent = "";
  $("#page-img").removeAttribute("src");
  $("#open-pdf").removeAttribute("href");
  $("#pager").hidden = true;
  $("#status").textContent = `Mapē Ienākošie (${state.settings?.inbox || ""}) nav jaunu kvīšu.`;
}

// --- viena kvīts -------------------------------------------------------------
async function load(key) {
  const token = ++state.loadToken;
  const item = (state.items || []).find((i) => i.key === key);
  if (!item) return;
  state.current = key;
  state.cur = { name: item.name, page: item.page, unit: item.unit, top: 0, bottom: 1 };
  markCurrent();
  $("#doc-name").textContent = item.label;
  $("#open-pdf").href = `/api/pdf?name=${encodeURIComponent(item.name)}`;
  $("#pager").hidden = true;
  showPage();
  $("#fields").hidden = true;
  $("#status").textContent = "Nolasa kvīti…";

  let data;
  try {
    const unit = item.unit ? `&unit=${encodeURIComponent(item.unit)}` : "";
    data = await api(`/api/extract?name=${encodeURIComponent(item.name)}&page=${item.page}${unit}`);
  } catch (e) {
    if (token === state.loadToken) $("#status").textContent = e.message;
    return;
  }
  if (token !== state.loadToken) return; // lietotājs pa to laiku izvēlējās citu

  state.cur = { name: item.name, page: item.page, unit: data.id, top: data.top, bottom: data.bottom };
  showPage();
  $("#status").textContent = data.error || "";
  for (const f of FIELDS) {
    const info = (data.fields || {})[f] || { value: "", confident: false, note: "Neizdevās nolasīt" };
    const box = document.querySelector(`.field[data-field="${f}"]`);
    const input = box.querySelector("input");
    input.value = f === "date" ? isoToLv(info.value) : info.value;
    box.classList.toggle("uncertain", !info.confident);
    box.querySelector(".note").textContent = info.note || "";
    const crop = box.querySelector(".crop");
    if (info.crop) crop.src = `data:image/png;base64,${info.crop}`;
    else crop.removeAttribute("src");
  }
  $("#fields").hidden = false;
  await updateTarget();
  if (token !== state.loadToken) return;
  const firstUncertain = document.querySelector(".field.uncertain input");
  (firstUncertain || $("#accept")).focus();
}

function showPage() {
  const c = state.cur;
  if (!c) return;
  $("#page-img").src = `/api/page?name=${encodeURIComponent(c.name)}&page=${c.page}`
    + `&top=${c.top}&bottom=${c.bottom}`;
}

function values() {
  return {
    contract: $("#f-contract").value.trim().toUpperCase(),
    serial: $("#f-serial").value.trim(),
    date: lvToIso($("#f-date").value),
  };
}

let targetTimer = null;
function scheduleTarget() {
  clearTimeout(targetTimer);
  targetTimer = setTimeout(updateTarget, 150);
}

let targetSeq = 0;
async function updateTarget() {
  const seq = ++targetSeq;
  const v = values();
  const messages = [];
  let data = { errors: {}, warnings: [], folder: "", file: "" };
  try {
    data = await api("/api/target", { method: "POST", body: JSON.stringify(v) });
  } catch (e) {
    messages.push(["error", e.message]);
  }
  if (seq !== targetSeq) return; // pa to laiku lauki mainīti; rāda jaunāko rezultātu
  if (!v.date && $("#f-date").value.trim()) {
    data.errors.date = "Datumu rakstiet formātā dd.mm.gggg";
  }
  for (const f of FIELDS) {
    document.querySelector(`.field[data-field="${f}"]`).classList.toggle("invalid", !!data.errors[f]);
  }
  for (const msg of Object.values(data.errors)) messages.push(["error", msg]);
  for (const msg of data.warnings) messages.push(["warning", msg]);
  const unconfirmed = document.querySelectorAll(".field.uncertain").length;
  if (unconfirmed) messages.push(["warning", `Jāpārbauda dzeltenie lauki (${unconfirmed})`]);

  $("#t-folder").textContent = data.folder || "—";
  $("#t-file").textContent = data.file || "—";
  const ul = $("#messages");
  ul.innerHTML = "";
  for (const [kind, text] of messages) {
    const li = document.createElement("li");
    li.className = kind;
    li.textContent = text;
    ul.appendChild(li);
  }
  state.targetOk = Object.keys(data.errors).length === 0 && !!data.folder && !!data.file;
  $("#accept").disabled = !state.targetOk || unconfirmed > 0 || state.busy;
}

async function accept() {
  if ($("#accept").disabled || !state.current || !state.cur) return;
  const key = state.current;
  const { name, page, unit } = state.cur;
  state.busy = true;
  $("#accept").disabled = true;
  try {
    const res = await api("/api/accept", {
      method: "POST",
      body: JSON.stringify({ name, page, unit, ...values() }),
    });
    toast(`Saglabāts: ${res.folder}/${res.file}`, true);
    state.skipped.delete(key);
    const next = pickNext(key);
    state.queue = state.queue.filter((n) => n !== key);
    state.items = state.items.filter((i) => i.key !== key);
    state.current = null;
    if (next && next !== key) load(next);
    await refreshQueue();
  } catch (e) {
    toast(e.message);
  } finally {
    state.busy = false;
    if (state.current) updateTarget();
  }
}

async function undo() {
  try {
    const res = await api("/api/undo", { method: "POST" });
    toast(`Atsaukts. Kvīts "${res.source}" atgriezta rindā.`);
    await refreshQueue();
    const page = res.unit ? res.unit.split("-")[0] : null;
    const item = state.items.find((i) => i.name === res.source
      && (!res.unit || (String(i.page) === page && i.unit === res.unit)));
    if (item) load(item.key);
  } catch (e) {
    toast(e.message);
  }
}

let toastTimer = null;
function toast(text, withUndo = false) {
  const el = $("#toast");
  el.innerHTML = "";
  const span = document.createElement("span");
  span.textContent = text;
  el.appendChild(span);
  if (withUndo) {
    const btn = document.createElement("button");
    btn.className = "small";
    btn.textContent = "Atsaukt";
    btn.onclick = () => { el.hidden = true; undo(); };
    el.appendChild(btn);
  }
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, withUndo ? 8000 : 5000);
}

// --- notikumi ----------------------------------------------------------------
for (const f of FIELDS) {
  const box = document.querySelector(`.field[data-field="${f}"]`);
  box.querySelector("input").addEventListener("input", () => {
    box.classList.remove("uncertain"); // labots = pārbaudīts
    scheduleTarget();
  });
  box.querySelector(".confirm").addEventListener("click", () => {
    box.classList.remove("uncertain");
    updateTarget();
    const next = document.querySelector(".field.uncertain input");
    (next || $("#accept")).focus();
  });
}
$("#fields").addEventListener("submit", (e) => { e.preventDefault(); accept(); });
$("#skip").onclick = () => {
  if (!state.current) return;
  state.skipped.add(state.current);
  const next = pickNext(state.current);
  if (next) load(next);
  refreshQueue();
};
$("#undo").onclick = undo;
$("#zoom").onclick = () => {
  const zoomed = $("#preview").classList.toggle("zoomed");
  $("#zoom").textContent = zoomed ? "Attālināt" : "Tuvināt";
};

$("#open-settings").onclick = () => {
  $("#s-inbox").value = state.settings?.inbox || "";
  $("#s-output").value = state.settings?.output || "";
  $("#settings-error").textContent = "";
  $("#settings").showModal();
};
$("#close-settings").onclick = () => $("#settings").close();
$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({ inbox: $("#s-inbox").value, output: $("#s-output").value }),
    });
    $("#settings").close();
    state.current = null;
    state.skipped.clear();
    refreshQueue();
  } catch (err) {
    $("#settings-error").textContent = err.message;
  }
});

refreshQueue();
setInterval(refreshQueue, 3000);
