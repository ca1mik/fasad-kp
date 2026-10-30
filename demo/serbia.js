"use strict";

const STORAGE_KEY = "fasad-flow-serbia-demo-v1";
const STAGES = ["Upit", "Ponuda", "Priprema", "Sečenje", "Farbanje", "Montaža", "Spremno"];
const currency = new Intl.NumberFormat("sr-RS", { maximumFractionDigits: 0 });
const dateFormat = new Intl.DateTimeFormat("sr-Latn-RS", { day: "2-digit", month: "short", year: "numeric" });

function isoAfter(days) {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function seedOrders() {
  return [
    { id: "FF-1042", customer: "Studio Dunav", product: "Kuhinjski frontovi · MDF", due: isoAfter(5), amount: 285000, stage: 4, materialReady: true, positions: 24 },
    { id: "FF-1041", customer: "Enterijer Plus", product: "Plakari po meri", due: isoAfter(9), amount: 420000, stage: 3, materialReady: true, positions: 18 },
    { id: "FF-1040", customer: "M. Petrović", product: "Frontovi · hrastov furnir", due: isoAfter(3), amount: 178000, stage: 2, materialReady: false, positions: 12 },
    { id: "FF-1039", customer: "Atelje 21", product: "Komoda i police", due: isoAfter(12), amount: 146000, stage: 6, materialReady: true, positions: 8 }
  ];
}

function loadOrders() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(parsed) && parsed.every(order => order && typeof order.id === "string" && typeof order.customer === "string" && Number.isInteger(order.stage))) return parsed;
  } catch { /* Demo still works if browser storage is unavailable. */ }
  return seedOrders();
}

let orders = loadOrders();
let selectedId = orders[0]?.id;

function saveOrders() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(orders)); } catch { /* Storage is optional for demo. */ }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function displayDate(value) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? "—" : dateFormat.format(date);
}

function daysToDue(value) {
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const due = new Date(`${value}T12:00:00`);
  return Math.round((due - today) / 86400000);
}

function status(order) {
  if (order.stage >= STAGES.length - 1) return { label: "Spremno", css: "done" };
  if (!order.materialReady) return { label: "Čeka materijal", css: "blocked" };
  if (order.stage < 2) return { label: "U pripremi", css: "ready" };
  return { label: "U izradi", css: "" };
}

function render() {
  const selected = orders.find(order => order.id === selectedId) || orders[0];
  selectedId = selected?.id;
  const active = orders.filter(order => order.stage < STAGES.length - 1);
  document.querySelector("#today").textContent = dateFormat.format(new Date());
  document.querySelector("#activeCount").textContent = active.length;
  document.querySelector("#dueCount").textContent = active.filter(order => daysToDue(order.due) <= 7).length;
  document.querySelector("#materialCount").textContent = active.filter(order => !order.materialReady).length;
  document.querySelector("#activeValue").textContent = `${currency.format(active.reduce((sum, order) => sum + Number(order.amount || 0), 0))} RSD`;
  document.querySelector("#orderRows").innerHTML = orders.map(order => {
    const badge = status(order);
    return `<tr data-id="${escapeHtml(order.id)}" class="${order.id === selectedId ? "selected" : ""}" tabindex="0" aria-label="Otvori nalog ${escapeHtml(order.id)}"><td><b>${escapeHtml(order.id)}</b><small>${escapeHtml(order.product)}</small></td><td>${escapeHtml(order.customer)}</td><td>${displayDate(order.due)}</td><td><span class="status ${badge.css}">${badge.label}</span></td></tr>`;
  }).join("");
  document.querySelector("#selectedId").textContent = selected?.id || "—";
  document.querySelector("#orderDetail").innerHTML = selected ? `<div class="detail-body"><h4>${escapeHtml(selected.product)}</h4><p>${escapeHtml(selected.customer)}</p><div class="detail-line"><span>Rok isporuke</span><b>${displayDate(selected.due)}</b></div><div class="detail-line"><span>Pozicije</span><b>${Number(selected.positions) || 0}</b></div><div class="detail-line"><span>Vrednost</span><b>${currency.format(Number(selected.amount) || 0)} RSD</b></div><div class="detail-line"><span>Materijal</span><b>${selected.materialReady ? "Spreman" : "Nedostaje"}</b></div><div class="flow-label">TOK NALOGA</div><div class="flow-list">${STAGES.map((stage, index) => `<span class="${index < selected.stage ? "passed" : index === selected.stage ? "current" : ""}">${stage}</span>`).join("")}</div><button class="detail-button" id="advanceOrder" type="button" ${selected.stage >= STAGES.length - 1 ? "disabled" : ""}>${selected.stage >= STAGES.length - 1 ? "Nalog je spreman" : selected.materialReady ? "Pređi na sledeću fazu →" : "Evidentiraj materijal →"}</button></div>` : '<div class="detail-body">Nema naloga.</div>';
}

document.querySelector("#orderRows").addEventListener("click", event => {
  const row = event.target.closest("tr[data-id]");
  if (row) { selectedId = row.dataset.id; render(); }
});
document.querySelector("#orderRows").addEventListener("keydown", event => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("tr[data-id]");
  if (row) { event.preventDefault(); selectedId = row.dataset.id; render(); }
});
document.querySelector("#orderDetail").addEventListener("click", event => {
  if (event.target.id !== "advanceOrder") return;
  const order = orders.find(item => item.id === selectedId);
  if (!order || order.stage >= STAGES.length - 1) return;
  if (!order.materialReady) order.materialReady = true;
  else order.stage += 1;
  saveOrders(); render();
});
document.querySelector("#resetDemo").addEventListener("click", () => {
  orders = seedOrders(); selectedId = orders[0].id; saveOrders(); render();
});
const dialog = document.querySelector("#newOrderDialog");
document.querySelector("#newOrder").addEventListener("click", () => {
  document.querySelector('#newOrderForm input[name="due"]').value = isoAfter(14);
  dialog.showModal();
});
document.querySelector("#closeDialog").addEventListener("click", () => dialog.close());
document.querySelector("#newOrderForm").addEventListener("submit", event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const values = new FormData(form);
  const next = Math.max(1042, ...orders.map(order => Number(order.id.replace(/\D/g, "")) || 0)) + 1;
  const order = {
    id: `FF-${next}`, customer: String(values.get("customer")).trim(), product: String(values.get("product")).trim(),
    due: String(values.get("due")), amount: Number(values.get("amount")), stage: 0, materialReady: false, positions: 1
  };
  if (!order.customer || !order.product || !Number.isFinite(order.amount) || order.amount < 0 || order.amount > 100000000) return;
  orders.unshift(order); selectedId = order.id; saveOrders(); render(); form.reset(); dialog.close();
});
render();
