// Extensions for the source based local CRM demo.
(function () {
  async function commitFinance(mutate,done){
    const before=structuredClone(data);
    try{mutate();const saved=await saveData();if(saved===false){data=normalizeData(before);return;}done();}
    catch(error){data=normalizeData(before);toast(error.message);}
  }
  const oldRow = leadPartRow;
  leadPartRow = function (part = {}) {
    return oldRow(part)
      .replace(' list="priceArticles"', '')
      .replace(/<datalist id="priceArticles">.*?<\/datalist>/, '')
      .replaceAll('data-clear="partColor"', 'data-kp="clear-field" data-field="partColor"')
      .replaceAll('data-clear="partMilling"', 'data-kp="clear-field" data-field="partMilling"')
      .replace('<input name="priceItemId" type="hidden"', `<input name="partUnit" type="hidden" value="${esc(part.unit || "шт")}"><input name="priceItemId" type="hidden"`)
      .replace('<label>Артикул', `<label>Из справочника<select name="catalogChoice"><option value="">Выбрать явно</option>${data.priceItems.map(item => `<option value="${esc(item.id)}" ${part.priceItemId === item.id ? "selected" : ""}>${esc(item.article)} · ${esc(item.name)}</option>`).join("")}</select></label><label>Артикул`);
  };

  const oldNewOrder = newOrderModal;
  newOrderModal = function (prefill = "") {
    oldNewOrder(prefill);
    const clientId = location.hash.startsWith("#clients/") ? location.hash.split("/")[1] : null;
    const client = data.clients.find(row => row.id === clientId);
    const clientInput = document.querySelector('#newOrderForm [name="client"]');
    if (client && clientInput && !clientInput.value) clientInput.value = client.name;
    document.querySelector('#newOrderForm [name="initialPayment"]')?.insertAdjacentHTML("afterend", '<button type="button" class="button" data-kp="no-payment">Нет оплаты</button>');
  };

  function renderPriceBook() {
    crumbs.textContent = "Справочник цен";
    app.innerHTML = pageHead("Справочники", "Цены и артикулы", "Здесь хранятся текущие цены для новых КП. Сохранённые заказы не изменяются.", '<button class="button primary" data-kp="new-item">＋ Добавить запись</button>') +
      `<article class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Артикул</th><th>Название</th><th>Тип работы</th><th>Единица</th><th>Цена</th><th></th></tr></thead><tbody>${data.priceItems.map(item => `<tr><td>${esc(item.article)}</td><td>${esc(item.name)}</td><td>${esc(item.kind)}</td><td>${esc(item.unit)}</td><td>${money(item.price)}</td><td><button class="button" data-kp="edit-item" data-id="${esc(item.id)}">Изменить запись</button></td></tr>`).join("") || '<tr><td colspan="6" class="empty">Справочник пуст</td></tr>'}</tbody></table></div></article>`;
  }

  function priceModal(item) {
    openModal(item ? "Изменить запись" : "Новая запись", "Артикул уникален внутри типа работы", `<form id="priceItemForm" class="form-grid" data-id="${esc(item?.id || "")}"><div class="form-group"><label>Артикул</label><input name="article" value="${esc(item?.article || "")}" required></div><div class="form-group"><label>Название</label><input name="name" value="${esc(item?.name || "")}" required></div><div class="form-group"><label>Тип работы</label><input name="kind" value="${esc(item?.kind || "")}" required></div><div class="form-group"><label>Единица</label><input name="unit" value="${esc(item?.unit || "шт")}" required></div><div class="form-group full"><label>Цена, ₽</label><input name="price" type="number" step="0.01" min="0" value="${item?.price ?? ""}" required></div></form>`, "Сохранить запись");
  }

  function renderQuote(id) {
    const order = data.orders.find(row => row.id === id);
    if (!order) return navigate("orders");
    const parts = FasadKP.quoteRows(order.parts, data.priceItems);
    const total = parts.reduce((sum, part) => sum + FasadKP.lineAmount(part), 0);
    crumbs.textContent = `Заказы / ${order.id} / КП`;
    app.innerHTML = pageHead("Коммерческое предложение", `КП по заказу ${esc(order.id)}`, `${esc(order.client)} · согласованные цены заказа`, `<button class="button" data-order="${esc(order.id)}">← Заказ</button><button class="button primary" data-kp="print-quote">Печать КП</button>`) +
      `<article class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Артикул</th><th>Название</th><th>Тип работы</th><th>Объём</th><th>Ед.</th><th>Цена</th><th>Сумма</th></tr></thead><tbody>${parts.map(part => `<tr><td>${esc(part.article || "—")}</td><td>${esc(part.name || "—")}</td><td>${esc(part.kind || "—")}</td><td>${(["??","?2","sqm"].includes(part.unit)?FasadRules.area(FasadKP.lineQuantity(part)):new Intl.NumberFormat("ru-RU").format(FasadKP.lineQuantity(part)))}</td><td>${esc(part.unit || "шт")}</td><td>${money(part.price || 0)}</td><td>${money(FasadKP.lineAmount(part))}</td></tr>`).join("")}</tbody><tfoot><tr><td colspan="6"><strong>Итого КП</strong></td><td><strong>${money(total)}</strong></td></tr></tfoot></table></div></article>` +
      `<article class="panel pad"><h3>Расчёты по заказу</h3><p>Оплачено по заказу: <strong>${money(order.paidAmount || 0)}</strong></p><p>Остаток по заказу: <strong>${money(Math.max(0, order.amount - order.paidAmount))}</strong></p><p class="muted">Свободный депозит клиента не является оплатой заказа.</p></article>`;
  }
  renderers["price-book"] = renderPriceBook;
  detailRenderers.quote = renderQuote;
  const oldStock = renderStock;
  renderStock = function () {
    oldStock();
    app.querySelector(".head-actions")?.insertAdjacentHTML("afterbegin", '<button class="button" data-kp="add-stock">＋ Добавить материал</button>');
  };
  renderers.stock = renderStock;
  window.addEventListener("hashchange", () => {
    const [route, id] = location.hash.slice(1).split("/");
    if (route === "quote" && id) renderQuote(decodeURIComponent(id));
  });

  const oldClient = renderClient;
  renderClient = function (id) {
    oldClient(id);
    const client = data.clients.find(row => row.id === id);
    if (!client) return;
    const movements = data.depositMovements.filter(row => row.clientId === id).slice().reverse();
    app.querySelector("aside.stack")?.insertAdjacentHTML("afterbegin", `<article class="panel pad"><h3 class="card-title">Депозит клиента</h3><h2>${money(FasadKP.depositBalance(data, id))}</h2><div class="head-actions"><button class="button primary" data-kp="topup" data-id="${esc(id)}">Пополнить депозит</button><button class="button" data-kp="withdraw" data-id="${esc(id)}">Уменьшить депозит</button></div><div class="activity-list deposit-history">${movements.map(row => `<div class="activity-row"><span class="activity-icon">${row.kind === "topup" || row.kind === "refund" ? "+" : "−"}</span><div><b>${money(row.amount)}</b><p>${esc({topup:"Пополнение",withdrawal:"Корректировка",spend:"Списание на заказ",refund:"Возврат списания"}[row.kind])}${row.orderId ? ` · ${esc(row.orderId)}` : ""}${row.reason ? ` · ${esc(row.reason)}` : ""}</p></div><time>${new Date(row.date).toLocaleDateString("ru-RU")}</time></div>`).join("") || '<div class="empty">Движений пока нет</div>'}</div></article>`);
  };

  const oldOrder = renderOrder;
  renderOrder = function (id) {
    oldOrder(id);
    const order = data.orders.find(row => row.id === id);
    if (!order) return;
    app.querySelector(".order-actions")?.insertAdjacentHTML("afterbegin", `<button class="button" data-kp="quote" data-id="${esc(id)}">Коммерческое предложение</button>`);
    app.querySelector("aside.stack")?.insertAdjacentHTML("beforeend", `<article class="panel pad"><h3 class="card-title">История оплат заказа</h3><div class="activity-list">${(order.payments || []).map(row => `<div class="activity-row"><div><b>${money(row.amount)}</b><p>${esc(row.method === "deposit" ? "С депозита клиента" : row.method || "Оплата")}</p></div><button class="link" data-kp="delete-payment" data-id="${esc(row.id || "")}">Удалить оплату</button></div>`).join("") || '<div class="empty">Оплат нет</div>'}</div></article>`);
  };

  function depositModal(clientId, kind) {
    const title = kind === "topup" ? "Пополнить депозит" : "Уменьшить депозит";
    openModal(title, `Доступно: ${money(FasadKP.depositBalance(data, clientId))}`, `<form class="form-grid" id="depositForm" data-id="${esc(clientId)}" data-kind="${kind}"><div class="form-group full"><label>Сумма, ₽</label><input name="amount" type="number" min="0.01" step="0.01" required></div><div class="form-group full"><label>${kind === "withdrawal" ? "Причина (обязательно)" : "Комментарий"}</label><input name="reason" ${kind === "withdrawal" ? "required" : ""}></div></form>`, title);
  }

  document.addEventListener("click", async event => {
    const button = event.target.closest("[data-kp]");
    if (!button) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const action = button.dataset.kp;
    if (action === "new-item" || action === "edit-item") priceModal(data.priceItems.find(row => row.id === button.dataset.id));
    if (action === "add-stock") openModal("Добавить материал", "Для раскроя укажите лист МДФ и начальный остаток", `<form id="kpStockForm" class="form-grid"><div class="form-group full"><label>Материал</label><select name="name"><option>МДФ 16 мм</option><option>МДФ 19 мм</option></select></div><div class="form-group"><label>Листов</label><input name="qty" type="number" min="0" step="1" required></div><div class="form-group"><label>Минимальный остаток</label><input name="min" type="number" min="0" step="1" value="0" required></div></form>`, "Добавить материал");
    if (action === "quote") navigate("quote", button.dataset.id);
    if (action === "print-quote") window.print();
    if (action === "topup" || action === "withdraw") depositModal(button.dataset.id, action === "withdraw" ? "withdrawal" : "topup");
    if (action === "delete-payment") {
      const id = decodeURIComponent(location.hash.split("/")[1]), order = data.orders.find(row => row.id === id);
      await commitFinance(()=>FasadKP.deleteOrderPayment(data,order,button.dataset.id),()=>{renderOrder(id);toast('Оплата удалена');});
    }
    if (action === "no-payment") { const input = document.querySelector('#newOrderForm [name="initialPayment"]'); if (input) input.value = ""; }
    if (action === "clear-field") { const input = button.closest(".lead-part-card")?.querySelector(`[name="${button.dataset.field}"]`); if (input) { input.value = ""; input.focus(); } }
  }, true);

  document.addEventListener("click", event => {
    const action = event.target.closest('[data-action="add-payment"]');
    if (!action) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const order = data.orders.find(row => row.id === action.dataset.id);
    if (!order) return;
    const due = Math.max(0, order.amount - order.paidAmount);
    if (!due) return toast("Заказ уже оплачен полностью");
    openModal("Оплата по заказу", `${order.id} · осталось ${money(due)}`, `<form class="form-grid" id="kpPaymentForm" data-id="${esc(order.id)}"><div class="form-group full"><label>Сумма, ₽</label><input name="amount" type="number" min="0.01" step="0.01" max="${due}" required></div><div class="form-group full"><label>Способ</label><select name="method"><option value="transfer">Перевод</option><option value="cash">Наличные</option><option value="card">Карта</option><option value="deposit">С депозита клиента</option></select></div></form>`, "Добавить оплату");
  }, true);

  document.addEventListener("click", async event => {
    if (!event.target.closest("[data-modal-save]")) return;
    const form = document.querySelector("#priceItemForm, #depositForm, #kpPaymentForm, #kpStockForm");
    if (!form) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (!form.reportValidity()) return;
    const fields = Object.fromEntries(new FormData(form));
    try {
      if (form.id === "priceItemForm") {
        FasadKP.savePriceItem(data.priceItems, fields, form.dataset.id || null);
        saveData(); closeModal(); renderPriceBook(); toast("Запись справочника сохранена");
      } else if (form.id === "kpStockForm") {
        if (data.stock.some(row => row.name === fields.name)) throw new Error("Материал уже есть на складе");
        data.stock.push({name:fields.name, type:"Плита", qty:Number(fields.qty), reserved:0, unit:"лист", min:Number(fields.min), createdAt:new Date().toISOString()});
        saveData(); closeModal(); renderStock(); toast("Материал добавлен");
      } else if (form.id === "depositForm") {
        await commitFinance(()=>FasadKP.addDepositMovement(data,form.dataset.id,form.dataset.kind,fields.amount,fields.reason),()=>{closeModal();renderClient(form.dataset.id);toast('Депозит обновлён');});
      } else {
        const order = data.orders.find(row => row.id === form.dataset.id);
        await commitFinance(()=>FasadKP.addOrderPayment(data,order,fields.amount,fields.method),()=>{closeModal();renderOrder(order.id);toast('Оплата добавлена');});
      }
    } catch (error) { toast(error.message); }
  }, true);

  document.addEventListener("change", event => {
    if (event.target.name !== "catalogChoice") return;
    const item = data.priceItems.find(row => row.id === event.target.value);
    const card = event.target.closest(".lead-part-card");
    if (!item || !card) return;
    card.querySelector('[name="partArticle"]').value = item.article;
    card.querySelector('[name="partName"]').value = item.name;
    card.querySelector('[name="partPrice"]').value = item.price;
    card.querySelector('[name="partUnit"]').value = item.unit;
    card.querySelector('[name="priceItemId"]').value = item.id;
    const kind=card.querySelector('[name="partKind"]');if(kind)kind.value=item.kind;
    refreshLeadTotal(card.closest("form"));
  });
  document.addEventListener("input", event => {
    if (event.target.name === "partArticle") {
      const card = event.target.closest(".lead-part-card");
      if (card) card.querySelector('[name="priceItemId"]').value = "";
    }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Enter" && event.target.closest(".lead-part-card") && ["partArticle", "partColor", "partMilling", "partName"].includes(event.target.name)) event.preventDefault();
  });

  // An empty first visit remains empty, including after the reset control is used.
  document.querySelector("#resetDemo").textContent = "Очистить демоданные";
  if (location.hash.startsWith("#quote/")) renderQuote(decodeURIComponent(location.hash.split("/")[1]));
  else renderRoute();
})();
