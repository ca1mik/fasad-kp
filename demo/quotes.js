// Standalone commercial proposals. These do not create orders or payments.
(function () {
  data.quotes ||= [];
  const number = (value,unit) => ["м²","м2","sqm"].includes(unit)?FasadRules.area(value):new Intl.NumberFormat("ru-RU").format(value);

  function renderQuotes() {
    crumbs.textContent = "Коммерческие предложения";
    app.innerHTML = pageHead("КП", "Коммерческие предложения", "Создавайте КП прямо из справочника цен, без заказа и предоплаты.", '<button class="button primary" data-quote="new">＋ Новое КП</button>') +
      `<article class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Номер</th><th>Клиент</th><th>Предмет</th><th>Дата</th><th>Сумма</th><th></th></tr></thead><tbody>${[...data.quotes].reverse().map(quote => `<tr class="clickable" data-quote-open="${esc(quote.id)}"><td><strong>${esc(quote.id)}</strong></td><td>${esc(quote.clientName)}</td><td>${esc(quote.title)}</td><td>${new Date(quote.createdAt).toLocaleDateString("ru-RU")}</td><td>${money(quote.total)}</td><td><button class="link">Открыть →</button></td></tr>`).join("") || '<tr><td colspan="6" class="empty">КП пока нет</td></tr>'}</tbody></table></div></article>`;
  }

  function lineFormRow() {
    return `<div class="quote-line-card"><div class="form-grid"><div class="form-group full"><label>Позиция справочника</label><select name="priceItemId" required><option value="">Выберите запись</option>${data.priceItems.map(item => `<option value="${esc(item.id)}">${esc(item.article)} · ${esc(item.name)} · ${money(item.price)}/${esc(item.unit)}</option>`).join("")}</select></div><div class="form-group"><label>Количество деталей</label><input name="qty" type="number" min="0.01" step="0.01" value="1" required></div><div class="form-group"><label>Высота, мм</label><input name="height" type="number" min="0" step="1" placeholder="Для цены за м²"></div><div class="form-group"><label>Ширина, мм</label><input name="width" type="number" min="0" step="1" placeholder="Для цены за м²"></div><div class="form-group"><label>Расчёт</label><div class="quote-line-info">Выберите позицию</div></div></div><button type="button" class="link" data-quote="remove-line">Удалить строку</button></div>`;
  }

  function newQuoteModal(clientId = "") {
    const client = data.clients.find(row => row.id === clientId);
    openModal("Новое КП", "Цены берутся из текущего справочника и фиксируются в созданном КП", `<form id="newQuoteForm" class="form-grid"><div class="form-group full"><label>Клиент из базы</label><select name="clientId"><option value="">Указать вручную</option>${data.clients.map(row => `<option value="${esc(row.id)}" ${row.id === clientId ? "selected" : ""}>${esc(row.name)}</option>`).join("")}</select></div><div class="form-group full"><label>Клиент</label><input name="clientName" value="${esc(client?.name || "")}" required placeholder="Имя или компания"></div><div class="form-group full"><label>Предмет КП</label><input name="title" required placeholder="Например, фасады для кухни"></div><div class="form-group"><label>Действует до</label><input name="validUntil" type="date"></div><div class="form-group full"><label>Комментарий</label><textarea name="note" placeholder="Условия и уточнения"></textarea></div><div class="form-group full"><div class="lead-parts-head"><label>Позиции КП</label><button type="button" class="link" data-quote="add-line">＋ Позиция</button></div><div id="quoteLines">${lineFormRow()}</div><p class="form-note">Для цены за м² укажите высоту и ширину каждой детали. Сумма депозита сюда не входит.</p><strong id="quoteDraftTotal">Итого: 0 ₽</strong></div></form>`, "Создать КП");
    document.querySelector("#modalLayer .modal")?.classList.add("wide");
  }

  function readLine(card) {
    const item = data.priceItems.find(row => row.id === card.querySelector('[name="priceItemId"]').value);
    if (!item) return null;
    const qty = Number(card.querySelector('[name="qty"]').value);
    const height = Number(card.querySelector('[name="height"]').value);
    const width = Number(card.querySelector('[name="width"]').value);
    if (!Number.isFinite(qty) || qty <= 0) throw new Error("Укажите количество больше нуля");
    if (["sqm", "м²", "м2"].includes(item.unit.toLocaleLowerCase("ru")) && (!Number.isFinite(height) || height <= 0 || !Number.isFinite(width) || width <= 0)) {
      throw new Error("Для цены за м² укажите высоту и ширину");
    }
    return FasadKP.applyPriceItem({qty, height, width}, item);
  }

  function refreshDraft() {
    const form = document.querySelector("#newQuoteForm");
    if (!form) return;
    let total = 0;
    form.querySelectorAll(".quote-line-card").forEach(card => {
      const item = data.priceItems.find(row => row.id === card.querySelector('[name="priceItemId"]').value);
      const info = card.querySelector(".quote-line-info");
      if (!item) { info.textContent = "Выберите позицию"; return; }
      try {
        const line = readLine(card);
        const amount = FasadKP.lineAmount(line);
        total += amount;
        info.textContent = `${number(FasadKP.lineQuantity(line),line.unit)} ${item.unit} × ${money(item.price)} = ${money(amount)}`;
      } catch { info.textContent = `Цена: ${money(item.price)}/${item.unit}`; }
    });
    form.querySelector("#quoteDraftTotal").textContent = `Итого: ${money(total)}`;
  }

  function saveQuote() {
    const form = document.querySelector("#newQuoteForm");
    if (!form?.reportValidity()) return;
    try {
      const lines = [...form.querySelectorAll(".quote-line-card")].map(readLine);
      if (!lines.length || lines.some(line => !line)) throw new Error("Добавьте хотя бы одну позицию из справочника");
      const fields = Object.fromEntries(new FormData(form));
      const quote = {
        id: nextRecordId("KP", data.quotes, 0),
        clientId: fields.clientId || null,
        clientName: String(fields.clientName).trim(),
        title: String(fields.title).trim(),
        validUntil: fields.validUntil || "",
        note: String(fields.note || "").trim(),
        createdAt: new Date().toISOString(),
        lines,
        total: lines.reduce((sum, line) => sum + FasadKP.lineAmount(line), 0),
      };
      data.quotes.push(quote);
      saveData(); closeModal(); navigate("quotes", quote.id); toast("КП создано");
    } catch (error) { toast(error.message); }
  }

  function renderSavedQuote(id) {
    const quote = data.quotes.find(row => row.id === id);
    if (!quote) return navigate("quotes");
    crumbs.textContent = `КП / ${quote.id}`;
    app.innerHTML = pageHead("Коммерческое предложение", `КП ${esc(quote.id)}`, `${esc(quote.clientName)} · ${esc(quote.title)}`, '<button class="button" data-route="quotes">← Все КП</button><button class="button primary" data-quote="print">Печать КП</button>') +
      `<article class="panel pad"><div class="detail-grid"><div class="detail"><small>Создано</small><strong>${new Date(quote.createdAt).toLocaleDateString("ru-RU")}</strong></div><div class="detail"><small>Действует до</small><strong>${quote.validUntil ? new Date(`${quote.validUntil}T00:00:00`).toLocaleDateString("ru-RU") : "Не указано"}</strong></div><div class="detail"><small>Клиент</small><strong>${esc(quote.clientName)}</strong></div></div></article>` +
      `<article class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Артикул</th><th>Наименование</th><th>Тип работы</th><th>Объём</th><th>Ед.</th><th>Цена</th><th>Сумма</th></tr></thead><tbody>${quote.lines.map(line => `<tr><td>${esc(line.article)}</td><td>${esc(line.name)}</td><td>${esc(line.kind)}</td><td>${number(FasadKP.lineQuantity(line),line.unit)}</td><td>${esc(line.unit)}</td><td>${money(line.price)}</td><td>${money(FasadKP.lineAmount(line))}</td></tr>`).join("")}</tbody><tfoot><tr><td colspan="6"><strong>Итого</strong></td><td><strong>${money(quote.total)}</strong></td></tr></tfoot></table></div></article>` +
      (quote.note ? `<article class="panel pad"><h3>Условия</h3><p>${esc(quote.note)}</p></article>` : "");
  }

  renderers.quotes = renderQuotes;
  detailRenderers.quotes = renderSavedQuote;
  window.addEventListener("hashchange", () => {
    const [route, id] = location.hash.slice(1).split("/");
    if (route === "quotes" && id) renderSavedQuote(id);
  });

  const oldClient = renderClient;
  renderClient = function (id) {
    oldClient(id);
    app.querySelector(".page-head .head-actions")?.insertAdjacentHTML("afterbegin", `<button class="button" data-quote="new" data-client-id="${esc(id)}">＋ Новое КП</button>`);
  };

  document.addEventListener("click", event => {
    const button = event.target.closest("[data-quote]");
    if (!button) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (button.dataset.quote === "new") newQuoteModal(button.dataset.clientId);
    if (button.dataset.quote === "add-line") { document.querySelector("#quoteLines")?.insertAdjacentHTML("beforeend", lineFormRow()); refreshDraft(); }
    if (button.dataset.quote === "remove-line") { button.closest(".quote-line-card")?.remove(); refreshDraft(); }
    if (button.dataset.quote === "print") window.print();
  }, true);

  document.addEventListener("click", event => {
    const target = event.target.closest("[data-quote-open]");
    if (target) { event.preventDefault(); event.stopImmediatePropagation(); navigate("quotes", target.dataset.quoteOpen); }
  }, true);

  document.addEventListener("click", event => {
    if (!event.target.closest("[data-modal-save]") || !document.querySelector("#newQuoteForm")) return;
    event.preventDefault(); event.stopImmediatePropagation(); saveQuote();
  }, true);

  document.addEventListener("change", event => {
    if (event.target.matches('#newQuoteForm [name="clientId"]')) {
      const client = data.clients.find(row => row.id === event.target.value);
      if (client) document.querySelector('#newQuoteForm [name="clientName"]').value = client.name;
    }
    if (event.target.closest("#newQuoteForm .quote-line-card")) refreshDraft();
  });
  document.addEventListener("input", event => {
    if (event.target.matches('#newQuoteForm [name="clientName"]')) {
      const select = document.querySelector('#newQuoteForm [name="clientId"]');
      const client = data.clients.find(row => row.id === select?.value);
      if (client && client.name !== event.target.value) select.value = "";
    }
    if (event.target.closest("#newQuoteForm .quote-line-card")) refreshDraft();
  });

  if (location.hash.startsWith("#quotes/")) renderSavedQuote(location.hash.split("/")[1]);
  else if (location.hash === "#quotes") renderRoute();
})();
