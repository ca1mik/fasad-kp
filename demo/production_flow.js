/*
 * Production workflow for the standalone Fasad Portal demo. No build step.
 * Load this script before app.js; its pure functions never mutate their inputs.
 *
 * const flow = window.FasadProduction;
 * const order = flow.bootstrap(existingOrder);
 * const assigned = flow.assign(order, {stage: order.stage, workerId: "W-2"});
 * const reported = flow.reportPart(assigned,
 *   {stage: assigned.stage, partId: assigned.parts[0].id,
 *    done: 4, defects: 0, workerId: "W-2", comment: "Готово"});
 * const {order: next, stock, movements} = flow.completeStage(reported, data.stock,
 *   {workerId: "W-2"});
 *
 * releaseCutting(order, stock, sheetCount) reserves sheets and starts "Распил";
 * completeStage consumes that reserve when the reported cutting stage finishes.
 */
(function (global) {
  "use strict";

  const ROUTES = Object.freeze({
    "Эмаль": ["Расчёт", "Согласование", "Распил", "Кромление", "ЧПУ", "Грунт", "Покраска", "Сборка", "Контроль качества", "Упаковка", "Готов к отгрузке"],
    "ПВХ": ["Расчёт", "Согласование", "Распил", "Кромление", "ЧПУ", "Пресс", "Сборка", "Контроль качества", "Упаковка", "Готов к отгрузке"],
    "Шпон": ["Расчёт", "Согласование", "Распил", "Кромление", "ЧПУ", "Пресс", "Сборка", "Контроль качества", "Упаковка", "Готов к отгрузке"]
  });
  const DEFAULT_ROUTE = ROUTES["Эмаль"];
  const PREPARATION = new Set(["Расчёт", "Согласование"]);
  const FINISHED = "Готов к отгрузке";
  const LEGACY_NAMES = Object.freeze({
    "Раскрой": "Распил", "Фрезеровка": "ЧПУ", "Фрезерование": "ЧПУ",
    "Контроль": "Контроль качества", "Готово": FINISHED
  });

  const copy = value => JSON.parse(JSON.stringify(value));
  const now = () => new Date().toISOString();
  const int = value => Number.isInteger(Number(value)) ? Number(value) : NaN;
  const sum = (items, key) => items.reduce((total, item) => total + Number(item[key] || 0), 0);
  const eventId = () => `EV-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

  function routeFor(order) {
    return [...(ROUTES[String(order?.direction || "").trim()] || DEFAULT_ROUTE)];
  }

  function normalizeStageName(name) {
    return LEGACY_NAMES[name] || name;
  }

  function partCount(order) {
    return (order.parts || []).reduce((total, part) => total + Math.max(0, int(part.qty) || 0), 0);
  }

  function cuttingSignature(order) {
    const spec = order.materialSpec || {};
    return JSON.stringify({
      material: [spec.stockName || spec.name, Number(spec.sheetWidth), Number(spec.sheetHeight), Number(spec.thickness), Number(spec.kerf), Number(spec.margin)],
      parts: (order.parts || []).map(part => [String(part.id), Number(part.height), Number(part.width), Number(part.qty), part.grain !== false])
    });
  }

  function cuttingSignatureV2(order) {
    return JSON.stringify({base:cuttingSignature(order),parts:(order.parts||[]).map(part=>[
      String(part.id),Number(part.thickness||order.materialSpec?.thickness||16),String(part.color||"").trim().toLocaleLowerCase("ru-RU")
    ])});
  }

  function isCuttingCurrent(order) {
    return order.cuttingStatus === "released" && Boolean(order.releasedSignature) &&
      order.releasedSignature === (order.releasedSignatureVersion===2?cuttingSignatureV2(order):cuttingSignature(order));
  }

  function makeStage(name, status, timestamp) {
    return {
      name, status, workerId: null, startedAt: status === "in_progress" ? timestamp : null,
      completedAt: null, blockedAt: null, blockedReason: "", comment: "", reports: []
    };
  }

  function bootstrap(order, timestamp = now()) {
    const result = copy(order);
    const route = routeFor(result);
    result.stage = normalizeStageName(result.stage);
    const current = Math.max(0, route.indexOf(result.stage));
    result.stage = route[current];
    if (result.production?.stages?.length) {
      const existing = new Map(result.production.stages.map(stage => [normalizeStageName(stage.name), stage]));
      result.production.route = route;
      result.production.stages = route.map((name, index) => {
        const stage = existing.get(name) || makeStage(name, "pending", timestamp);
        stage.name = name;
        if (index < current) {
          stage.status = "done";
        } else if (index === current) {
          if (stage.status !== "blocked") stage.status = "in_progress";
          stage.startedAt ||= timestamp;
        } else {
          stage.status = "pending";
        }
        stage.reports ||= [];
        return stage;
      });
      result.production.history ||= [];
      return result;
    }
    result.production = {
      route,
      stages: route.map((name, index) => makeStage(name, index < current ? "done" : index === current ? "in_progress" : "pending", timestamp)),
      history: []
    };
    return result;
  }

  function findStage(order, stageName) {
    const stage = order.production?.stages?.find(item => item.name === stageName);
    if (!stage) throw new Error(`Этап «${stageName}» не найден в маршруте`);
    return stage;
  }

  function history(order, type, stage, timestamp, details = {}) {
    order.production.history.unshift({id: eventId(), type, stage, at: timestamp, ...details});
  }

  function stageProgress(order, stageName = order.stage) {
    const normalized = bootstrap(order);
    const stage = findStage(normalized, stageName);
    const byPart = (normalized.parts || []).map(part => {
      const reports = stage.reports.filter(report => report.partId === part.id);
      const required = Math.max(0, int(part.qty) || 0);
      const done = sum(reports, "done");
      const defects = sum(reports, "defects");
      return {partId: part.id, name: part.name, required, done, defects, remaining: Math.max(0, required - done)};
    });
    const required = sum(byPart, "required");
    const done = sum(byPart, "done");
    const defects = sum(byPart, "defects");
    const remaining = sum(byPart, "remaining");
    const preparation = PREPARATION.has(stageName);
    const ready = stage.status !== "blocked" && (preparation || stageName === FINISHED || (required > 0 && remaining === 0));
    return {stage: stageName, status: stage.status, required, done, defects, remaining,
      percent: required ? Math.min(100, Math.round(done / required * 100)) : preparation || stageName === FINISHED ? 100 : 0,
      ready, byPart};
  }

  function assign(order, options = {}) {
    const result = bootstrap(order, options.at);
    const name = options.stage || result.stage;
    const stage = findStage(result, name);
    const workerId = String(options.workerId || "").trim();
    if (!workerId) throw new Error("Выберите исполнителя");
    if (name !== result.stage || stage.status === "done") throw new Error("Назначить можно только текущий этап");
    stage.workerId = workerId;
    if (stage.status === "pending") stage.status = "in_progress";
    stage.startedAt ||= options.at || now();
    history(result, "assignment", name, options.at || now(), {workerId});
    return result;
  }

  function reportPart(order, options = {}) {
    const result = bootstrap(order, options.at);
    const name = options.stage || result.stage;
    const stage = findStage(result, name);
    if (name !== result.stage || stage.status === "done" || stage.status === "blocked") throw new Error("Отчёт доступен только для открытого этапа");
    if (PREPARATION.has(name) || name === FINISHED) throw new Error("На этом этапе отчёты по деталям не нужны");
    if (name === "Распил" && !isCuttingCurrent(result)) throw new Error("Карта раскроя изменилась. Обновите резерв перед распилом");
    const part = (result.parts || []).find(item => item.id === options.partId);
    if (!part) throw new Error("Деталь не найдена в заказе");
    const done = int(options.done ?? 0), defects = int(options.defects ?? 0);
    if (!Number.isFinite(done) || !Number.isFinite(defects) || done < 0 || defects < 0 || done + defects === 0) {
      throw new Error("Укажите целое количество годных деталей или брака");
    }
    const workerId = String(options.workerId || stage.workerId || "").trim();
    if (!workerId) throw new Error("Выберите исполнителя отчёта");
    const alreadyDone = sum(stage.reports.filter(report => report.partId === part.id), "done");
    if (alreadyDone + done > Number(part.qty)) throw new Error(`Годных деталей больше, чем требуется: ${part.qty}`);
    if (alreadyDone >= Number(part.qty)) throw new Error("Все детали этой позиции уже сданы");
    const timestamp = options.at || now();
    const report = {id: eventId(), partId: part.id, partName: part.name, done, defects, workerId,
      comment: String(options.comment || "").trim(), at: timestamp};
    stage.reports.push(report);
    stage.workerId ||= workerId;
    stage.status = "in_progress";
    stage.startedAt ||= timestamp;
    history(result, "part_report", name, timestamp, {partId: part.id, done, defects, workerId, reportId: report.id});
    result.productionDone = stageProgress(result, name).done;
    return result;
  }

  function canAdvance(order) {
    const normalized = bootstrap(order);
    const stage = findStage(normalized, normalized.stage);
    if (stage.status === "blocked") return {ok: false, reason: stage.blockedReason || "Этап заблокирован"};
    if (normalized.stage === FINISHED) return {ok: false, reason: "Заказ уже готов к отгрузке"};
    if (normalized.stage === "Распил" && !isCuttingCurrent(normalized)) return {ok: false, reason: "Сначала обновите карту раскроя и резерв склада"};
    const progress = stageProgress(normalized);
    if (!progress.ready) return {ok: false, reason: `По этапу «${normalized.stage}» осталось ${progress.remaining} годных деталей`};
    return {ok: true, reason: ""};
  }

  function ensureStock(stock) { return Array.isArray(stock) ? copy(stock) : []; }

  function releaseCutting(order, stock, sheetCount, options = {}) {
    const result = bootstrap(order, options.at);
    const nextStock = ensureStock(stock);
    const rawPlan=Array.isArray(sheetCount)?sheetCount:[{materialName:result.materialSpec?.stockName||result.materialSpec?.name,count:sheetCount}];
    const planned=new Map();
    for(const item of rawPlan){
      const name=String(item.materialName||"").trim(),count=int(item.count);
      if(!name||!Number.isFinite(count)||count<1)throw new Error("Некорректный резерв листов");
      planned.set(name,(planned.get(name)||0)+count);
    }
    const plan=[...planned].map(([materialName,count])=>({materialName,count}));
    const sheets=plan.reduce((total,item)=>total+item.count,0);
    if (!Number.isFinite(sheets) || sheets < 1) throw new Error("Нет пригодных листов в карте раскроя");
    if (result.consumedSheets || !["Расчёт", "Согласование", "Распил"].includes(result.stage)) {
      throw new Error("Раскрой уже выполнен. Верните заказ в подготовку перед изменением карты");
    }
    if (findStage(result, "Распил").reports.length) {
      throw new Error("По распилу уже есть отчёты. Сначала разберите выполненную работу перед заменой карты");
    }
    const previous = Math.max(0, Number(result.reservedSheets || 0));
    const oldPlan=Array.isArray(result.reservedMaterials)?result.reservedMaterials:
      previous?[{materialName:result.reservedMaterial,count:previous}]:[];
    for(const item of plan){
      const material=nextStock.find(stockItem=>stockItem.name===item.materialName);
      if(!material)throw new Error(`Материал «${item.materialName}» не найден на складе`);
      const oldCount=oldPlan.filter(old=>old.materialName===item.materialName).reduce((total,old)=>total+Number(old.count||0),0);
      const available=Number(material.qty)-Number(material.reserved||0)+oldCount;
      if(available<item.count)throw new Error(`На складе недостаточно ${item.materialName}: свободно ${available} лист.`);
    }
    for(const item of oldPlan){const material=nextStock.find(stockItem=>stockItem.name===item.materialName);
      if(material)material.reserved=Math.max(0,Number(material.reserved||0)-Number(item.count||0));}
    for(const item of plan){const material=nextStock.find(stockItem=>stockItem.name===item.materialName);
      material.reserved=Number(material.reserved||0)+item.count;}
    const timestamp = options.at || now();
    result.reservedSheets = sheets;
    result.reservedMaterial = plan.length===1?plan[0].materialName:null;
    result.reservedMaterials = plan;
    result.releasedSignatureVersion = 2;
    result.releasedSignature = cuttingSignatureV2(result);
    result.cuttingStatus = "released";
    result.material = true;
    result.stage = "Распил";
    result.status = "В работе";
    result.productionDone = 0;
    const cutting = findStage(result, "Распил");
    cutting.status = "in_progress";
    cutting.startedAt ||= timestamp;
    cutting.reports = [];
    for (const stage of result.production.stages) {
      if (PREPARATION.has(stage.name)) { stage.status = "done"; stage.completedAt ||= timestamp; }
    }
    history(result, "cutting_released", "Распил", timestamp, {sheets, materials:plan, previous});
    return {order: result, stock: nextStock, movements: plan.map(item=>({kind:"R",title:`${item.materialName} · ${item.count} лист.`,
      note:`${previous?"Обновлён":"Создан"} резерв под ${result.id} по карте раскроя`,time:timestamp}))};
  }

  function completeStage(order, stock, options = {}) {
    const result = bootstrap(order, options.at);
    const nextStock = ensureStock(stock);
    const check = canAdvance(result);
    if (!check.ok) throw new Error(check.reason);
    const name = result.stage;
    const route = routeFor(result);
    const currentIndex = route.indexOf(name);
    const nextName = route[currentIndex + 1];
    const timestamp = options.at || now();
    const current = findStage(result, name);
    const workerId = String(options.workerId || current.workerId || "").trim();
    if (!PREPARATION.has(name) && !workerId) throw new Error("Выберите исполнителя этапа");
    if (name === "Контроль качества" && !String(options.comment || "").trim()) {
      throw new Error("Для контроля качества укажите результат проверки в комментарии");
    }
    const movements = [];
    if (name === "Распил") {
      const sheets = Math.max(0, Number(result.reservedSheets || 0));
      const plan=Array.isArray(result.reservedMaterials)?result.reservedMaterials:
        [{materialName:result.reservedMaterial,count:sheets}];
      if(sheets<1||plan.reduce((total,item)=>total+Number(item.count||0),0)!==sheets||
         plan.some(item=>{const material=nextStock.find(stockItem=>stockItem.name===item.materialName);
           return !material||Number(material.reserved||0)<item.count||Number(material.qty)<item.count;})){
        throw new Error("Резерв листов отсутствует или недостаточен. Обновите раскрой");
      }
      for(const item of plan){const material=nextStock.find(stockItem=>stockItem.name===item.materialName);
        material.reserved-=item.count;material.qty-=item.count;
        movements.push({kind:"−",title:`${material.name} · ${item.count} лист.`,note:`Списано на распил ${result.id}`,time:timestamp});}
      result.consumedSheets = Math.max(0, Number(result.consumedSheets || 0)) + sheets;
      result.reservedSheets = 0;
      result.reservedMaterials=[];
    }
    current.status = "done";
    current.workerId ||= workerId || null;
    current.startedAt ||= timestamp;
    current.completedAt = timestamp;
    current.comment = String(options.comment || "").trim();
    const next = findStage(result, nextName);
    next.status = "in_progress";
    next.startedAt ||= timestamp;
    result.stage = nextName;
    result.status = nextName === FINISHED ? "Готов" : PREPARATION.has(nextName) ? "Согласование" : "В работе";
    result.productionDone = nextName === FINISHED ? partCount(result) : 0;
    history(result, "stage_completed", name, timestamp, {workerId: workerId || null, nextStage: nextName});
    return {order: result, stock: nextStock, movements};
  }

  function setBlocked(order, reason, options = {}) {
    const result = bootstrap(order, options.at);
    const stage = findStage(result, result.stage);
    if (stage.status === "done") throw new Error("Завершённый этап нельзя заблокировать");
    const message = String(reason || "").trim();
    if (!message) throw new Error("Укажите причину остановки");
    const timestamp = options.at || now();
    stage.status = "blocked";
    stage.blockedAt = timestamp;
    stage.blockedReason = message;
    history(result, "blocked", result.stage, timestamp, {reason: message});
    return result;
  }

  function resume(order, options = {}) {
    const result = bootstrap(order, options.at);
    const stage = findStage(result, result.stage);
    if (stage.status !== "blocked") throw new Error("Текущий этап не остановлен");
    stage.status = "in_progress";
    stage.blockedReason = "";
    history(result, "resumed", result.stage, options.at || now());
    return result;
  }

  function workQueue(data) {
    return (data.orders || []).map(order => {
      const normalized = bootstrap(order);
      const stage = findStage(normalized, normalized.stage);
      return {orderId: normalized.id, client: normalized.client, product: normalized.product,
        direction: normalized.direction, due: normalized.due, stage: normalized.stage, status: stage.status,
        workerId: stage.workerId, progress: stageProgress(normalized), partCount: partCount(normalized)};
    }).filter(item => item.stage !== FINISHED);
  }

  function reports(data) {
    return (data.orders || []).flatMap(order => (order.production?.stages || []).flatMap(stage =>
      (stage.reports || []).map(report => ({orderId: order.id, client: order.client,
        product: order.product, stage: stage.name, ...report}))));
  }

  global.FasadProduction = Object.freeze({ROUTES, routeFor, normalizeStageName, partCount, cuttingSignature,
    isCuttingCurrent, bootstrap, stageProgress, assign, reportPart, canAdvance,
    releaseCutting, completeStage, setBlocked, resume, workQueue, reports});
})(window);
