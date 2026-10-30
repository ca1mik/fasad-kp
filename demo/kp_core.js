/* Shared rules for the browser demo. No network or server state is used here. */
(function (root) {
  const DEMO_CLIENTS = {"C-101":["Мария Крылова","+7 920 000-24-18"],"C-102":["ООО «Формат»","+7 831 222-18-40"],"C-103":["Анна Воронова","+7 950 701-33-12"],"C-104":["ООО «Монолит»","+7 831 415-07-02"],"C-105":["Илья Морозов","+7 930 812-44-60"],"C-106":["Студия «Линия»","+7 831 290-14-41"]};
  const DEMO_LEADS = {"L-0281":["Фасады для кухни, эмаль","Марина Соколова"],"L-0280":["Комплект фасадов ПВХ","ООО «Интерьер НН»"],"L-0279":["Гардеробная, шпон","Андрей Петров"],"L-0278":["Фасады для 4 объектов","Студия Forma"]};
  const DEMO_ORDERS = {"F-1048":["Стойка ресепшен",186000],"F-1046":["Фасады, 42 детали",312000],"F-1042":["Кухня · шпон",284000],"F-1041":["Шкаф в прихожую",142000],"F-1038":["Гардеробная",267000],"F-1035":["Кухня · пластик",221000],"F-1029":["Мебель в офис",394000],"F-1027":["Комплект фасадов",118000]};
  const DEMO_STOCK = {"МДФ 16 мм":[84,27],"МДФ 19 мм":[31,18],"Плёнка ПВХ Белый мат":[186,42],"Плёнка ПВХ Графит":[58,31],"Эмаль RAL 9010":[24,8],"Шпон дуба А":[73,29],"Кромка 1×23 дуб":[340,84]};
  const round = value => Math.round((Number(value) + Number.EPSILON) * 100) / 100;
  const positive = value => Number.isFinite(Number(value)) && Number(value) > 0;

  function cleanDemo(source) {
    const value = structuredClone(source || {});
    value.leads = (value.leads || []).filter(row => !(row.demo || DEMO_LEADS[row.id]?.[0] === row.subject && DEMO_LEADS[row.id]?.[1] === row.client && !row.orderId));
    value.orders = (value.orders || []).filter(row => !(row.demo || DEMO_ORDERS[row.id]?.[0] === row.product && DEMO_ORDERS[row.id]?.[1] === row.amount && !(row.payments || []).length));
    const keptOrderIds = new Set(value.orders.map(row => row.id));
    const usedClients = new Set([...value.leads, ...value.orders].map(row => row.clientId).filter(Boolean));
    value.clients = (value.clients || []).filter(row => !(row.demo&&!usedClients.has(row.id) || DEMO_CLIENTS[row.id]?.[0] === row.name && DEMO_CLIENTS[row.id]?.[1] === row.phone && !usedClients.has(row.id)));
    value.priceItems = (value.priceItems || []).filter(row => !row.demo);
    value.stock = (value.stock || []).filter(row => !(row.demo || DEMO_STOCK[row.name]?.[0] === row.qty && DEMO_STOCK[row.name]?.[1] === row.reserved));
    value.stockMovements = (value.stockMovements || []).filter(row => !(row.demo || (/F-1042|F-1046|F-1038/.test(row.note || "") && ![...keptOrderIds].some(id => (row.note || "").includes(id))) || row.note === "Приход · накладная 882"));
    // Existing, unmarked stock rows can be real; keep them. New installs start empty.
    value.depositMovements ||= [];
    return value;
  }

  function normalizeArticle(value) {
    return String(value || "").trim().replace(/^(?:артикул|арт|article|art)[.\s№]*(?=\d)/i, "")
      .trim().toUpperCase();
  }

  function savePriceItem(items, values, existingId = null) {
    const article = normalizeArticle(values.article);
    const name = String(values.name || "").trim();
    const kind = String(values.kind || "").trim();
    const unit = String(values.unit || "").trim();
    const price = Number(values.price);
    if (!article || !name || !kind || !unit || !Number.isFinite(price) || price < 0) {
      throw new Error("Заполните артикул, название, тип работы, единицу и неотрицательную цену");
    }
    if (items.some(row => row.id !== existingId && normalizeArticle(row.article) === article && String(row.kind).trim().toLocaleLowerCase("ru") === kind.toLocaleLowerCase("ru"))) {
      throw new Error("Артикул уже есть в этом типе работы");
    }
    const current = items.find(row => row.id === existingId);
    const item = {id: current?.id || crypto.randomUUID(), article, name, kind, unit, price: round(price)};
    if (current) Object.assign(current, item);
    else items.push(item);
    return item;
  }

  function applyPriceItem(part, item) {
    return {...part, priceItemId: item.id, article: item.article, name: item.name, price: item.price, unit: item.unit, kind: item.kind};
  }

  function quoteRows(parts, items) {
    return parts.map(part => {
      const item = items.find(row => row.id === part.priceItemId);
      // A saved order keeps the agreed article, unit and price even when the catalog changes.
      return item ? {
        ...part,
        article: part.article || item.article,
        name: part.name || item.name,
        price: Object.hasOwn(part, "price") ? part.price : item.price,
        unit: part.unit || item.unit,
        kind: part.kind || item.kind,
      } : {...part};
    });
  }

  function lineQuantity(part) {
    if (["sqm", "м²", "м2"].includes(String(part.unit || "").toLocaleLowerCase("ru"))) {
      return Number(part.qty || 0) * Number(part.height || 0) * Number(part.width || 0) / 1_000_000;
    }
    return Number(part.qty || 0);
  }

  function lineAmount(part) { return round(lineQuantity(part) * Number(part.price || 0)); }

  function depositBalance(state, clientId) {
    return round((state.depositMovements || []).filter(row => row.clientId === clientId)
      .reduce((sum, row) => sum + (row.kind === "topup" || row.kind === "refund" ? row.amount : -row.amount), 0));
  }

  function addDepositMovement(state, clientId, kind, amount, reason = "", orderId = null) {
    if (!positive(amount)) throw new Error("Введите сумму больше нуля");
    const money = round(amount);
    if(money<=0)throw new Error('Минимальная сумма — 0,01 ₽');
    if(!['topup','withdrawal','spend','refund'].includes(kind))throw new Error('Неизвестная операция депозита');
    if ((kind === "withdrawal" || kind === "spend") && money > depositBalance(state, clientId)) {
      throw new Error("На депозите недостаточно средств");
    }
    if (kind === "withdrawal" && !String(reason).trim()) throw new Error("Укажите причину уменьшения депозита");
    const row = {id: crypto.randomUUID(), clientId, kind, amount: money, reason: String(reason).trim(), orderId, date: new Date().toISOString()};
    (state.depositMovements ||= []).push(row);
    return row;
  }

  function addOrderPayment(state, order, amount, method) {
    if (!positive(amount)) throw new Error("Введите сумму больше нуля");
    const money = round(amount);
    if(money<=0)throw new Error('Минимальная сумма — 0,01 ₽');
    if(!order)throw new Error('Заказ не найден');
    if(!['deposit','cash','card','transfer','bank','other','Наличные','Карта','Перевод'].includes(method))throw new Error('Выберите способ оплаты');
    if (money > round(order.amount - order.paidAmount)) throw new Error("Сумма превышает остаток заказа");
    const row = {id: crypto.randomUUID(), amount: money, method, date: new Date().toISOString()};
    if (method === "deposit") {const movement=addDepositMovement(state, order.clientId, "spend", money, `Оплата заказа ${order.id}`, order.id);movement.paymentId=row.id;}
    (order.payments ||= []).push(row);
    order.paidAmount = round(order.payments.reduce((sum, payment) => sum + payment.amount, 0));
    order.paid = order.amount ? Math.round(order.paidAmount / order.amount * 100) : 0;
    return row;
  }

  function deleteOrderPayment(state, order, paymentId) {
    const index = (order.payments || []).findIndex(row => row.id === paymentId);
    if (index < 0) throw new Error("Оплата не найдена");
    const payment=order.payments[index];
    if (payment.method === "deposit") {const movement=addDepositMovement(state, order.clientId, "refund", payment.amount, `Удалена оплата заказа ${order.id}`, order.id);movement.paymentId=payment.id;}
    order.payments.splice(index, 1);
    order.paidAmount = round(order.payments.reduce((sum, row) => sum + row.amount, 0));
    order.paid = order.amount ? Math.round(order.paidAmount / order.amount * 100) : 0;
    return payment;
  }

  root.FasadKP = {cleanDemo, normalizeArticle, savePriceItem, applyPriceItem, quoteRows, lineQuantity, lineAmount,
    depositBalance, addDepositMovement, addOrderPayment, deleteOrderPayment};
})(typeof window === "undefined" ? globalThis : window);
