// Small-screen position editor, example orders and a persistent colour theme.
(function () {
  leadPartRow = function (part = {}) {
    const value = input => esc(String(input ?? ""));
    return `<div class="lead-part-card" data-source-part-id="${value(part.id)}">
      <div class="lead-part-card-head"><strong>Деталь</strong><button type="button" class="remove-position" aria-label="Удалить деталь">Удалить</button></div>
      <div class="lead-part-row">
        <label class="part-name">Наименование<input name="partName" placeholder="Например, дверца шкафа" value="${value(part.name)}" required></label>
        <label>Высота, мм<input name="partHeight" type="number" min="1" placeholder="720" value="${value(part.height)}" required></label>
        <label>Ширина, мм<input name="partWidth" type="number" min="1" placeholder="400" value="${value(part.width)}" required></label>
        <label>Количество, шт.<input name="partQty" type="number" min="1" max="500" value="${value(part.qty ?? 1)}" required></label>
      </div>
      <div class="lead-part-extra">
        <label>Толщина, мм<input name="partThickness" type="number" min="1" value="${value(part.thickness ?? 16)}"></label>
        <label>Артикул<input name="partArticle" placeholder="Например, Арт.110" value="${value(part.article)}"></label>
        <div class="lead-param-field"><label>Цвет<input name="partColor" placeholder="Например, белый софт" value="${value(part.color)}"></label><button type="button" data-kp="clear-field" data-field="partColor" aria-label="Очистить всё" title="Очистить цвет">Сбросить</button></div>
        <div class="lead-param-field"><label>Фрезеровка<input name="partMilling" placeholder="Например, рамка" value="${value(part.milling)}"></label><button type="button" data-kp="clear-field" data-field="partMilling" aria-label="Очистить всё" title="Очистить фрезеровку">Сбросить</button></div>
      </div>
      <details class="lead-part-options"><summary>Справочник и цена <span>за штуку / м²</span></summary>
        <label>Выбрать из справочника<select name="catalogChoice"><option value="">Выбрать явно</option>${data.priceItems.map(item => `<option value="${value(item.id)}" ${part.priceItemId === item.id ? "selected" : ""}>${value(item.article)} · ${value(item.name)}</option>`).join("")}</select></label>
        <label><input type="checkbox" name="partNoRotation" ${part.no_rotation?"checked":""}> Запретить поворот</label><label>Тип работы<input name="partKind" value="${value(part.kind)}" placeholder="Например, фрезеровка"></label><label>Расчёт цены<select name="partUnit"><option value="шт" ${part.unit!=="м²"?"selected":""}>За штуку</option><option value="м²" ${part.unit==="м²"?"selected":""}>За м² (метраж)</option></select></label>
        <label style="display:flex;align-items:center;gap:8px"><input name="partGrain" type="checkbox" style="width:auto" ${part.grain===true?'checked':''}>Сохранять направление текстуры (запрет поворота)</label>
        <label><span class="part-price-label">Цена за ${part.unit==="м²"?"м²":"штуку"}, ₽</span><input name="partPrice" type="number" min="0" step="0.01" value="${value(part.price)}"></label>
      </details>
      <input name="priceItemId" type="hidden" value="${value(part.priceItemId)}">
    </div>`;
  };

  function nextPositionFrom(card) {
    if (!card) return {};
    const result=Object.fromEntries(["article", "color", "milling", "thickness", "price", "unit", "kind"].map(key => [key, card.querySelector(`[name="part${key[0].toUpperCase()}${key.slice(1)}"]`)?.value.trim() || ""]));
    result.priceItemId=card.querySelector('[name=priceItemId]')?.value||'';
    return result;
  }

  function updatePositionSummary(card) {
    const summary = card?.querySelector(".lead-part-summary");
    if (!summary) return;
    const read = name => card.querySelector(`[name="${name}"]`)?.value.trim() || "";
    const size = read("partHeight") && read("partWidth") ? `${read("partHeight")} × ${read("partWidth")} мм` : "размер не указан";
    summary.textContent = [read("partName") || "Деталь", size, `${read("partQty") || 1} шт.`, read("partColor")].filter(Boolean).join(" · ");
  }

  function prepareLeadCard(card) {
    if (!card || card.querySelector(".lead-part-collapse")) return;
    card.querySelector(".lead-part-card-head")?.insertAdjacentHTML("beforeend", '<span class="lead-part-summary" aria-live="polite"></span><button type="button" class="lead-part-collapse" aria-expanded="true">Свернуть</button>');
    updatePositionSummary(card);
  }
  window.FasadLeadUI={prepareLeadCard};

  document.addEventListener("input", event => {
    if (event.target.closest("#leadForm .lead-part-card")) updatePositionSummary(event.target.closest(".lead-part-card"));
  });

  document.addEventListener("click", event => {
    const toggle = event.target.closest("#leadForm .lead-part-collapse");
    if (toggle) {
      const card = toggle.closest(".lead-part-card");
      card.classList.toggle("is-collapsed");
      toggle.setAttribute("aria-expanded", String(!card.classList.contains("is-collapsed")));
      toggle.textContent = card.classList.contains("is-collapsed") ? "Развернуть" : "Свернуть";
      return;
    }
    const remove = event.target.closest(".remove-position");
    if (remove) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const form = remove.closest("form");
      remove.closest(".lead-part-card").remove();
      if (form) refreshLeadTotal(form);
      return;
    }
    const add = event.target.closest("#addLeadPart, #addEditLeadPart, #addOrderPart");
    if (!add) return;
    const list = add.closest(".form-group")?.querySelector(".lead-parts-list");
    if (!list) return;
    const last = list.querySelector(".lead-part-card:last-child");
    const missing = ["partName", "partHeight", "partWidth"].map(name => last?.querySelector(`[name="${name}"]`)).find(input => input && !input.value.trim());
    event.preventDefault();
    event.stopImmediatePropagation();
    if (missing) {
      missing.focus();
      toast("Сначала заполните название, высоту и ширину текущей позиции");
      return;
    }
    list.insertAdjacentHTML("beforeend", leadPartRow(nextPositionFrom(last)));
    if (list.closest("#leadForm")) {
      prepareLeadCard(list.querySelector(".lead-part-card:last-child"));
      [...list.querySelectorAll(".lead-part-card")].slice(0, -1).forEach(card => {
        card.classList.add("is-collapsed");
        const button = card.querySelector(".lead-part-collapse");
        if (button) { button.setAttribute("aria-expanded", "false"); button.textContent = "Развернуть"; }
        updatePositionSummary(card);
      });
    }
    list.querySelector(".lead-part-card:last-child [name=partName]")?.focus();
    refreshLeadTotal(add.closest("form"));
  }, true);

  const themeButton = document.querySelector("#themeToggle");
  function setTheme(dark) {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    themeButton.setAttribute("aria-pressed", String(dark));
    themeButton.textContent = dark ? "Светлая тема" : "Тёмная тема";
    localStorage.setItem("fasad-demo-theme", dark ? "dark" : "light");
  }
  setTheme(localStorage.getItem("fasad-demo-theme") === "dark");
  themeButton.addEventListener("click", () => setTheme(document.documentElement.dataset.theme !== "dark"));

  function samplePart(orderId, number, name, height, width, qty, article, color, milling, thickness, price) {
    return {id:`${orderId}-P${number}`,name,height,width,qty,article,color,milling,thickness,price,unit:"шт",edge:"4 стороны",grain:true};
  }
  function loadExampleOrders() {
    const examples = [
      {id:"F-DEMO-101",clientId:"C-DEMO-101",client:"Мария Орлова",product:"Кухня · белый софт",direction:"Эмаль",stage:"Расчёт",status:"Новый",due:"2026-10-28",parts:[
        samplePart("F-DEMO-101",1,"Фасад верхний",720,400,4,"Арт.110","Белый софт","Рамка",16,4200),
        samplePart("F-DEMO-101",2,"Фасад нижний",715,596,2,"Арт.110","Белый софт","Рамка",16,5900),
        samplePart("F-DEMO-101",3,"Панель боковая",2312,600,1,"Арт.110","Белый софт","Рамка",16,11600),
        samplePart("F-DEMO-101",4,"Фасад повтор",720,400,2,"Арт.110","Белый софт","Рамка",16,4200)
      ]},
      {id:"F-DEMO-102",clientId:"C-DEMO-102",client:"Студия Лист",product:"Шкаф · эвкалипт",direction:"ПВХ",stage:"Фрезеровка",status:"В работе",due:"2026-11-02",parts:[
        samplePart("F-DEMO-102",1,"Дверь шкафа",2200,447,2,"Арт.128","Эвкалипт гринвуд","Волна 40 мм",19,9800),
        samplePart("F-DEMO-102",2,"Антресоль",500,447,2,"Арт.128","Эвкалипт гринвуд","Волна 40 мм",19,4100),
        samplePart("F-DEMO-102",3,"Дверь шкафа",2200,447,1,"Арт.128","Эвкалипт гринвуд","Волна 40 мм",19,9800)
      ]},
      {id:"F-DEMO-103",clientId:"C-DEMO-103",client:"Алексей Волков",product:"Гостиная · два цвета",direction:"Эмаль",stage:"Согласование",status:"Новый",due:"2026-11-10",parts:[
        samplePart("F-DEMO-103",1,"Фасад белый",800,500,3,"Арт.110","Белый софт","Без фрезеровки",16,4700),
        samplePart("F-DEMO-103",2,"Фасад графит",800,500,2,"Арт.110","Графит матовый","Без фрезеровки",16,4900),
        samplePart("F-DEMO-103",3,"Ящик белый",220,500,4,"Арт.110","Белый софт","Без фрезеровки",16,2400)
      ]}
    ];
    let added = 0;
    for (const spec of examples) {
      if (data.orders.some(order => order.id === spec.id)) continue;
      if (!data.clients.some(client => client.id === spec.clientId)) data.clients.push({id:spec.clientId,name:spec.client,initials:spec.client.split(" ").map(word => word[0]).join("").slice(0,2),phone:"—",email:"—",city:"—",address:"—",type:"Демо",demo:true});
      const order = {...spec,initials:spec.client.split(" ").map(word => word[0]).join("").slice(0,2),amount:partsEstimate(spec.parts),paid:0,paidAmount:0,payments:[],manager:"Демо",material:false,risk:false,materialSpec:FasadFactorySettings.snapshot(data.factorySettings,spec.parts[0].thickness === 19 ? "МДФ 19 мм" : "МДФ 16 мм"),cuttingStatus:"draft",productionDone:0,demo:true,sampleKey:"orders-v1"};
      Object.assign(order,FasadProduction.bootstrap(order));
      data.orders.push(order);
      added++;
    }
    if (added) {localStorage.setItem("fasad-demo-clean-v2","1");saveData();}
    navigate("orders");
    toast(added ? `Добавлено ${added} примера заказов` : "Примеры заказов уже загружены");
  }
  document.querySelector("#exampleOrders").addEventListener("click", loadExampleOrders);

  function enhanceLeadForm() {
    const form = document.querySelector("#leadForm");
    if (!form) return;
    const workspaceGrid = form.closest(".sidebar-grid");
    const formPanel = form.closest(".panel");
    const recentPanel = workspaceGrid?.querySelector(":scope > .panel");
    const workspaceStack = formPanel?.parentElement;
    const stats = document.querySelector("#app > .stats");
    if (workspaceGrid && formPanel && recentPanel) {
      workspaceGrid.classList.add("manager-workspace");
      workspaceGrid.insertBefore(formPanel, recentPanel);
      workspaceStack?.remove();
      stats?.remove();
      formPanel.classList.add("manager-form-panel");
      recentPanel.classList.add("manager-recent-panel");
      recentPanel.querySelector(".panel-head p").textContent = "Новая заявка появится здесь первой. Полный список — в разделе «Заявки».";
      const recentHead = recentPanel.querySelector(".panel-head");
      recentHead.insertAdjacentHTML("beforeend", `<button type="button" class="button" data-route="leads">Все заявки →</button>`);
      const recentBody = recentPanel.querySelector("tbody");
      if (recentBody) recentBody.innerHTML = [...data.leads].slice(0, 10).map(leadRow).join("") || '<tr><td colspan="7" class="empty">Заявок пока нет. Создайте первую выше.</td></tr>';
    }
    const page = document.querySelector("#app > .page-head");
    if (page) {
      page.querySelector(".eyebrow").textContent = "Рабочее место менеджера";
      page.querySelector("h1").textContent = "Принять заявку";
      page.querySelector(".lead").textContent = "Запишите клиента и детали. После сохранения можно открыть раскрой или чертёж для ЧПУ.";
      page.querySelector(".head-actions").innerHTML = '<button type="button" class="button" data-action="load-cad-sample">Посмотреть пример ЧПУ</button><button type="button" class="button" data-route="leads">Все заявки</button>';
    }
    form.classList.add("lead-form-guided");
    const group = name => form.querySelector(`[name="${name}"]`)?.closest(".form-group");
    const heading = (number, title, help, before) => {
      const block = document.createElement("div");
      block.className = "lead-section-heading form-group full";
      block.innerHTML = `<span>${number}</span><div><h3>${title}</h3><p>${help}</p></div>`;
      form.insertBefore(block, before);
    };

    heading("1", "Клиент", "Укажите имя и телефон. Остальные контакты можно добавить позже.", group("clientId"));
    const contacts = document.createElement("details");
    contacts.className = "lead-optional form-group full";
    contacts.innerHTML = '<summary>Реквизиты и адрес доставки <span>необязательно</span></summary><div class="lead-optional-grid"></div>';
    form.insertBefore(contacts, group("subject"));
    for (const name of ["organization", "email", "address"]) contacts.querySelector(".lead-optional-grid").append(group(name));

    heading("2", "Изделие, номер и срок", "Цифры номера введите вручную. Буква добавится по направлению; ведущие нули сохранятся.", group("subject"));
    form.insertBefore(group("leadNumber"), group("due"));
    const positions = document.querySelector("#leadPartsList")?.closest(".form-group");
    heading("3", "Детали заявки", "Здесь внесите обычные детали. Одна строка — один размер с количеством одинаковых штук.", positions);
    positions.querySelector(".lead-parts-head label").textContent = "Размеры и обработка";
    positions.querySelector("#addLeadPart").textContent = "＋ Добавить деталь";
    positions.querySelector(".form-note").textContent = "Укажите размеры и количество; артикул, цвет и толщину — для нужной детали. Фрезеровку заполняйте, только если она нужна. Новая строка наследует эти параметры из предыдущей: при смене цвета или обработки измените их в нужной строке. Раскрой и чертёж для ЧПУ строятся из введённых деталей после сохранения.";
    positions.querySelectorAll(".lead-part-card").forEach(prepareLeadCard);

    const submit = form.querySelector(".lead-submit-actions").closest(".form-group");
    const cnc = document.createElement("div");
    cnc.className = "lead-cnc-guide form-group full";
    cnc.innerHTML = '<strong>Чертёж для ЧПУ</strong><p>После сохранения можно открыть фасад, проверить размеры, фрезеровку и сверление, затем выбрать станок.</p>';
    form.insertBefore(cnc, submit);

    const more = document.createElement("details");
    more.className = "lead-optional form-group full";
    more.innerHTML = '<summary>Источник и комментарий <span>необязательно</span></summary><div class="lead-optional-grid"></div>';
    form.insertBefore(more, cnc);
    for (const name of ["source", "note"]) more.querySelector(".lead-optional-grid").append(group(name));

    const actions = form.querySelector(".lead-submit-actions");
    actions.querySelector('[data-submit-mode="lead"]').textContent = "Сохранить заявку";
    actions.querySelector('[data-submit-mode="cutting"]').textContent = "Сохранить и открыть раскрой";
    actions.querySelector('[data-submit-mode="order"]').textContent = "Оформить заказ";
    actions.insertAdjacentHTML("afterbegin", '<button class="button primary" type="submit" data-submit-mode="cad">Сохранить и открыть чертёж →</button>');
    formPanel?.querySelector(".panel-head p")?.replaceChildren(document.createTextNode("Сначала основные сведения. Остальное можно заполнить позже."));
  }

  const originalWorkspace = renderWorkspace;
  renderWorkspace = function () {
    originalWorkspace();
    enhanceLeadForm();
  };
  renderers.workspace = renderWorkspace;

  // Arrow keys move between the same fields in neighbouring position rows.
  document.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key) ||
        event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const input = event.target;
    if (!input.matches?.("input, select")) return;
    const row = input.closest(".lead-part-card, .part-row");
    const list = row?.closest(".lead-parts-list, #partsList");
    if (!list) return;
    if (event.key === "ArrowLeft" && typeof input.selectionStart === "number" && input.selectionStart > 0) return;
    if (event.key === "ArrowRight" && typeof input.selectionEnd === "number" && input.selectionEnd < input.value.length) return;
    const rows = [...list.querySelectorAll(".lead-part-card, .part-row")];
    const controls = item => [...item.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]), select')]
      .filter(control => control.getClientRects().length && !control.disabled);
    const current = controls(row), column = current.indexOf(input), rowIndex = rows.indexOf(row);
    if (column < 0 || rowIndex < 0) return;
    let nextRow = rowIndex, nextColumn = column;
    if (event.key === "ArrowUp") nextRow--;
    if (event.key === "ArrowDown") nextRow++;
    if (event.key === "ArrowLeft") nextColumn--;
    if (event.key === "ArrowRight") nextColumn++;
    if (nextColumn < 0) { nextRow--; nextColumn = Infinity; }
    if (nextColumn >= current.length) { nextRow++; nextColumn = 0; }
    const destinationRow = rows[nextRow];
    if (!destinationRow) return;
    if (destinationRow.classList.contains("is-collapsed")) {
      destinationRow.classList.remove("is-collapsed");
      const toggle = destinationRow.querySelector(".lead-part-collapse");
      if (toggle) { toggle.setAttribute("aria-expanded", "true"); toggle.textContent = "Свернуть"; }
    }
    const options = controls(destinationRow);
    const destination = options[Math.min(nextColumn, options.length - 1)];
    if (!destination) return;
    event.preventDefault();
    destination.focus();
    destination.select?.();
    destination.scrollIntoView({block:"nearest"});
  });

  // A shareable entry point opens the CAD example in a fresh browser as well.
  window.addEventListener("hashchange", () => { if (location.hash === "#cad-demo") loadCadSample(); });
  if (location.hash === "#cad-demo") loadCadSample();
  else renderRoute();
})();
