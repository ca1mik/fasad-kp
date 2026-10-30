const initialData = {
  leads: [],
  clients: [],
  orders: [],
  quotes: [],
  priceItems: [],
  depositMovements: [],
  factorySettings: FasadFactorySettings.defaults(),
  machines: [
    {id:"M-1",name:"Демо: фрезер 1",controller:"Контроллер не настроен"},
    {id:"M-2",name:"Демо: фрезер 2",controller:"Контроллер не настроен"}
  ],
  workers: [
    {id:"W-1",name:"Сергей Мельников",initials:"СМ",role:"Технолог",active:3,reports:148,done:724,defect:4,load:88,color:"green"},
    {id:"W-2",name:"Роман Ильин",initials:"РИ",role:"Оператор ЧПУ",active:2,reports:121,done:658,defect:7,load:76,color:"blue"},
    {id:"W-3",name:"Павел Егоров",initials:"ПЕ",role:"Маляр",active:2,reports:96,done:403,defect:3,load:69,color:"rose"},
    {id:"W-4",name:"Ирина Лебедева",initials:"ИЛ",role:"Упаковка",active:1,reports:84,done:512,defect:1,load:54,color:""},
    {id:"W-5",name:"Денис Котов",initials:"ДК",role:"Прессовщик",active:2,reports:76,done:381,defect:5,load:81,color:"blue"},
    {id:"W-6",name:"Артём Волков",initials:"АВ",role:"Комплектовщик",active:1,reports:59,done:298,defect:0,load:46,color:"green"}
  ],
  stock: [],
  stockMovements: []
};

const PRODUCTION_STAGES=["Расчёт","Согласование","Распил","Фрезеровка","Грунт","Покраска","Пресс","Упаковка","Готов к отгрузке"];
const LEGACY_MATERIAL_PRESETS={
  "МДФ 16 мм":{name:"МДФ 16 мм",thickness:16,sheetWidth:2800,sheetHeight:2070,price:0,stockName:"МДФ 16 мм"},
  "МДФ 19 мм":{name:"МДФ 19 мм",thickness:19,sheetWidth:2800,sheetHeight:2070,price:0,stockName:"МДФ 19 мм"}
};
const MATERIAL_PRESETS=FasadFactorySettings.defaults().materials;
const DEFAULT_PARTS=[];
const SAMPLE_LEAD_PARTS={};
const clone=value=>JSON.parse(JSON.stringify(value));
const uid=()=>`P-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,7)}`;

function partsForOrder(){return [];}
function normalizeData(source){
  const result=source&&source.orders?source:clone(initialData);
  result.factorySettings=FasadFactorySettings.normalize(result.factorySettings);
  Object.assign(MATERIAL_PRESETS,result.factorySettings.materials);
  result.leads=result.leads||[];
  result.clients=result.clients||[];
  result.stock=result.stock||[];
  result.priceItems=result.priceItems||[];
  result.quotes=result.quotes||[];
  result.depositMovements=result.depositMovements||[];
  result.machines=Array.isArray(result.machines)?result.machines:clone(initialData.machines);
  result.orders.forEach((order,index)=>{
    const hadProduction=Boolean(order.production?.stages?.length);
    if(!Array.isArray(order.parts))order.parts=[];
    order.parts=order.parts.map((p,i)=>({id:p.id||`${order.id}-P${i+1}`,name:p.name||"Деталь",height:Number(p.height??p[1]??600),width:Number(p.width??p[2]??400),qty:Number(p.qty??p[3]??1),price:Number(p.price??p[4]??0),edge:p.edge||"4 стороны",grain:p.grain!==false,no_rotation:p.no_rotation===true,article:p.article||"",color:p.color||"",milling:p.milling||"",thickness:Number(p.thickness||16),priceItemId:p.priceItemId||null,kind:p.kind||"",unit:p.unit||"шт",cadModel:p.cadModel||null}));
    order.materialSpec={...LEGACY_MATERIAL_PRESETS["МДФ 16 мм"],kerf:4,margin:10,...order.materialSpec};
    order.cuttingStatus=order.cuttingStatus||"draft";
    order.productionDone=Number(order.productionDone||0);
    order.paidAmount=Number(order.paidAmount??order.amount*order.paid/100);
    if(!Array.isArray(order.payments))order.payments=order.paidAmount?[{id:uid(),amount:order.paidAmount,method:"legacy",date:new Date().toISOString()}]:[];
    order.payments.forEach(payment=>{payment.id ||= uid();});
    if(order.cuttingStatus==="released"&&!order.releasedSignature)order.cuttingStatus="draft";
    Object.assign(order,FasadProduction.bootstrap(order));
    if(!hadProduction&&["Распил","Фрезеровка","Грунт","Покраска","Пресс","Упаковка"].includes(order.stage)){
      const workerId=["Распил","Фрезеровка"].includes(order.stage)?"W-2":["Грунт","Покраска"].includes(order.stage)?"W-3":order.stage==="Пресс"?"W-5":"W-4";
      Object.assign(order,FasadProduction.assign(order,{workerId}));
    }
  });
  result.stockMovements=result.stockMovements||[];
  result.clients.forEach(client=>{client.organization=client.organization||"";client.comment=client.comment||"";client.createdAt=client.createdAt||"2026-09-01";});
  result.leads.forEach(lead=>{
    lead.parts=(lead.parts||[]).map((part,index)=>({id:part.id||`${lead.id}-P${index+1}`,name:part.name||"Деталь",height:Number(part.height??600),width:Number(part.width??400),qty:Number(part.qty??1),price:Number(part.price??0),edge:part.edge||"4 стороны",grain:part.grain!==false,article:part.article||"",color:part.color||"",milling:part.milling||"",thickness:Number(part.thickness||16),priceItemId:part.priceItemId||null,kind:part.kind||"",unit:part.unit||"шт",grain:part.grain===true,no_rotation:part.no_rotation===true,cadModel:part.cadModel||null}));
    lead.materialSpec={...LEGACY_MATERIAL_PRESETS["МДФ 16 мм"],kerf:4,margin:10,...lead.materialSpec};
    lead.cuttingStatus=lead.cuttingStatus||"draft";
    if(!lead.clientId){let client=result.clients.find(c=>c.name.toLowerCase()===String(lead.client).toLowerCase()||(lead.phone&&lead.phone!=="—"&&c.phone===lead.phone));
      if(!client){const id=`C-${Math.max(0,...result.clients.map(c=>Number(c.id.slice(2))||0))+1}`;client={id,name:lead.client,initials:String(lead.client).split(" ").map(x=>x[0]).join("").slice(0,2),organization:"",phone:lead.phone||"—",email:"—",city:"—",address:"—",comment:"",type:"Частный клиент",createdAt:new Date().toISOString().slice(0,10)};result.clients.push(client);}
      lead.clientId=client.id;
    }
    lead.direction=lead.direction||("ПВХ"===lead.subject?.match(/ПВХ/)?.[0]?"ПВХ":"Эмаль");
    lead.due=lead.due||"";
    lead.note=lead.note||"";
  });
  reconcileData(result);
  return result;
}

function reconcileData(target){
  target.clients.forEach(client=>{
    const orders=target.orders.filter(order=>order.clientId===client.id);
    client.orders=orders.length;
    client.revenue=orders.reduce((sum,order)=>sum+Number(order.amount||0),0);
    client.balance=orders.reduce((sum,order)=>sum+Math.max(0,Number(order.amount||0)-Number(order.paidAmount||0)),0);
  });
}

let data = normalizeData(loadData());
let currentRoute = "workspace";
let lastRenderedHash = null;
let activeOrderFilter = "Все";
const batchSelectedIds = new Set();

function loadData(){
  if(window.FasadWorkspace){if(window.FasadWorkspace.initialData)return window.FasadWorkspace.initialData;const empty=structuredClone(initialData);empty.workers=[];empty.machines=[];return empty;}
  const raw=localStorage.getItem("fasad-demo-data");
  if(!raw)return structuredClone(initialData);
  try {
    const saved=JSON.parse(raw);
    if(!localStorage.getItem("fasad-demo-clean-v2")){
      try {
        localStorage.setItem(`fasad-demo-backup-${new Date().toISOString()}`,raw);
        const cleaned=FasadKP.cleanDemo(saved);
        localStorage.setItem("fasad-demo-data",JSON.stringify(cleaned));
        localStorage.setItem("fasad-demo-clean-v2","1");
        return cleaned;
      } catch { return saved; }
    }
    return saved;
  } catch { return structuredClone(initialData); }
}
function saveData(){ reconcileData(data);if(window.FasadWorkspace){return window.FasadWorkspace.save(data);}localStorage.setItem("fasad-demo-data",JSON.stringify(data));return Promise.resolve(true); }
function esc(value){return String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));}
const money = value => new Intl.NumberFormat("ru-RU").format(value)+" ₽";
const app = document.querySelector("#app");
const crumbs = document.querySelector("#crumbs");

function badge(value){
  const type = /проср|блок|долг/.test(value.toLowerCase())?"red":/нов|расч|ожида/.test(value.toLowerCase())?"amber":/готов|оплач|заверш/.test(value.toLowerCase())?"green":/соглас|фрез|пресс|покра|работ/.test(value.toLowerCase())?"blue":"gray";
  return `<span class="badge ${type}"><i class="dot"></i>${esc(value)}</span>`;
}
function avatar(initials,color=""){ return `<i class="avatar ${color}">${esc(initials)}</i>`; }
function pageHead(eyebrow,title,lead,actions=""){
  return `<header class="page-head"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="lead">${lead}</p></div><div class="head-actions">${actions}</div></header>`;
}
function stat(label,value,note,delta="",dark=false){
  return `<article class="stat ${dark?"dark":""}"><div class="label"><span>${label}</span><i class="delta ${delta.startsWith("-")?"down":""}">${delta}</i></div><strong>${value}</strong><small>${note}</small>${dark?'<svg class="spark" viewBox="0 0 80 28"><path d="M1 25 C13 18,20 23,30 14 S48 17,57 8 S70 11,79 2"/></svg>':""}</article>`;
}
function orderRow(order){
  return `<tr class="clickable" data-order="${order.id}">
    <td><strong class="num">${order.id}</strong></td>
    <td><div class="client-cell">${avatar(order.initials)}<div><strong>${esc(order.client)}</strong><small>${esc(order.manager)}</small></div></div></td>
    <td>${esc(order.product)}</td><td>${esc(order.direction)}</td><td>${badge(order.stage)}</td>
    <td class="${order.risk?"danger-text":""}">${order.due}</td><td><strong class="num">${money(order.amount)}</strong></td>
    <td><div class="num">${order.paid}%</div><div class="progress-line"><i style="width:${order.paid}%"></i></div></td>
    <td><button class="link">Открыть →</button></td></tr>`;
}
function leadPartRow(part={}){return `<div class="lead-part-card" data-source-part-id="${esc(part.id||"")}"><div class="lead-part-row"><input name="partName" placeholder="Название" value="${esc(part.name||"")}" required><input name="partHeight" type="number" min="1" placeholder="В, мм" value="${part.height??""}" required><input name="partWidth" type="number" min="1" placeholder="Ш, мм" value="${part.width??""}" required><input name="partQty" type="number" min="1" max="500" placeholder="Шт." value="${part.qty??1}" required><button type="button" aria-label="Удалить позицию">×</button></div><div class="lead-part-extra"><label>Артикул<input name="partArticle" placeholder="Артикул" value="${esc(part.article||"")}" list="priceArticles"></label><label>Цвет<input name="partColor" placeholder="Цвет" value="${esc(part.color||"")}"></label><button type="button" class="link" data-clear="partColor">Очистить всё</button><label>Фрезеровка<input name="partMilling" placeholder="Фрезеровка" value="${esc(part.milling||"")}"></label><button type="button" class="link" data-clear="partMilling">Очистить всё</button><input name="partThickness" type="number" min="1" placeholder="Толщ., мм" value="${part.thickness??""}"><input name="partPrice" type="number" min="0" placeholder="Цена/шт" value="${part.price??""}"><input name="priceItemId" type="hidden" value="${esc(part.priceItemId||"")}"><datalist id="priceArticles">${data.priceItems.map(item=>`<option value="${esc(item.article)}">${esc(item.name)}</option>`).join("")}</datalist></div></div>`;}
function partsFromForm(form,prefix){const source=data.leads.find(lead=>lead.id===form.dataset.leadId)||data.leads.find(lead=>lead.id===prefix);return [...form.querySelectorAll(".lead-part-card")].map((card,index)=>{const original=source?.parts.find(part=>part.id===card.dataset.sourcePartId);const priceItemId=card.querySelector('[name="priceItemId"]').value||null;return {id:`${prefix}-P${index+1}`,name:card.querySelector('[name="partName"]').value.trim(),height:Number(card.querySelector('[name="partHeight"]').value),width:Number(card.querySelector('[name="partWidth"]').value),qty:Number(card.querySelector('[name="partQty"]').value),article:card.querySelector('[name="partArticle"]').value.trim(),color:card.querySelector('[name="partColor"]').value.trim(),milling:card.querySelector('[name="partMilling"]').value.trim(),thickness:Number(card.querySelector('[name="partThickness"]').value)||16,price:Number(card.querySelector('[name="partPrice"]').value)||0,priceItemId,kind:card.querySelector('[name="partKind"]')?.value||original?.kind||data.priceItems.find(item=>item.id===priceItemId)?.kind||"",unit:card.querySelector('[name="partUnit"]')?.value||data.priceItems.find(item=>item.id===priceItemId)?.unit||"шт",edge:"4 стороны",no_rotation:card.querySelector('[name="partNoRotation"]')?.checked??original?.no_rotation??false,grain:card.querySelector('[name="partGrain"]')?.checked??original?.grain??false,cadModel:original?.cadModel?clone(original.cadModel):null};});}
function partsEstimate(parts){return FasadRules.round2(parts.reduce((sum,part)=>sum+FasadKP.lineAmount(part),0));}
function refreshLeadTotal(form){const target=form.querySelector("#leadPartsTotal");if(target){const parts=partsFromForm(form,"PREVIEW");target.textContent=`${parts.length} позиций · ${parts.reduce((n,p)=>n+p.qty,0)} деталей · ${FasadRules.area(orderPartArea({parts}))} м² · предварительно ${money(partsEstimate(parts))}`;}}
function nextRecordId(prefix,collection,base){return `${prefix}-${String(Math.max(base,...collection.map(item=>Number(item.id.replace(/\D/g,""))||0))+1).padStart(4,"0")}`;}
function leadIdFromNumber(number,direction){
  const digits=String(number??'').trim();
  return /^\d+$/.test(digits)?digits+'-'+({'Эмаль':'Э','ПВХ':'П','Шпон':'Ш'}[direction]||'Э'):null;
}
function resolveLeadClient(form){
  const f=new FormData(form),name=String(f.get("client")||"").trim(),phone=String(f.get("phone")||"").trim();
  let client=data.clients.find(c=>c.id===f.get("clientId"));
  if(!client)client=data.clients.find(c=>c.name.toLowerCase()===name.toLowerCase()||(phone&&c.phone===phone));
  if(!client){client={id:`C-${Math.max(0,...data.clients.map(c=>Number(c.id.slice(2))||0))+1}`,name,initials:name.split(" ").map(x=>x[0]).join("").slice(0,2),organization:"",phone:"—",email:"—",city:"—",address:"—",comment:"",type:"Частный клиент",createdAt:new Date().toISOString().slice(0,10)};data.clients.unshift(client);}
  client.name=name;client.initials=name.split(" ").map(x=>x[0]).join("").slice(0,2);
  for(const field of ["organization","phone","email","address"]){const value=String(f.get(field)||"").trim();if(value)client[field]=value;}
  return client;
}
function leadRow(lead){
  const count=lead.parts?.reduce((sum,p)=>sum+p.qty,0)||0;
  return `<tr class="clickable" data-open-lead="${esc(lead.id)}"><td><strong class="num">${esc(lead.id)}</strong></td><td><div class="client-cell">${avatar(String(lead.client).split(" ").map(x=>x[0]).join("").slice(0,2))}<div><strong>${esc(lead.client)}</strong><small>${esc(lead.phone)}</small></div></div></td><td>${esc(lead.subject)}<small class="lead-detail-count">${lead.parts?.length||0} позиций · ${count} деталей</small></td><td>${esc(lead.source)}</td><td>${badge(lead.status)}</td><td>${esc(lead.date)}</td><td>${lead.orderId?`<button class="link" data-order="${lead.orderId}">${lead.orderId} →</button>`:`<button class="link" data-action="lead-to-order" data-lead="${esc(lead.id)}">В заказ →</button>`}</td></tr>`;
}

function loadCadSample(){
  const existing=data.orders.find(order=>order.demo&&order.sampleKey==="cad-v1");
  if(existing){navigate("cad",`${existing.id}/${existing.parts[0].id}`);return;}
  const suffix=Date.now().toString(36),clientId=`C-CAD-${suffix}`,orderId=`F-CAD-${suffix}`;
  const client={id:clientId,name:"Демо-мастерская",initials:"ДМ",phone:"—",email:"—",city:"—",address:"—",type:"Демо",demo:true};
  const parts=[
    {id:`${orderId}-P1`,name:"Фасад с рамкой",height:700,width:400,thickness:16,qty:2,price:4500,unit:"шт",edge:"4 стороны",grain:true,article:"DEMO-110",color:"Белый софт",milling:"Скруглённая рамка"},
    {id:`${orderId}-P2`,name:"Фасад с пазами",height:600,width:350,thickness:16,qty:1,price:3900,unit:"шт",edge:"4 стороны",grain:false,article:"DEMO-128",color:"Эвкалипт",milling:"Вертикальные пазы"}
  ];
  parts[0].cadModel=FasadCAD.modelForPart(parts[0],{template:"rounded_frame",params:{inset:40,bandWidth:8,radius:20,depth:2}});
  parts[1].cadModel=FasadCAD.modelForPart(parts[1],{template:"vertical_grooves",params:{inset:30,grooveWidth:6,grooveCount:3,grooveSpacing:80,depth:2}});
  const order={id:orderId,clientId,client:client.name,initials:client.initials,product:"Образец фасадов для CAD",direction:"Эмаль",stage:"Расчёт",status:"Новый",due:"—",amount:partsEstimate(parts),paid:0,paidAmount:0,payments:[],manager:"Демо",material:false,risk:false,parts,materialSpec:FasadFactorySettings.snapshot(data.factorySettings,"МДФ 16 мм"),materialSpecs:materialSnapshots(data.factorySettings),cuttingStatus:"draft",productionDone:0,demo:true,sampleKey:"cad-v1"};
  Object.assign(order,FasadProduction.bootstrap(order));
  data.clients.push(client);data.orders.push(order);
  localStorage.setItem("fasad-demo-clean-v2","1");
  saveData();navigate("cad",`${orderId}/${parts[0].id}`);toast("Открыт пример фасада с фрезеровкой и выбором станка");
}

function renderWorkspace(){
  crumbs.textContent="Рабочее место";
  app.innerHTML = pageHead("Рабочее место менеджера","Принять заявку и сразу передать её в работу","Клиент, расчёт, заказ и производство связаны в одной цепочке. Новую заявку можно зафиксировать за минуту.",'<button class="button" data-action="load-cad-sample">Открыть пример CAD</button><button class="button" data-route="orders">Все заказы</button><button class="button primary" data-action="new-order">＋ Новый заказ</button>')+
  `<section class="stats">${stat("Новые заявки",data.leads.filter(l=>l.status==="Новая").length,"требуют обработки")}${stat("Расчёты",data.orders.filter(o=>o.stage==="Расчёт").length,"заказов на расчёте")}${stat("В работе",data.orders.filter(o=>o.status==="В работе").length,"заказов в цехе","",true)}${stat("Готовы",data.orders.filter(o=>o.status==="Готов").length,"к отгрузке")}${stat("Оплаты",money(data.orders.reduce((s,o)=>s+o.paidAmount,0)),"получено по заказам")}</section>
  <section class="grid sidebar-grid">
    <div class="stack">
      <article class="panel">
        <div class="panel-head"><div><h2>Новая заявка</h2><p>Заказчик, позиции, срок и расчёт в одном месте</p></div></div>
        <div class="panel-body"><form id="leadForm" class="form-grid">
          <div class="form-group full"><label>Выбрать заказчика из базы</label><select name="clientId" id="leadClientSelect"><option value="">＋ Новый заказчик</option>${data.clients.map(c=>`<option value="${c.id}">${esc(c.name)} · ${esc(c.phone)}</option>`).join("")}</select></div>
          <div class="form-group"><label>Клиент или компания</label><input name="client" required placeholder="Имя или компания"></div>
          <div class="form-group"><label>Организация</label><input name="organization" placeholder="Для счёта и документов"></div>
          <div class="form-group"><label>Телефон</label><input name="phone" placeholder="+7 999 000-00-00"></div>
          <div class="form-group"><label>Email</label><input name="email" type="email" placeholder="mail@example.ru"></div>
          <div class="form-group full"><label>Адрес доставки</label><input name="address" placeholder="Город, улица, дом"></div>
          <div class="form-group full"><label>Что нужно изготовить</label><textarea name="subject" required placeholder="Кухня, фасады, материал, примерные размеры…"></textarea></div>
          <div class="form-group"><label>Номер заявки</label><input name="leadNumber" inputmode="numeric" pattern="[0-9]+" maxlength="80" required placeholder="Например, 0001"><small>Цифры введите вручную. Ведущие нули сохранятся; буква добавится по направлению.</small></div>
          <div class="form-group"><label>Срок изготовления</label><input name="due" type="date"></div>
          <div class="form-group"><label>Источник</label><select name="source"><option>Звонок</option><option>Сайт</option><option>Email</option><option>Telegram</option><option>WhatsApp</option><option>Менеджер</option></select></div>
          <div class="form-group"><label>Направление</label><select name="direction"><option>Эмаль</option><option>ПВХ</option><option>Шпон</option></select></div>
          <div class="form-group full"><div class="lead-parts-head"><label>Детали заявки</label><button type="button" class="link" id="importExcelButton">↑ Импорт Excel</button><input id="importExcelFile" type="file" accept=".xlsx,.xls,.csv" hidden><button type="button" class="link" id="addLeadPart">＋ Добавить деталь</button></div><div class="lead-parts-list" id="leadPartsList">${leadPartRow()}</div><div class="form-note">Одна строка — один размер и количество одинаковых деталей. Артикул, цвет и толщина относятся к этой строке; фрезеровку указывайте, если нужна.</div></div>
          <div class="form-group full"><label>Комментарий</label><textarea name="note" placeholder="Цвет, пожелания клиента, особые условия"></textarea></div>
          <div class="form-group full"><div class="lead-total" id="leadPartsTotal">Предварительно: 0 ₽</div><div class="lead-submit-actions"><button class="button" type="submit" data-submit-mode="lead">Только заявку</button><button class="button" type="submit" data-submit-mode="cutting">Создать и раскроить</button><button class="button amber" type="submit" data-submit-mode="order">Создать заказ</button></div></div>
        </form></div>
      </article>
      <article class="panel pad"><div class="panel-head" style="padding:0 0 12px"><div><h3>Сегодня</h3><p>Ближайшие действия менеджера</p></div></div>
        <div class="activity-list">
          <div class="empty">Новых действий пока нет</div>
        </div>
      </article>
    </div>
    <article class="panel">
      <div class="panel-head"><div><h2>Мои заявки</h2><p>Последние обращения и расчёты</p></div></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Заявка</th><th>Клиент</th><th>Что нужно</th><th>Источник</th><th>Статус</th><th>Создана</th><th></th></tr></thead><tbody>
      ${data.leads.map(leadRow).join("")}
      </tbody></table></div>
    </article>
  </section>`;
}

function renderLeads(){
  crumbs.textContent="Заявки";
  app.innerHTML=pageHead("Клиенты и расчёты","Заявки","Каждая заявка связана с заказчиком, позициями, раскроем и будущим заказом.",'<button class="button primary" data-route="workspace">＋ Новая заявка</button>')+
  `<section class="stats">${stat("Всего заявок",data.leads.length,"в журнале")}${stat("Новые",data.leads.filter(l=>l.status==="Новая").length,"ожидают ответа")}${stat("На расчёте",data.leads.filter(l=>l.status==="Расчёт").length,"смета в подготовке","",true)}${stat("В заказе",data.leads.filter(l=>l.orderId).length,"переданы в работу")}${stat("Деталей",data.leads.reduce((sum,l)=>sum+orderPartCount(l),0),"в заявках")}</section>
  <article class="panel"><div class="filters"><input class="field grow" id="leadSearch" placeholder="Номер, заказчик, телефон или изделие"><select class="select" id="leadStatusFilter"><option>Все статусы</option><option>Новая</option><option>Расчёт</option><option>Согласование</option><option>В заказе</option></select></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Заявка</th><th>Заказчик</th><th>Изделие и детали</th><th>Источник</th><th>Статус</th><th>Создана</th><th></th></tr></thead><tbody id="leadsBody">${data.leads.map(leadRow).join("")}</tbody></table></div></article>`;
}
function renderLead(id){
  const lead=data.leads.find(l=>l.id===id);if(!lead)return navigate("leads");
  const client=data.clients.find(c=>c.id===lead.clientId);
  crumbs.textContent=`Заявки / ${lead.id}`;
  app.innerHTML=pageHead(`Заявка ${esc(lead.id)}`,esc(lead.subject),`${esc(lead.client)} · ${lead.direction} · ${orderPartCount(lead)} деталей`,`<button class="button" data-action="edit-lead" data-id="${esc(id)}">✎ Редактировать</button><button class="button" data-action="open-lead-cutting" data-id="${esc(id)}">✂ Раскрой заявки</button>${lead.orderId?`<button class="button primary" data-order="${lead.orderId}">Заказ ${lead.orderId} →</button>`:`<button class="button primary" data-action="lead-to-order" data-lead="${esc(id)}">Создать заказ →</button>`}`)+
  `<section class="grid asym"><div class="stack"><article class="panel pad"><div class="detail-grid"><div class="detail"><small>Заказчик</small><strong><button class="link" data-client="${client?.id||""}">${esc(client?.name||lead.client)}</button></strong></div><div class="detail"><small>Телефон</small><strong>${esc(lead.phone||"—")}</strong></div><div class="detail"><small>Направление</small><strong>${lead.direction}</strong></div><div class="detail"><small>Срок</small><strong>${lead.due?new Date(`${lead.due}T00:00:00`).toLocaleDateString("ru-RU"):"Не указан"}</strong></div><div class="detail"><small>Источник</small><strong>${esc(lead.source)}</strong></div><div class="detail"><small>Адрес</small><strong>${esc(lead.address||"—")}</strong></div><div class="detail"><small>Статус</small><strong>${lead.status}</strong></div><div class="detail"><small>Организация</small><strong>${esc(lead.organization||"—")}</strong></div></div></article>
  <article class="panel"><div class="panel-head"><div><h2>Детали заявки</h2><p>Эти детали попадают в раскрой и переходят в заказ</p></div><strong>${money(partsEstimate(lead.parts))}</strong></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Деталь</th><th>Высота</th><th>Ширина</th><th>Шт.</th><th>Толщина</th><th>Артикул</th><th>Цвет</th><th>Фрезеровка</th><th>Цена / единица</th><th>Сумма</th></tr></thead><tbody>${lead.parts.map(p=>`<tr><td><strong>${esc(p.name)}</strong></td><td>${p.height}</td><td>${p.width}</td><td>${p.qty}</td><td>${p.thickness} мм</td><td>${esc(p.article||"—")}</td><td>${esc(p.color||"—")}</td><td>${esc(p.milling||"—")}</td><td>${money(p.price)} / ${esc(p.unit||"??")}</td><td><strong>${money(FasadKP.lineAmount(p))}</strong></td></tr>`).join("")||'<tr><td colspan="10" class="empty">Деталей пока нет</td></tr>'}</tbody></table></div></article></div>
  <aside class="stack"><article class="panel pad"><h3 class="card-title">Итоги заявки</h3><div class="readiness-list"><div><span>Позиции</span><strong>${lead.parts.length}</strong></div><div><span>Детали</span><strong>${orderPartCount(lead)} шт.</strong></div><div><span>Площадь</span><strong>${FasadRules.area(orderPartArea(lead))} м²</strong></div><div><span>Предварительная сумма</span><strong>${money(lead.amount)}</strong></div></div><button class="button amber wide" data-action="open-lead-cutting" data-id="${esc(id)}">Показать карту раскроя</button></article><article class="panel pad"><h3 class="card-title">Комментарий</h3><p class="muted">${esc(lead.note||"Пока без комментария")}</p></article><article class="panel pad"><h3 class="card-title">Связи</h3><div class="readiness-list"><div><span>Заказчик</span><strong>${client?`<button class="link" data-client="${client.id}">${esc(client.name)}</button>`:"—"}</strong></div><div><span>Заказ</span><strong>${lead.orderId?`<button class="link" data-order="${lead.orderId}">${lead.orderId}</button>`:"Ещё не создан"}</strong></div></div></article></aside></section>`;
}

function renderDashboard(){
  crumbs.textContent="Сводка";
  const total=data.orders.reduce((sum,order)=>sum+Number(order.amount||0),0);
  const paid=data.orders.reduce((sum,order)=>sum+Number(order.paidAmount||0),0);
  const active=data.orders.filter(order=>order.status==="В работе").length;
  app.innerHTML=pageHead("Операционный обзор","Сводка по системе","Показатели из текущих заявок, заказов и оплат.",'<button class="button" data-route="reports">Открыть отчёт</button><button class="button primary" data-route="production">Открыть производство</button>')+
    `<section class="stats">${stat("Клиенты",data.clients.length,"в базе")}${stat("Заявки",data.leads.length,"обращений")}${stat("Заказы",data.orders.length,money(total),"",true)}${stat("Оплачено",money(paid),"по заказам")}${stat("В работе",active,"заказов")}</section>
    <article class="panel"><div class="panel-head"><div><h2>Последние заказы</h2><p>Суммы и поступления по заказам</p></div><button class="link" data-route="orders">Все заказы →</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Заказ</th><th>Клиент</th><th>Сумма</th><th>Оплачено</th></tr></thead><tbody>${data.orders.slice(0,8).map(order=>`<tr class="clickable" data-order="${esc(order.id)}"><td>${esc(order.id)}</td><td>${esc(order.client)}</td><td>${money(order.amount)}</td><td>${money(order.paidAmount)}</td></tr>`).join("")||'<tr><td colspan="4" class="empty">Заказов пока нет</td></tr>'}</tbody></table></div></article>`;
}

function renderClients(){
  crumbs.textContent="Клиенты";
  const revenue=data.clients.reduce((s,c)=>s+c.revenue,0);
  app.innerHTML=pageHead("Клиенты","База клиентов","Адреса, расчёты, заказы, оплаты и вся история общения с клиентом.",'<button class="button primary" data-action="new-client">＋ Новый клиент</button>')+
  `<section class="stats">${stat("Заказчиков",data.clients.length,"в базе")}${stat("С заявками",data.clients.filter(c=>data.leads.some(l=>l.clientId===c.id)).length,"история обращений")}${stat("Сумма заказов",money(revenue),"по текущим заказам", "",true)}${stat("К получению",money(data.clients.reduce((s,c)=>s+c.balance,0)),"остаток по заказам")}${stat("Повторные",data.clients.filter(c=>c.orders>1).length,"2 и более заказов")}</section>
  <article class="panel"><div class="filters"><input class="field grow" id="clientSearch" placeholder="Поиск по имени, телефону или email"></div>
  <div class="table-wrap"><table class="data-table"><thead><tr><th>Клиент</th><th>Тип</th><th>Контакты</th><th>Город / адрес</th><th>Заказов</th><th>Выручка</th><th>Баланс</th><th></th></tr></thead><tbody id="clientsBody">${clientRows(data.clients)}</tbody></table></div></article>`;
}
function clientRows(items){return items.map(c=>`<tr class="clickable" data-client="${c.id}"><td><div class="client-cell">${avatar(c.initials)}<strong>${esc(c.name)}</strong></div></td><td>${esc(c.type)}</td><td><strong>${esc(c.phone)}</strong><br><span class="muted">${esc(c.email)}</span></td><td>${esc(c.city)}<br><span class="muted">${esc(c.address)}</span></td><td>${c.orders}</td><td><strong>${money(c.revenue)}</strong></td><td class="${c.balance?"danger-text":"success-text"}">${c.balance?money(c.balance):"Нет долга"}</td><td><button class="link">Открыть →</button></td></tr>`).join("")}

function renderClient(id){
  const client=data.clients.find(c=>c.id===id);if(!client)return navigate("clients");
  const leads=data.leads.filter(l=>l.clientId===id),orders=data.orders.filter(o=>o.clientId===id);
  const payments=orders.flatMap(o=>(o.payments||[]).map(p=>({...p,orderId:o.id}))).sort((a,b)=>b.date.localeCompare(a.date));
  crumbs.textContent=`Клиенты / ${client.name}`;
  app.innerHTML=pageHead("Карточка заказчика",esc(client.name),`${esc(client.type)} · ${esc(client.organization||client.city||"Контакт")}`,`<button class="button" data-action="edit-client" data-id="${client.id}">✎ Редактировать</button><button class="button" data-route="workspace">＋ Заявка</button><button class="button primary" data-action="new-order">＋ Заказ</button>`)+
  `<section class="grid asym"><div class="stack"><article class="panel pad"><div class="detail-grid"><div class="detail"><small>Телефон</small><strong>${esc(client.phone)}</strong></div><div class="detail"><small>Email</small><strong>${esc(client.email)}</strong></div><div class="detail"><small>Организация</small><strong>${esc(client.organization||"—")}</strong></div><div class="detail"><small>Тип</small><strong>${esc(client.type)}</strong></div><div class="detail"><small>Город</small><strong>${esc(client.city)}</strong></div><div class="detail"><small>Адрес доставки</small><strong>${esc(client.address)}</strong></div></div></article>
  <article class="panel"><div class="panel-head"><div><h2>Заявки заказчика</h2><p>Новые обращения и расчёты</p></div><button class="link" data-route="leads">Все заявки →</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Заявка</th><th>Изделие</th><th>Деталей</th><th>Статус</th><th>Срок</th><th>Заказ</th></tr></thead><tbody>${leads.map(l=>`<tr class="clickable" data-open-lead="${esc(l.id)}"><td><strong>${esc(l.id)}</strong></td><td>${esc(l.subject)}</td><td>${orderPartCount(l)}</td><td>${badge(l.status)}</td><td>${l.due||"—"}</td><td>${l.orderId||"—"}</td></tr>`).join("")||'<tr><td colspan="6" class="empty">Заявок пока нет</td></tr>'}</tbody></table></div></article>
  <article class="panel"><div class="panel-head"><div><h2>Заказы заказчика</h2><p>Суммы, сроки и этапы производства</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Заказ</th><th>Изделие</th><th>Этап</th><th>Деталей</th><th>Срок</th><th>Сумма</th><th>Оплачено</th></tr></thead><tbody>${orders.map(o=>`<tr class="clickable" data-order="${o.id}"><td><strong>${o.id}</strong></td><td>${esc(o.product)}</td><td>${badge(o.stage)}</td><td>${orderPartCount(o)}</td><td>${o.due}</td><td>${money(o.amount)}</td><td>${money(o.paidAmount)}</td></tr>`).join("")||'<tr><td colspan="7" class="empty">Заказов пока нет</td></tr>'}</tbody></table></div></article></div>
  <aside class="stack"><article class="panel pad"><p class="eyebrow">Финансы заказчика</p><h2 class="client-balance">${money(client.balance)}</h2><div class="money-grid"><div class="money-card"><small>Заказов</small><strong>${orders.length}</strong></div><div class="money-card"><small>Сумма</small><strong>${money(client.revenue)}</strong></div><div class="money-card"><small>Оплачено</small><strong>${money(client.revenue-client.balance)}</strong></div></div></article><article class="panel pad"><h3 class="card-title">Комментарий</h3><p class="muted">${esc(client.comment||"Пока без комментария")}</p></article><article class="panel pad"><h3 class="card-title">История оплат</h3><div class="activity-list">${payments.map(p=>`<div class="activity-row"><span class="activity-icon">₽</span><div><b>${money(p.amount)}</b><p>Заказ ${p.orderId}</p></div><time>${p.date}</time></div>`).join("")||'<div class="empty">Оплат пока нет</div>'}</div></article></aside></section>`;
}

function renderOrders(){
  crumbs.textContent="Заказы";
  const filtered=activeOrderFilter==="Все"?data.orders:data.orders.filter(o=>o.status===activeOrderFilter);
  app.innerHTML=pageHead("Заказы","Заказы клиентов","Сроки, материалы, оплаты и текущий этап производства видны прямо в списке.",'<button class="button" data-action="download-report">↓ Экспорт CSV</button><button class="button primary" data-action="new-order">＋ Новый заказ</button>')+
  `<section class="stats">${stat("Всего заказов",data.orders.length,money(data.orders.reduce((s,o)=>s+o.amount,0)))}${stat("Новые",data.orders.filter(o=>o.status==="Новый").length,"нужно рассчитать")}${stat("В производстве",data.orders.filter(o=>o.status==="В работе").length,"активных заказов","",true)}${stat("Готовы",data.orders.filter(o=>o.status==="Готов").length,"на отгрузку")}${stat("С риском",data.orders.filter(o=>o.risk).length,"контроль сроков")}</section>
  <article class="panel"><div class="filters"><input class="field grow" id="orderSearch" placeholder="Номер, клиент или изделие"><div class="tabs" id="orderTabs">${["Все","Новый","Согласование","В работе","Готов"].map(x=>`<button class="tab ${activeOrderFilter===x?"active":""}" data-filter="${x}">${x}</button>`).join("")}</div><select class="select"><option>Все направления</option><option>Эмаль</option><option>ПВХ</option><option>Шпон</option></select></div>
  <div class="table-wrap"><table class="data-table"><thead><tr><th>Заказ</th><th>Клиент</th><th>Изделие</th><th>Направление</th><th>Этап</th><th>Срок</th><th>Сумма</th><th>Оплата</th><th></th></tr></thead><tbody id="ordersBody">${filtered.map(orderRow).join("")}</tbody></table></div></article>`;
}

function orderPartArea(order){return order.parts.reduce((sum,p)=>sum+p.height*p.width*p.qty,0)/1e6;}
function orderPartCount(order){return order.parts.reduce((sum,p)=>sum+p.qty,0);}
function routeMarkup(order){
  const route=FasadProduction.routeFor(order);
  const current=Math.max(0,route.indexOf(order.stage));
  return route.map((name,index)=>`<div class="route-step ${index<current?"done":index===current?"current":""}"><i>${index<current?"✓":index+1}</i><span>${name}</span><small>${index<current?"готово":index===current?"в работе":"ожидает"}</small></div>`).join("");
}

function renderOrder(id){
  const o=data.orders.find(x=>x.id===id);if(!o)return navigate("orders");
  const c=data.clients.find(x=>x.id===o.clientId);
  const partCount=orderPartCount(o),partArea=orderPartArea(o);
  const cutting=calculateOrderNesting(o);
  crumbs.textContent=`Заказы / ${o.id}`;
  app.innerHTML=`<section class="panel order-hero"><div><p class="eyebrow">${o.status}</p><div class="order-id"><button class="button ghost" data-route="orders">←</button><h1>${o.id}</h1>${badge(o.stage)}${o.risk?badge("Риск срока"):""}</div><p class="lead">${esc(o.product)} · ${o.direction} · ${partCount} деталей · ${FasadRules.area(partArea)} м²</p></div><div class="order-summary"><div><small>Сумма</small><strong>${money(o.amount)}</strong></div><div><small>Оплачено</small><strong>${o.paid}%</strong></div><div><small>Срок</small><strong class="${o.risk?"danger-text":""}">${o.due}</strong></div></div></section>
  <div class="head-actions order-actions"><button class="button" data-action="print-order">Печать бланка</button><button class="button" data-action="open-cutting" data-id="${o.id}">✂ Раскрой (${cutting.sheets.length} л.)</button><button class="button" data-action="add-payment" data-id="${o.id}">Добавить оплату</button><button class="button" data-action="edit-order" data-id="${o.id}">✎ Заказ и смета</button><button class="button primary" data-action="advance-order" data-id="${o.id}">${FasadProduction.routeFor(o).indexOf(o.stage)>=2?"Открыть этап →":"Передать дальше →"}</button></div>
  <section class="grid asym"><div class="stack">
    <article class="panel pad"><div class="detail-grid"><div class="detail"><small>Клиент</small><strong><button class="link" data-client="${o.clientId}">${esc(o.client)}</button></strong></div><div class="detail"><small>Телефон</small><strong>${c?.phone||"—"}</strong></div><div class="detail"><small>Менеджер</small><strong>${o.manager}</strong></div><div class="detail"><small>Материал</small><strong>${o.materialSpec.name} · ${o.material?"зарезервирован":"не зарезервирован"}</strong></div></div></article>
    <article class="panel"><div class="panel-head"><div><h2>Детали и смета заказа</h2><p>${o.parts.length} позиций · ${partCount} деталей · данные используются в раскрое</p></div><button class="button" data-action="open-cutting" data-id="${o.id}">Редактировать и раскроить</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Наименование</th><th>Высота</th><th>Ширина</th><th>Кол-во</th><th>Кромка</th><th>Цена</th><th>Сумма</th><th>Чертёж</th></tr></thead><tbody>${o.parts.map(p=>`<tr><td><strong>${esc(p.name)}</strong></td><td>${p.height} мм</td><td>${p.width} мм</td><td>${p.qty}</td><td>${p.edge}</td><td>${money(p.price)} / ${esc(p.unit||"??")}</td><td><strong>${money(FasadKP.lineAmount(p))}</strong></td><td><button class="link" data-action="open-cad" data-id="${esc(o.id)}" data-part-id="${esc(p.id)}">Открыть</button></td></tr>`).join("")}</tbody><tfoot><tr><td colspan="7"><strong>Итого с материалами и работой</strong></td><td><strong>${money(o.amount)}</strong></td></tr></tfoot></table></div></article>
    <article class="panel pad"><div class="panel-head route-head"><div><h2>Производственный маршрут</h2><p>Раскрой, ЧПУ, отделка и упаковка связаны с заказом</p></div><button class="link" data-route="production">Открыть производство →</button></div><div class="route">${routeMarkup(o)}</div></article>
  </div><aside class="stack">
    <article class="panel pad"><h3 class="card-title">Подготовка производства</h3><div class="readiness-list"><div><span>Карта раскроя</span><strong>${cutting.sheets.length} листа · ${cutting.efficiency}%</strong></div><div><span>Задание ЧПУ</span><strong>${partCount} деталей</strong></div><div><span>Склад</span><strong>${o.consumedSheets?`списано ${o.consumedSheets} л.`:o.reservedSheets?`резерв ${o.reservedSheets} л.`:"ожидает резерва"}</strong></div></div><button class="button amber wide" data-action="open-cutting" data-id="${o.id}">Открыть подготовку</button></article>
    <article class="panel pad"><h3 class="card-title">Деньги по заказу</h3><div class="money-grid"><div class="money-card"><small>Сумма</small><strong>${money(o.amount)}</strong></div><div class="money-card"><small>Получено</small><strong>${money(o.paidAmount)}</strong></div><div class="money-card"><small>Остаток</small><strong class="danger-text">${money(o.amount-o.paidAmount)}</strong></div></div><div class="progress-line order-pay"><i style="width:${o.paid}%"></i></div>${o.payments?.length?`<p class="muted payment-note">Последняя оплата ${money(o.payments[0].amount)} · ${o.payments[0].date}</p>`:""}</article>
    <article class="panel pad"><h3 class="card-title">Документы заказа</h3><div class="file-row"><i>▤</i><div><b>Бланк заказа</b><small>печать по текущим деталям</small></div><button class="link" data-action="print-order">Печать</button></div><div class="file-row"><i>◇</i><div><b>Задание ЧПУ</b><small>координаты деталей и листов</small></div><button class="link" data-action="open-cutting" data-id="${o.id}">Открыть</button></div></article>
  </aside></section>`;
}

function splitFreeRectangles(freeRects,used){
  const next=[];
  freeRects.forEach(rect=>{
    const separated=used.x>=rect.x+rect.w||used.x+used.w<=rect.x||used.y>=rect.y+rect.h||used.y+used.h<=rect.y;
    if(separated){next.push(rect);return;}
    if(used.x>rect.x)next.push({x:rect.x,y:rect.y,w:used.x-rect.x,h:rect.h});
    if(used.x+used.w<rect.x+rect.w)next.push({x:used.x+used.w,y:rect.y,w:rect.x+rect.w-used.x-used.w,h:rect.h});
    if(used.y>rect.y)next.push({x:rect.x,y:rect.y,w:rect.w,h:used.y-rect.y});
    if(used.y+used.h<rect.y+rect.h)next.push({x:rect.x,y:used.y+used.h,w:rect.w,h:rect.y+rect.h-used.y-used.h});
  });
  return next.filter((r,i,list)=>r.w>1&&r.h>1&&!list.some((other,j)=>j!==i&&r.x>=other.x&&r.y>=other.y&&r.x+r.w<=other.x+other.w&&r.y+r.h<=other.y+other.h));
}
function findPlacement(sheet,item,spec){
  const {gapX,gapY}=FasadCuttingLayout.rules(spec);
  // The sheet's long X axis follows the board grain, so a part's height runs along X.
  const orientations=[{w:item.height,h:item.width,rotated:false}];
  if(spec.allowRotation!==false&&!item.grain&&!item.no_rotation&&item.width!==item.height)orientations.push({w:item.width,h:item.height,rotated:true});
  let best=null;
  sheet.free.forEach((rect,rectIndex)=>orientations.forEach(size=>{
    const packedW=size.w+gapX,packedH=size.h+gapY;
    if(size.w<=rect.w&&size.h<=rect.h){
      const r=FasadCuttingLayout.rules(spec),edgeX=spec.sheetWidth-r.right,edgeY=spec.sheetHeight-r.bottom;
      if(packedW>rect.w&&rect.x+rect.w<edgeX-0.001||packedH>rect.h&&rect.y+rect.h<edgeY-0.001)return;
      const score=(rect.w*rect.h-packedW*packedH)*10+Math.min(rect.w-packedW,rect.h-packedH);
      if(!best||score<best.score)best={...size,packedW,packedH,x:rect.x,y:rect.y,rectIndex,score};
    }
  }));
  return best;
}
function materialSnapshots(settings){
  return Object.fromEntries(Object.keys(FasadFactorySettings.normalize(settings).materials)
    .map(name=>{const snapshot=FasadFactorySettings.snapshot(settings,name);return [snapshot.thickness,snapshot];}));
}
function calculateNesting(parts,spec,specs={}){
  const valid=parts.filter(p=>p.height>0&&p.width>0&&p.qty>0);
  const items=[];
  valid.forEach((part,partIndex)=>{for(let number=1;number<=Math.min(500,part.qty);number++)items.push({...part,partIndex,number,physicalNumber:items.length+1});});
  items.sort((a,b)=>Math.max(b.width,b.height)-Math.max(a.width,a.height)||b.width*b.height-a.width*a.height);
  const sheets=[],oversized=[];
  items.forEach(item=>{
    const thickness=Number(item.thickness||spec.thickness||16);
    const itemSpec=spec.mode==='film'?{...spec,thickness}:Number(spec.thickness||16)===thickness?spec:(specs[thickness]||{...spec,thickness,name:`МДФ ${thickness} мм`,stockName:`МДФ ${thickness} мм`});
    const rule=FasadCuttingLayout.rules(itemSpec),usableW=itemSpec.sheetWidth-rule.left-rule.right,usableH=itemSpec.sheetHeight-rule.top-rule.bottom;
    const color=String(item.color||"").trim();
    const materialKey=`${spec.mode==='film'?'film|':''}${thickness}|${color.toLocaleLowerCase('ru-RU')}|`+JSON.stringify([String(item.material||itemSpec.name||'').trim().toLocaleLowerCase('ru-RU'),spec.mode==='film'?String(item.article||'').trim().toLocaleLowerCase('ru-RU'):'']);
    const materialName=itemSpec.stockName||itemSpec.name;
    let target=null,placement=null;
    for(const sheet of sheets){if(sheet.materialKey!==materialKey)continue;const candidate=findPlacement(sheet,item,itemSpec);if(candidate){target=sheet;placement=candidate;break;}}
    if(!placement){
      const sheet={placements:[],free:[{x:rule.left,y:rule.top,w:usableW,h:usableH}],materialKey,materialName,thickness,color,spec:itemSpec};
      placement=findPlacement(sheet,item,itemSpec);
      if(!placement){oversized.push(item);return;}
      sheets.push(sheet);target=sheet;
    }
    const used={x:placement.x,y:placement.y,w:placement.packedW,h:placement.packedH};
    target.free=splitFreeRectangles(target.free,used);
    target.placements.push({...item,x:placement.x,y:placement.y,placedWidth:placement.w,placedHeight:placement.h,rotated:placement.rotated});
  });
  const partArea=items.filter(x=>!oversized.includes(x)).reduce((sum,p)=>sum+p.width*p.height,0);
  const sheetArea=sheets.reduce((sum,sheet)=>sum+sheet.spec.sheetWidth*sheet.spec.sheetHeight,0);
  const efficiency=sheetArea?Math.round(partArea/sheetArea*100):0;
  return {sheets,oversized,parts:items.length,area:partArea/1e6,efficiency,waste:Math.max(0,(sheetArea-partArea)/1e6),cost:sheets.reduce((sum,sheet)=>sum+Number(sheet.spec.price||0),0)};
}
function calculateOrderNesting(order){
  const automatic=calculateNesting(order.parts,order.materialSpec,order.materialSpecs);
  return FasadCuttingLayout.apply(order,automatic)||automatic;
}
function cuttingMapAddress(record){
  if(!record)return "";
  const sourceLead=data.leads.find(lead=>lead.id===record.id||lead.orderId===record.id);
  const client=data.clients.find(item=>item.id===record.clientId);
  return String(sourceLead?.address||record.address||client?.address||"").trim();
}
let cuttingOverlayMode="milling",selectedLayoutKey=null;
function cuttingSheetSvg(sheet,spec,index,owner=null){
  spec=sheet.spec||spec;
  const r=FasadCuttingLayout.rules(spec),zone=`<rect class="sheet-work-zone" x="${r.left}" y="${r.top}" width="${Math.max(0,spec.sheetWidth-r.left-r.right)}" height="${Math.max(0,spec.sheetHeight-r.top-r.bottom)}"/>`;
  const colors=["c1","c2","c3","c4","c5","c6","c7","c8"];
  const orderIds=[...new Set(sheet.placements.map(part=>part.orderId).filter(Boolean))];
  const owners=owner?[owner]:orderIds.map(id=>data.orders.find(order=>order.id===id)).filter(Boolean);
  const addresses=[...new Set(owners.map(cuttingMapAddress).filter(Boolean))];
  const articles=[...new Set(sheet.placements.map(part=>String(part.article||"").trim()).filter(Boolean))];
  const customer=owners.map(item=>item.client).filter(Boolean).join(", ")||"Не указан";
  const address=addresses.join("; ")||"Не указан";
  const article=articles.join(", ")||"Не указан";
  const pieces=sheet.placements.map(p=>{
    const label=`<text x="${p.x+p.placedWidth/2}" y="${p.y+p.placedHeight/2}" dominant-baseline="middle" text-anchor="middle" style="font-size:${Math.min(38,p.placedHeight/3,p.placedWidth/(p.placedWidth>250?10:4))}px">${p.placedWidth>250?`${p.height}×${p.width} · `:""}#${p.physicalNumber||p.number}</text>`;
    let overlay="";
    if(p.cadModel&&cuttingOverlayMode!=="none"){
      try{overlay=FasadCAD.overlaySvg(FasadCAD.modelForPart(p),p,cuttingOverlayMode);}catch{/* Invalid saved geometry must not break the cutting map. */}
    }
    return `<g class="layout-piece ${selectedLayoutKey===FasadCuttingLayout.key(p)?'selected':''}" data-layout-key="${esc(FasadCuttingLayout.key(p))}" data-sheet-index="${index}" data-x="${p.x}" data-y="${p.y}" data-rotated="${p.rotated}"><rect class="piece ${colors[p.partIndex%colors.length]}" x="${p.x}" y="${p.y}" width="${p.placedWidth}" height="${p.placedHeight}"><title>${p.orderId?`${esc(p.orderId)} · `:""}${esc(p.name)} · ${p.width}×${p.height} мм · №${p.number}${p.rotated?" · поворот 90°":""}</title></rect>${overlay}${label}</g>`;
  }).join("");
  return `<article class="cut-sheet-card"><header><div><strong>Лист ${index+1} · ${esc(sheet.materialName||spec.name)}</strong><span>${sheet.placements.length} деталей · ${esc(sheet.color||"без цвета")}</span></div><b>${spec.sheetWidth} × ${spec.sheetHeight}</b></header><dl class="cut-sheet-meta"><div><dt>Заказ / заявка</dt><dd>${esc(owner?.id||orderIds.join(", ")||"—")}</dd></div><div><dt>Заказчик</dt><dd>${esc(customer)}</dd></div><div><dt>Адрес</dt><dd>${esc(address)}</dd></div><div><dt>Артикул</dt><dd>${esc(article)}</dd></div><div><dt>Толщина</dt><dd>${esc(sheet.thickness||spec.thickness||"—")} мм</dd></div></dl><div class="sheet-area"><svg class="sheet-svg live" viewBox="0 0 ${spec.sheetWidth} ${spec.sheetHeight}" aria-label="Карта раскроя листа ${index+1}"><rect class="board" x="1" y="1" width="${spec.sheetWidth-2}" height="${spec.sheetHeight-2}" rx="10"/>${zone}${pieces}</svg></div></article>`;
}
function cuttingResultsMarkup(order,result){
  const spec=order.materialSpec;
  if(!result.sheets.length)return result.oversized.length?`<div class="cut-warning">Детали не помещаются на лист: ${result.oversized.map(p=>`${esc(p.name)} ${p.width}×${p.height}`).join(", ")}. Проверьте размер листа, поля и поворот.</div>`:'<div class="empty cutting-empty">Добавьте хотя бы одну корректную деталь — карта появится здесь автоматически.</div>';
  return `${result.oversized.length?`<div class="cut-warning"><b>Не помещаются на лист:</b> ${result.oversized.map(p=>`${esc(p.name)} ${p.width}×${p.height}`).join(", ")}. Измените размер листа или разрешите поворот.</div>`:""}<div class="cut-sheet-grid">${result.sheets.map((sheet,index)=>cuttingSheetSvg(sheet,spec,index,order)).join("")}</div>`;
}
function cuttingStatsMarkup(order,result){
  const placed=result.sheets.reduce((sum,sheet)=>sum+sheet.placements.length,0);
  return `${stat("Листов",result.sheets.length,order.materialSpec.name)}${stat("Деталей",result.parts,`${placed} размещено · ${FasadRules.area(result.area)} м²`)}${stat("Полезный выход",`${result.efficiency}%`,`отход ${FasadRules.area(result.waste)} м²`,"",true)}${stat("Материал",money(result.cost),"по складской цене")}`;
}
function updateGroupedParts(order){
  const list=document.querySelector("#partsList");
  if(!list)return;
  let panel=document.querySelector("#groupedParts");
  if(!panel){list.insertAdjacentHTML("afterend",'<details id="groupedParts" class="grouped-parts"><summary>Сводка одинаковых размеров</summary><div class="table-wrap"><table class="data-table"><thead><tr><th>Размер, мм</th><th>Кол-во</th><th>Артикул</th><th>Толщина</th><th>Цвет</th><th>Фрезеровка</th><th>Площадь, м²</th></tr></thead><tbody></tbody></table></div></details>');panel=document.querySelector("#groupedParts");}
  const groups=FasadGroupedParts.group(order.parts);
  panel.querySelector("summary").textContent=`Сводка одинаковых размеров · ${groups.length} групп`;
  panel.querySelector("tbody").innerHTML=groups.map(item=>`<tr><td>${item.height} × ${item.width}</td><td>${item.quantity}</td><td>${esc(item.article||"—")}</td><td>${item.thickness||"—"}</td><td>${esc(item.color||"—")}</td><td>${esc(item.milling||"—")}</td><td>${FasadRules.area(item.areaSqm)}</td></tr>`).join("");
}
function updateCuttingResults(order){
  const result=calculateOrderNesting(order);
  const maps=document.querySelector("#cuttingMaps"),stats=document.querySelector("#cuttingStats"),count=document.querySelector("#partsCount"),release=document.querySelector("#releaseCutting"),cnc=document.querySelector("#cncMeta"),yieldBadge=document.querySelector("#cutYieldBadge"),releaseNote=document.querySelector("#releaseNote");
  if(maps)maps.innerHTML=cuttingResultsMarkup(order,result);
  if(stats)stats.innerHTML=cuttingStatsMarkup(order,result);
  if(count)count.textContent=`${order.parts.length} позиций · ${orderPartCount(order)} деталей`;
  if(yieldBadge)yieldBadge.innerHTML=badge(`Выход ${result.efficiency}%`);
  const isLead=data.leads.some(l=>l.id===order.id);
  if(releaseNote)releaseNote.textContent=isLead?"Сначала создайте заказ из этой заявки. Все детали и параметры раскроя перейдут в заказ.":`Система зарезервирует ${result.sheets.length} листа на складе и поставит заказ на этап «Распил».`;
  if(release){release.disabled=!result.sheets.length||result.oversized.length>0||Boolean(order.consumedSheets);release.textContent=isLead?"Создать заказ по заявке":FasadProduction.isCuttingCurrent(order)?"Резерв актуален · обновить":"Передать в производство";}
  if(cnc)cnc.innerHTML=`<div><span>Черновик</span><strong>CNC-${order.id.replace("F-","")}-01</strong></div><div><span>Деталей</span><strong>${result.parts}</strong></div><div><span>Листов</span><strong>${result.sheets.length}</strong></div><div><span>Инструмент</span><strong>Фреза Ø8 · паз Ø4</strong></div>`;
  updateGroupedParts(order);
  return result;
}
function partRow(part){
  return `<div class="part-row" data-part-id="${part.id}"><input aria-label="Название" data-part-field="name" value="${esc(part.name)}"><input aria-label="Высота" data-part-field="height" type="number" min="1" max="5000" value="${part.height}"><input aria-label="Ширина" data-part-field="width" type="number" min="1" max="5000" value="${part.width}"><input aria-label="Количество" data-part-field="qty" type="number" min="1" max="500" value="${part.qty}"><select aria-label="Кромка" data-part-field="edge"><option ${part.edge==="4 стороны"?"selected":""}>4 стороны</option><option ${part.edge==="2 стороны"?"selected":""}>2 стороны</option><option ${part.edge==="1 сторона"?"selected":""}>1 сторона</option><option ${part.edge==="Нет"?"selected":""}>Нет</option></select><label class="grain-check" title="Сохранять направление текстуры"><input data-part-field="grain" type="checkbox" ${part.grain?"checked":""}><span>↕</span></label><button aria-label="Удалить деталь">×</button></div>`;
}
function renderCutting(orderId){
  const record=data.orders.find(o=>o.id===orderId)||data.leads.find(l=>l.id===orderId)||data.orders.find(o=>o.id==="F-1048")||data.orders[0];
  const order=window.FasadProduct?.cuttingRecord(record)||record;
  if(!order)return;
  if(app.dataset.cuttingOrder!==order.id)selectedLayoutKey=null;
  const isLead=data.leads.some(l=>l.id===order.id);
  const result=calculateOrderNesting(order);
  crumbs.textContent=`Раскрой / ${order.id}`;
  app.innerHTML=pageHead("Подготовка производства",`Раскрой ${order.id}`,isLead?"Карта строится прямо из деталей заявки. После согласования те же детали перейдут в заказ.":"Детали заказа, листы, карта раскроя, складской резерв и задание ЧПУ связаны между собой.",'<button class="button" data-action="print-cutting">Печать карты / PDF</button><button class="button" data-action="download-cnc">↓ Задание ЧПУ</button><button class="button primary" id="calculateCutting">Пересчитать</button>')+
  `<div class="cut-flow"><span class="done">1 · ${isLead?"Заявка":"Заказ"}</span><i>→</i><span class="active">2 · Раскрой</span><i>→</i><span>3 · Резерв склада</span><i>→</i><span>4 · ЧПУ</span><i>→</i><span>5 · Производство</span></div>
  <section class="cutting-layout"><div class="stack">
    <article class="panel pad"><div class="panel-head compact-head"><div><h3>Источник и лист</h3><p>Детали берутся из выбранной заявки или заказа</p></div>${badge(isLead?"Заявка":FasadProduction.isCuttingCurrent(order)?"Передан в цех":"Черновик")}</div><div class="form-grid"><div class="form-group full"><label>Заявка / заказ</label><select id="cuttingOrderSelect"><optgroup label="Заказы">${data.orders.map(o=>`<option value="${o.id}" ${o.id===order.id?"selected":""}>${o.id} · ${esc(o.client)} · ${esc(o.product)}</option>`).join("")}</optgroup><optgroup label="Заявки">${data.leads.map(l=>`<option value="${esc(l.id)}" ${l.id===order.id?"selected":""}>${esc(l.id)} · ${esc(l.client)} · ${esc(l.subject)}</option>`).join("")}</optgroup></select></div><div class="form-group full"><label>Материал</label><select id="materialPreset">${Object.keys(MATERIAL_PRESETS).map(name=>`<option ${name===order.materialSpec.name?"selected":""}>${name}</option>`).join("")}</select></div><div class="form-group"><label>Пропил, мм</label><input id="cutKerf" type="number" min="0" max="20" value="${order.materialSpec.kerf}"></div><div class="form-group"><label>Отступ от края, мм</label><input id="cutMargin" type="number" min="0" max="100" value="${order.materialSpec.margin}"></div><div class="form-group"><label>Ширина листа, мм</label><input id="cutSheetWidth" type="number" min="100" max="5000" value="${order.materialSpec.sheetWidth}"></div><div class="form-group"><label>Высота листа, мм</label><input id="cutSheetHeight" type="number" min="100" max="5000" value="${order.materialSpec.sheetHeight}"></div><div class="form-group full"><label class="cut-rotation-toggle"><input id="cutAllowRotation" type="checkbox" ${order.materialSpec.allowRotation!==false?"checked":""}> Разрешить поворот деталей без текстуры</label></div></div></article>
    <article class="panel pad"><div class="panel-head parts-head"><div><h3>Детали</h3><p id="partsCount">${order.parts.length} позиций · ${orderPartCount(order)} деталей</p></div><button class="link" id="addPart">＋ Добавить</button></div><div class="part-columns"><span>Название</span><span>В</span><span>Ш</span><span>Кол.</span><span>Кромка</span><span>Текст.</span><span></span></div><div class="parts-list" id="partsList">${order.parts.map(partRow).join("")}</div></article>
  </div><div class="stack"><article class="panel"><div class="panel-head"><div><h2>Карты раскроя</h2><p>Каждый прямоугольник — отдельная заготовка; рисунок фрезеровки показан внутри неё.</p></div><div id="cutYieldBadge">${badge(`Выход ${result.efficiency}%`)}</div></div><div class="panel-body"><label class="cut-overlay-control">Показать слой <select id="cutOverlayMode"><option value="none" ${cuttingOverlayMode==='none'?'selected':''}>Только раскрой</option><option value="contours" ${cuttingOverlayMode==='contours'?'selected':''}>Контур фасада</option><option value="milling" ${cuttingOverlayMode==='milling'?'selected':''}>Фрезеровка</option><option value="operations" ${cuttingOverlayMode==='operations'?'selected':''}>Все операции</option></select></label><div class="cut-manual-tools"><span id="selectedPiece">Выберите деталь на карте и перетащите её</span><button class="button" data-action="rotate-piece">Повернуть 90°</button><button class="button" data-action="move-piece-sheet">На следующий лист</button><button class="button" data-action="reset-manual-layout">Автораскрой</button></div><div id="cuttingMaps">${cuttingResultsMarkup(order,result)}</div><p class="form-note">Ручное перемещение проверяет поля листа и пропил. Траектория инструмента пока не рассчитывается; скруглённый фасад раскраивается как прямоугольная заготовка.</p></div></article>
    <section class="stats cutting-stats" id="cuttingStats">${cuttingStatsMarkup(order,result)}</section>
    <section class="grid cols-2"><article class="panel pad"><div class="panel-head compact-head"><div><h3>Задание оператору ЧПУ</h3><p>Формируется из актуальной карты</p></div>${badge("Черновик")}</div><div class="form-group full"><label for="cncMachineSelect">Станок</label><select id="cncMachineSelect"><option value="">Выберите станок</option>${data.machines.map(machine=>`<option value="${esc(machine.id)}" ${order.cncMachineId===machine.id?"selected":""}>${esc(machine.name)} · ${esc(machine.controller)}</option>`).join("")}</select></div><button class="link" data-action="add-cnc-machine">＋ Добавить станок</button><p class="form-note">JSON — только черновик задания. Управляющая программа для станка требует настройки постпроцессора и проверки технологом.</p><div class="cnc-meta" id="cncMeta"><div><span>Черновик</span><strong>CNC-${order.id.replace("F-","")}-01</strong></div><div><span>Деталей</span><strong>${result.parts}</strong></div><div><span>Листов</span><strong>${result.sheets.length}</strong></div><div><span>Инструмент</span><strong>Фреза Ø8 · паз Ø4</strong></div></div><button class="button wide" data-action="download-cnc">Скачать черновик JSON</button></article>
    <article class="panel pad release-card"><div><p class="eyebrow">Следующий шаг</p><h3>${isLead?"Создать заказ":"Резерв и запуск"}</h3><p id="releaseNote">${isLead?"Все детали и параметры раскроя перейдут в заказ.":`Система зарезервирует ${result.sheets.length} листа на складе и поставит заказ на этап «Распил».`}</p></div><button class="button amber wide" id="releaseCutting" ${!result.sheets.length||result.oversized.length||order.consumedSheets?"disabled":""}>${isLead?"Создать заказ по заявке":FasadProduction.isCuttingCurrent(order)?"Резерв актуален · обновить":"Передать в производство"}</button></article></section>
  </div></section>`;
  app.dataset.cuttingOrder=order.id;
  updateGroupedParts(order);
}

function renderBatchCutting(){
  crumbs.textContent="Раскрой партией";
  const selected=data.orders.filter(order=>batchSelectedIds.has(order.id));
  const groups=new Map();
  selected.forEach(order=>order.parts.forEach(part=>{
    const thickness=Number(part.thickness||order.materialSpec.thickness||16);
    const spec=Number(order.materialSpec.thickness||16)===thickness?order.materialSpec:
      (order.materialSpecs?.[thickness]||{...order.materialSpec,thickness,name:`МДФ ${thickness} мм`,stockName:`МДФ ${thickness} мм`});
    const key=[spec.name,spec.sheetWidth,spec.sheetHeight,spec.kerf,spec.margin,spec.allowRotation!==false].join("|");
    if(!groups.has(key))groups.set(key,{spec,parts:[],orders:[]});
    const group=groups.get(key);
    if(!group.orders.includes(order.id))group.orders.push(order.id);
    group.parts.push({...part,orderId:order.id});
  }));
  const results=[...groups.values()].map(group=>({...group,result:calculateNesting(group.parts,group.spec)}));
  const sheets=results.reduce((sum,group)=>sum+group.result.sheets.length,0);
  const pieces=results.reduce((sum,group)=>sum+group.result.parts,0);
  const area=results.reduce((sum,group)=>sum+group.result.area,0);
  app.innerHTML=pageHead("Производство","Раскрой партии","Выберите заказы: их детали разместятся на общих листах. Заказы с разными материалами и форматами листа раскладываются отдельно.",'<button class="button" data-action="print-batch">Печать карт / PDF</button>')+
    `<section class="stats">${stat("Заказов",selected.length,"в партии")}${stat("Листов",sheets,"по всем материалам")}${stat("Деталей",pieces,"размещено и ожидает размещения")}${stat("Площадь",`${FasadRules.area(area)} м²`,"полезная площадь")}</section>
    <article class="panel"><div class="panel-head"><div><h2>Заказы для партии</h2><p>Отметьте несколько заказов одного материала, чтобы увидеть совместную карту.</p></div><label class="batch-select-all"><input id="batchSelectAll" type="checkbox" ${data.orders.length&&selected.length===data.orders.length?"checked":""}> Выбрать все</label></div><div class="table-wrap"><table class="data-table"><thead><tr><th></th><th>Заказ</th><th>Клиент</th><th>Материал</th><th>Деталей</th><th>Площадь</th></tr></thead><tbody>${data.orders.map(order=>`<tr><td><input class="batch-order-check" type="checkbox" value="${esc(order.id)}" ${batchSelectedIds.has(order.id)?"checked":""} aria-label="Добавить заказ ${esc(order.id)} в партию"></td><td><strong>${esc(order.id)}</strong></td><td>${esc(order.client)}</td><td>${esc(order.materialSpec.name)}</td><td>${orderPartCount(order)}</td><td>${FasadRules.area(orderPartArea(order))} м²</td></tr>`).join("")||'<tr><td colspan="6" class="empty">Заказов пока нет. Сначала создайте заказ из заявки.</td></tr>'}</tbody></table></div></article>
    ${results.map(group=>`<article class="panel batch-map-group"><div class="panel-head"><div><h2>${esc(group.spec.name)} · ${group.spec.sheetWidth}×${group.spec.sheetHeight} мм</h2><p>Заказы: ${group.orders.map(esc).join(", ")} · пропил ${group.spec.kerf} мм · поля ${group.spec.margin} мм</p></div>${badge(`${group.result.sheets.length} листов`)}</div><div class="panel-body">${group.result.oversized.length?`<div class="cut-warning">Не помещаются: ${group.result.oversized.map(part=>`${esc(part.orderId)} ${esc(part.name)} ${part.height}×${part.width}`).join(", ")}</div>`:""}<div class="cut-sheet-grid">${group.result.sheets.map((sheet,index)=>cuttingSheetSvg(sheet,group.spec,index)).join("")||'<div class="empty">В выбранных заказах нет деталей для раскроя.</div>'}</div><p class="form-note">Полезный выход: ${group.result.efficiency}% · площадь деталей ${FasadRules.area(group.result.area)} м² · свободная площадь ${FasadRules.area(group.result.waste)} м².</p></div></article>`).join("")||'<article class="panel pad"><div class="empty">Отметьте заказы выше, чтобы построить общую карту раскроя.</div></article>'}`;
}

function workerName(id){return data.workers.find(w=>w.id===id)?.name||"Не назначен";}
function stageStateName(state){return ({pending:"Ожидает",in_progress:"В работе",blocked:"Заблокирован",done:"Завершён"})[state]||state;}
function renderProduction(){
  crumbs.textContent="Производство";
  const queue=FasadProduction.workQueue(data),reports=FasadProduction.reports(data);
  const active=queue.filter(item=>!["Расчёт","Согласование"].includes(item.stage));
  app.innerHTML=pageHead("Производство","Очередь цеха","Каждый заказ проходит свои участки: исполнитель принимает этап, сдаёт детали и фиксирует брак.",'<button class="button" data-route="workers">Работники</button><button class="button primary" data-route="orders">Все заказы</button>')+
  `<section class="stats">${stat("В очереди",queue.length,"заказов")}${stat("На участках",active.length,"активных этапов","",true)}${stat("Заблокированы",queue.filter(q=>q.status==="blocked").length,"требуют решения")}${stat("Сдано деталей",reports.reduce((sum,r)=>sum+r.done,0),"по отчётам работников")}${stat("Брак",reports.reduce((sum,r)=>sum+r.defects,0),"отмечен по позициям")}</section>
  <article class="panel"><div class="panel-head"><div><h2>Очередь производства</h2><p>Откройте этап, назначьте исполнителя и сдайте детали по позициям</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Заказ</th><th>Заказчик</th><th>Этап / участок</th><th>Состояние</th><th>Исполнитель</th><th>Прогресс</th><th>Срок</th><th></th></tr></thead><tbody>${queue.map(item=>`<tr class="clickable" data-production-order="${item.orderId}"><td><strong>${item.orderId}</strong></td><td>${esc(item.client)}</td><td>${item.stage}</td><td>${badge(stageStateName(item.status))}</td><td>${esc(workerName(item.workerId))}</td><td>${item.progress.done}/${item.progress.required} дет. <div class="progress-line"><i style="width:${item.progress.percent}%"></i></div></td><td>${item.due}</td><td><button class="link">Открыть →</button></td></tr>`).join("")||'<tr><td colspan="8" class="empty">Очередь пуста</td></tr>'}</tbody></table></div></article>
  <section class="grid cols-2 production-secondary"><article class="panel"><div class="panel-head"><div><h2>Участки</h2><p>Текущие задания по этапам</p></div></div><div class="panel-body status-bars">${[...new Set(queue.map(item=>item.stage))].map(stage=>{const count=queue.filter(item=>item.stage===stage).length;return `<div class="status-bar"><span>${stage}</span><div class="progress-line"><i style="width:${Math.round(count/Math.max(1,queue.length)*100)}%"></i></div><b>${count}</b></div>`}).join("")}</div></article><article class="panel"><div class="panel-head"><div><h2>Отчёты работников</h2><p>Последние фактические операции</p></div></div><div class="panel-body activity-list">${reports.slice(-8).reverse().map(r=>`<div class="activity-row"><span class="activity-icon">${r.defects?"!":"✓"}</span><div><b>${r.orderId} · ${r.stage}</b><p>${esc(workerName(r.workerId))} · ${esc(r.partName)} · годных ${r.done}${r.defects?` · брак ${r.defects}`:""}</p></div><time>${new Date(r.at).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})}</time></div>`).join("")||'<div class="empty">Отчётов пока нет</div>'}</div></article></section>`;
}
function renderProductionStage(id){
  const order=data.orders.find(o=>o.id===id);if(!order)return navigate("production");
  const production=FasadProduction.bootstrap(order).production,stage=production.stages.find(s=>s.name===order.stage),progress=FasadProduction.stageProgress(order);
  const route=FasadProduction.routeFor(order),index=route.indexOf(order.stage);
  crumbs.textContent=`Производство / ${order.id} / ${order.stage}`;
  app.innerHTML=pageHead(`Заказ ${order.id}`,`Этап: ${order.stage}`,`${esc(order.client)} · ${esc(order.product)} · ${orderPartCount(order)} деталей`,`<button class="button" data-order="${order.id}">Карточка заказа</button><button class="button" data-route="production">Очередь</button>`)+
  `<div class="stage-timeline">${route.map((name,i)=>`<div class="stage-timeline-item ${i<index?"done":i===index?"current":""}"><span>${i<index?"✓":i+1}</span><b>${name}</b><small>${i<index?"завершён":i===index?stageStateName(stage.status):"ожидает"}</small></div>`).join("")}</div>
  <section class="stats">${stat("Нужно",progress.required,"деталей на этапе")}${stat("Сдано",progress.done,"годных деталей","",true)}${stat("Осталось",progress.remaining,"к выполнению")}${stat("Брак",progress.defects,"отдельно от годных")}${stat("Готовность",`${progress.percent}%`,stageStateName(stage.status))}</section>
  <section class="grid asym"><div class="stack"><article class="panel"><div class="panel-head"><div><h2>Отчёт по деталям</h2><p>Количество годных деталей и брак фиксируются по каждой позиции</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Деталь</th><th>Размер</th><th>Нужно</th><th>Сдано</th><th>Брак</th><th>Осталось</th><th></th></tr></thead><tbody>${progress.byPart.map(part=>{const source=order.parts.find(p=>p.id===part.partId);return `<tr><td><strong>${esc(part.name)}</strong><small class="lead-detail-count">${esc(source?.article||source?.color||"")}</small></td><td>${source?.height}×${source?.width}</td><td>${part.required}</td><td>${part.done}</td><td>${part.defects}</td><td>${part.remaining}</td><td>${["Расчёт","Согласование","Готов к отгрузке"].includes(order.stage)?"—":`<button class="link" data-action="stage-report" data-id="${order.id}" data-part-id="${part.partId}" ${part.remaining<=0||stage.status==="blocked"?"disabled":""}>＋ Отчёт</button>`}</td></tr>`}).join("")}</tbody></table></div></article>
  <article class="panel"><div class="panel-head"><div><h2>Журнал этапа</h2><p>Кто, когда и сколько деталей сдал</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Время</th><th>Исполнитель</th><th>Деталь</th><th>Годные</th><th>Брак</th><th>Комментарий</th></tr></thead><tbody>${[...stage.reports].reverse().map(r=>`<tr><td>${new Date(r.at).toLocaleString("ru-RU")}</td><td>${esc(workerName(r.workerId))}</td><td>${esc(r.partName)}</td><td>${r.done}</td><td>${r.defects}</td><td>${esc(r.comment||"—")}</td></tr>`).join("")||'<tr><td colspan="6" class="empty">Отчётов пока нет</td></tr>'}</tbody></table></div></article></div>
  <aside class="stack"><article class="panel pad"><h3 class="card-title">Управление этапом</h3><div class="form-group"><label>Исполнитель</label><select id="stageWorkerSelect"><option value="">Выберите работника</option>${data.workers.map(w=>`<option value="${w.id}" ${w.id===stage.workerId?"selected":""}>${esc(w.name)} · ${esc(w.role)}</option>`).join("")}</select></div><div class="stage-actions"><button class="button wide" data-action="stage-assign" data-id="${order.id}">Назначить исполнителя</button>${stage.status==="blocked"?`<button class="button amber wide" data-action="stage-resume" data-id="${order.id}">Возобновить этап</button>`:`<button class="button wide" data-action="stage-block" data-id="${order.id}">Остановить этап</button>`}<button class="button primary wide" data-action="stage-complete" data-id="${order.id}" ${stage.status==="blocked"?"disabled":""}>${["Расчёт","Согласование"].includes(order.stage)?"Передать дальше":"Завершить этап"} →</button></div>${stage.blockedReason?`<p class="cut-warning">Причина остановки: ${esc(stage.blockedReason)}</p>`:""}<p class="form-note">Следующий этап откроется после сдачи всех годных деталей. Брак остаётся в журнале и требует довыпуска.</p></article><article class="panel pad"><h3 class="card-title">Заказ и материал</h3><div class="readiness-list"><div><span>Заказчик</span><strong>${esc(order.client)}</strong></div><div><span>Материал</span><strong>${order.materialSpec.name}</strong></div><div><span>Раскрой</span><strong>${FasadProduction.isCuttingCurrent(order)?"актуален":order.consumedSheets?"списан":"ожидает"}</strong></div><div><span>Листы</span><strong>${order.reservedSheets||order.consumedSheets||0}</strong></div><div><span>Срок</span><strong>${order.due}</strong></div></div><button class="button wide" data-action="open-cutting" data-id="${order.id}">Открыть карту</button></article></aside></section>`;
}

function renderWorkers(){
  crumbs.textContent="Работники";
  const reports=FasadProduction.reports(data);
  const activeStages=data.orders.flatMap(order=>order.production?.stages||[]).filter(stage=>stage.status==="in_progress"&&stage.workerId);
  const today=new Date().toDateString(),todayReports=reports.filter(report=>new Date(report.at).toDateString()===today);
  const metrics=workerId=>{const own=reports.filter(report=>report.workerId===workerId);return {active:activeStages.filter(stage=>stage.workerId===workerId).length,reports:own.length,done:own.reduce((sum,row)=>sum+Number(row.done||0),0),defects:own.reduce((sum,row)=>sum+Number(row.defects||0),0)};};
  app.innerHTML=pageHead("Производство","Работники","Текущая нагрузка, активные задания, выработка и качество по каждому сотруднику.",'<button class="button" data-action="new-worker">Добавить работника</button><button class="button primary" data-route="production">Открыть задания</button>')+
  `<section class="stats">${stat("Сотрудники",data.workers.length,"в локальном справочнике")}${stat("Активных заданий",activeStages.length,"назначенные этапы")}${stat("Сделано сегодня",todayReports.reduce((sum,row)=>sum+Number(row.done||0),0),"годных деталей","",true)}${stat("Брак сегодня",todayReports.reduce((sum,row)=>sum+Number(row.defects||0),0),"деталей")}${stat("Отчёты",reports.length,"по этапам")}</section>
  <section class="worker-cards">${data.workers.map(w=>{const value=metrics(w.id);return `<article class="worker-card"><div class="worker-top">${avatar(esc(w.initials),w.color)}<div><strong>${esc(w.name)}</strong><small>${esc(w.role)}</small></div>${badge(value.active?"Есть задания":"Без задания")}</div><div class="detail-grid" style="grid-template-columns:repeat(3,1fr);margin-top:12px"><div class="detail"><small>Этапы</small><strong>${value.active}</strong></div><div class="detail"><small>Отчёты</small><strong>${value.reports}</strong></div><div class="detail"><small>Брак</small><strong>${value.defects}</strong></div></div><button class="button wide" style="margin-top:11px" data-action="worker-details" data-id="${w.id}">Открыть карточку</button></article>`;}).join("")}</section>`;
}

function renderMaterials(){
  crumbs.textContent="Материалы";
  app.innerHTML=pageHead("Справочники","Материалы","Материалы раскроя и отделки с текущим складским остатком.",'<button class="button primary" data-route="stock">Открыть склад</button>')+
  `<article class="panel"><div class="panel-head"><div><h2>Каталог материалов</h2><p>Плиты доступны для выбора в раскрое заказа</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Материал</th><th>Тип</th><th>Формат</th><th>На складе</th><th>Свободно</th><th>Для раскроя</th></tr></thead><tbody>${data.stock.map(s=>{const spec=MATERIAL_PRESETS[s.name];return `<tr><td><strong>${esc(s.name)}</strong></td><td>${s.type}</td><td>${spec?`${spec.sheetWidth}×${spec.sheetHeight} мм`:"—"}</td><td>${s.qty} ${s.unit}</td><td>${s.qty-s.reserved} ${s.unit}</td><td>${spec?badge("Доступен"):"—"}</td></tr>`}).join("")}</tbody></table></div></article>`;
}

function renderSettings(){
  const settings=data.factorySettings;
  crumbs.textContent="Настройки производства";
  app.innerHTML=pageHead("Настройки","Профиль производства","Эти параметры применяются к новым заявкам и заказам; существующие карты сохраняют свои размеры и зазоры.")+
  `<form id="factorySettingsForm" class="stack"><article class="panel pad"><h3 class="card-title">Предприятие</h3><div class="form-group"><label for="factoryCompanyName">Название</label><input id="factoryCompanyName" name="companyName" maxlength="255" required value="${esc(settings.companyName)}"></div><p class="form-note">Это локальные настройки браузерного демо. Общая база, права пользователей и синхронизация между устройствами здесь пока отсутствуют.</p></article>
  <article class="panel pad"><h3 class="card-title">Форматы листов МДФ</h3><p class="muted">Версия условий: ${settings.version}. Размеры, отступ и пропил копируются в новый заказ.</p><div class="grid cols-2">${Object.entries(settings.materials).map(([name,spec])=>{const thickness=spec.thickness;return `<div class="panel pad"><h3>${esc(name)}</h3><div class="form-grid"><div class="form-group"><label>Длина листа, мм</label><input name="sheetWidth${thickness}" type="number" min="100" max="5000" step="1" required value="${spec.sheetWidth}"></div><div class="form-group"><label>Ширина листа, мм</label><input name="sheetHeight${thickness}" type="number" min="100" max="5000" step="1" required value="${spec.sheetHeight}"></div><div class="form-group"><label>Отступ от края, мм</label><input name="margin${thickness}" type="number" min="0" max="100" step="1" required value="${spec.margin}"></div><div class="form-group"><label>Пропил между деталями, мм</label><input name="kerf${thickness}" type="number" min="0" max="20" step="1" required value="${spec.kerf}"></div><label class="settings-toggle full"><input name="allowRotation${thickness}" type="checkbox" ${spec.allowRotation?"checked":""}><span>Поворот деталей без текстуры</span></label></div></div>`}).join("")}</div></article><button class="button primary" type="submit">Сохранить настройки</button></form>`;
}
function stockRows(items){return items.map(s=>{const free=s.qty-s.reserved;return `<tr><td><strong>${esc(s.name)}</strong></td><td>${s.type}</td><td>${s.qty} ${s.unit}</td><td>${s.reserved} ${s.unit}</td><td><strong>${free} ${s.unit}</strong></td><td>${s.min} ${s.unit}</td><td>${badge(free<s.min?"Ниже минимума":"Достаточно")}</td></tr>`}).join("");}
function renderStock(){
  crumbs.textContent="Склад";
  app.innerHTML=pageHead("Склад","Остатки и движения","Свободный остаток, резерв под заказы, минимальный запас и история операций.",'<button class="button primary" data-action="stock-receipt">＋ Приход</button>')+
  `<section class="stats">${stat("Позиций",data.stock.length,"в складском учёте")}${stat("Листов МДФ",data.stock.filter(s=>s.type==="Плита").reduce((n,s)=>n+s.qty,0),"на складе","",true)}${stat("В резерве",data.stock.filter(s=>s.type==="Плита").reduce((n,s)=>n+s.reserved,0),"листов под заказы")}${stat("Ниже минимума",data.stock.filter(s=>s.qty-s.reserved<s.min).length,"нужно пополнить")}${stat("Движений",data.stockMovements.length,"в истории демо")}</section>
  <section class="grid asym"><article class="panel"><div class="panel-head"><div><h2>Остатки на складе</h2><p>Доступно с учётом резерва</p></div><input class="field" id="stockSearch" placeholder="Найти материал"></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Материал</th><th>Тип</th><th>Остаток</th><th>Резерв</th><th>Свободно</th><th>Минимум</th><th>Состояние</th></tr></thead><tbody id="stockBody">${stockRows(data.stock)}</tbody></table></div></article>
  <aside class="panel"><div class="panel-head"><div><h2>Последние движения</h2><p>Резервы и списания по заказам</p></div></div><div class="panel-body activity-list">${data.stockMovements.slice(0,8).map(m=>`<div class="activity-row"><span class="activity-icon">${m.kind}</span><div><b>${esc(m.title)}</b><p>${esc(m.note)}</p></div><time>${m.time}</time></div>`).join("")}</div></aside></section>`;
}

function renderReports(){
  crumbs.textContent="Отчёты";
  const total=data.orders.reduce((sum,o)=>sum+o.amount,0);
  const received=data.orders.reduce((sum,o)=>sum+o.paidAmount,0);
  const pieces=data.orders.reduce((sum,o)=>sum+orderPartCount(o),0);
  const area=data.orders.reduce((sum,o)=>sum+orderPartArea(o),0);
  const groups=[...new Set(data.orders.map(o=>o.direction))].map(name=>{const orders=data.orders.filter(o=>o.direction===name);return {name,orders,amount:orders.reduce((sum,o)=>sum+o.amount,0),received:orders.reduce((sum,o)=>sum+o.paidAmount,0),pieces:orders.reduce((sum,o)=>sum+orderPartCount(o),0),area:orders.reduce((sum,o)=>sum+orderPartArea(o),0)};});
  app.innerHTML=pageHead("Аналитика","Отчёт по демо-данным","Все показатели пересчитываются из заявок, заказов, деталей, оплат и этапов.",'<button class="button primary" data-action="download-report">↓ Скачать CSV</button>')+
  `<section class="stats">${stat("Заказов",data.orders.length,"создано в системе")}${stat("Сумма заказов",money(total),"по всем заказам","",true)}${stat("Оплачено",money(received),"получено от клиентов")}${stat("Деталей",pieces,`${FasadRules.area(area)} м² в заказах`)}${stat("К получению",money(total-received),"остаток по заказам")}</section>
  <section class="grid cols-2"><article class="panel"><div class="panel-head"><div><h2>По направлениям</h2><p>Суммы и детали из карточек заказов</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Направление</th><th>Заказов</th><th>Сумма</th><th>Оплачено</th><th>Деталей</th><th>Площадь</th></tr></thead><tbody>${groups.map(g=>`<tr><td><strong>${g.name}</strong></td><td>${g.orders.length}</td><td>${money(g.amount)}</td><td>${money(g.received)}</td><td>${g.pieces}</td><td>${FasadRules.area(g.area)} м²</td></tr>`).join("")}</tbody></table></div></article>
  <article class="panel"><div class="panel-head"><div><h2>Загрузка по этапам</h2><p>Текущее состояние производственной очереди</p></div></div><div class="panel-body status-bars">${PRODUCTION_STAGES.map(stage=>{const count=data.orders.filter(o=>o.stage===stage).length;return `<div class="status-bar"><span>${stage}</span><div class="progress-line"><i style="width:${Math.round(count/Math.max(1,data.orders.length)*100)}%"></i></div><b>${count}</b></div>`}).join("")}</div></article></section>
  <article class="panel" style="margin-top:14px"><div class="panel-head"><div><h2>Заказы и исполнение</h2><p>Откройте заказ для детализации и карты раскроя</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Заказ</th><th>Клиент</th><th>Этап</th><th>Деталей</th><th>Листов</th><th>Сумма</th><th>Получено</th></tr></thead><tbody>${data.orders.map(o=>`<tr class="clickable" data-order="${o.id}"><td><strong>${o.id}</strong></td><td>${esc(o.client)}</td><td>${o.stage}</td><td>${orderPartCount(o)}</td><td>${calculateOrderNesting(o).sheets.length}</td><td>${money(o.amount)}</td><td>${money(o.paidAmount)}</td></tr>`).join("")}</tbody></table></div></article>`;
}

const renderers={workspace:renderWorkspace,leads:renderLeads,dashboard:renderDashboard,clients:renderClients,orders:renderOrders,cutting:renderCutting,"cutting-batch":renderBatchCutting,production:renderProduction,workers:renderWorkers,materials:renderMaterials,stock:renderStock,reports:renderReports,settings:renderSettings};
const detailRenderers={};
function navigate(route,id){
  location.hash=id?`${route}/${route==="cad"?String(id).split("/").map(encodeURIComponent).join("/"):encodeURIComponent(id)}`:route;
  renderRoute();
}
function renderRoute(){
  const [route="workspace",rawId,rawPartId]=location.hash.replace(/^#/,"").split("/");
  const id=rawId?decodeURIComponent(rawId):undefined,partId=rawPartId?decodeURIComponent(rawPartId):undefined;
  currentRoute=route||"workspace";
  document.querySelector("#factoryName").textContent=data.factorySettings.companyName;
  document.querySelectorAll("#nav button[data-route]").forEach(btn=>btn.classList.toggle("active",btn.dataset.route===currentRoute));
  document.querySelector("#sidebar").classList.remove("open");
  if(id&&detailRenderers[currentRoute])detailRenderers[currentRoute](id); else if(currentRoute==="orders"&&id)renderOrder(id); else if(currentRoute==="clients"&&id)renderClient(id); else if(currentRoute==="leads"&&id)renderLead(id); else if(currentRoute==="cutting")renderCutting(id); else if(currentRoute==="cad")FasadCADUI.render(id,partId); else (renderers[currentRoute]||renderWorkspace)();
  document.querySelector("#ordersBadge").textContent=data.orders.length;
  document.querySelector("#leadsBadge").textContent=data.leads.length;
  document.querySelector('#nav [data-route="production"] em').textContent=data.orders.filter(order=>!["Расчёт","Согласование","Готов к отгрузке"].includes(order.stage)).length;
  app.scrollTop=0; window.scrollTo({top:0});
  lastRenderedHash=location.hash;
}
function toast(text){
  const el=document.querySelector("#toast");el.textContent=text;el.classList.add("show");clearTimeout(window.demoToast);window.demoToast=setTimeout(()=>el.classList.remove("show"),2400);
}
function openModal(title,subtitle,body,saveText="Сохранить"){
  const layer=document.querySelector("#modalLayer");layer.innerHTML=`<section class="modal"><header class="modal-head"><div><h2>${title}</h2><p>${subtitle}</p></div><button class="modal-close" data-close>×</button></header><div class="modal-body">${body}</div><footer class="modal-actions"><button class="button" data-close>Отмена</button><button class="button primary" data-modal-save>${saveText}</button></footer></section>`;layer.classList.add("open");layer.setAttribute("aria-hidden","false");
}
function closeModal(){const layer=document.querySelector("#modalLayer");layer.classList.remove("open");layer.setAttribute("aria-hidden","true");}
function newOrderModal(prefill=""){
  const lead=typeof prefill==="object"?prefill:null;
  const clientName=lead?.client||prefill;
  const selectedClient=lead?.clientId||data.clients.find(c=>c.name===clientName)?.id||"";
  const due=new Date();due.setDate(due.getDate()+14);
  const parts=lead?.parts?.length?lead.parts:[{}];
  openModal("Новый заказ","Заказчик, смета, позиции и предоплата связаны с заказом",`<form class="form-grid" id="newOrderForm" data-lead-id="${esc(lead?.id||"")}"><div class="form-group full"><label>Заказчик из базы</label><select name="clientId" id="orderClientSelect"><option value="">＋ Новый заказчик</option>${data.clients.map(c=>`<option value="${c.id}" ${selectedClient===c.id?"selected":""}>${esc(c.name)} · ${esc(c.phone)}</option>`).join("")}</select></div><div class="form-group full"><label>Имя или компания</label><input name="client" value="${esc(clientName)}" required placeholder="Имя или компания"></div><div class="form-group full"><label>Изделие</label><input name="product" value="${esc(lead?.subject||"")}" required placeholder="Например, фасады для кухни"></div><div class="form-group"><label>Направление</label><select name="direction">${["Эмаль","ПВХ","Шпон"].map(x=>`<option ${lead?.direction===x?"selected":""}>${x}</option>`).join("")}</select></div><div class="form-group"><label>Срок</label><input name="due" type="date" value="${esc(lead?.due||due.toISOString().slice(0,10))}" required></div><div class="form-group"><label>Менеджер</label><select name="manager"><option>Анна Белова</option><option>Ольга Миронова</option></select></div><div class="form-group"><label>Сумма заказа, ₽</label><input name="amount" id="orderAmountInput" type="number" min="0" value="${lead?.amount||partsEstimate(parts)}" required></div><div class="form-group full"><div class="lead-parts-head"><label>Детали заказа</label><button type="button" class="link" id="addOrderPart">＋ Добавить деталь</button></div><div class="lead-parts-list" id="orderPartsList">${parts.map(leadPartRow).join("")}</div><div class="form-note">Эти детали сразу появятся в смете и раскрое заказа.</div></div><div class="form-group"><label>Предоплата, ₽</label><input name="initialPayment" type="number" min="0" value="0"></div><div class="form-group"><label>Способ оплаты</label><select name="paymentMethod"><option>Перевод</option><option>Наличные</option><option>Карта</option></select></div></form>`,"Создать заказ");
  document.querySelector("#modalLayer .modal")?.classList.add("wide");
}
function editLeadModal(lead){
  openModal(`Заявка ${esc(lead.id)}`,"Данные заказчика и детали заявки",`<form class="form-grid" id="editLeadForm" data-lead-id="${esc(lead.id)}"><div class="form-group"><label>Номер · ручной ввод</label><input name="leadNumber" value="${esc(lead.id.replace(/-[ЭПШ]$/,''))}" required></div><div class="form-group"><label>Статус</label><select name="status">${["Новая","Расчёт","Согласование","В заказе"].map(status=>`<option ${lead.status===status?"selected":""}>${status}</option>`).join("")}</select></div><div class="form-group full"><label>Заказчик</label><select name="clientId">${data.clients.map(c=>`<option value="${c.id}" ${lead.clientId===c.id?"selected":""}>${esc(c.name)}</option>`).join("")}</select></div><div class="form-group full"><label>Изделие</label><input name="subject" value="${esc(lead.subject)}" required></div><div class="form-group"><label>Направление</label><select name="direction">${["Эмаль","ПВХ","Шпон"].map(x=>`<option ${lead.direction===x?"selected":""}>${x}</option>`).join("")}</select></div><div class="form-group"><label>Срок</label><input name="due" type="date" value="${esc(lead.due||"")}"></div><div class="form-group full"><label>Адрес доставки</label><input name="address" value="${esc(lead.address||"")}"></div><div class="form-group full"><label>Комментарий</label><textarea name="note">${esc(lead.note||"")}</textarea></div><div class="form-group full"><div class="lead-parts-head"><label>Детали заявки</label><button type="button" class="link" id="addEditLeadPart">＋ Добавить деталь</button></div><div class="lead-parts-list" id="editLeadPartsList">${lead.parts.map(leadPartRow).join("")}</div><div class="lead-total" id="leadPartsTotal"></div></div></form>`,"Сохранить заявку");
  document.querySelector("#modalLayer .modal")?.classList.add("wide");
  refreshLeadTotal(document.querySelector("#editLeadForm"));
}
function editClientModal(client){
  openModal(`Заказчик ${esc(client.name)}`,"Контакты и реквизиты сохраняются во всех связанных карточках",`<form class="form-grid" id="editClientForm" data-client-id="${client.id}"><div class="form-group full"><label>Имя или компания</label><input name="name" value="${esc(client.name)}" required></div><div class="form-group"><label>Организация</label><input name="organization" value="${esc(client.organization||"")}"></div><div class="form-group"><label>Тип</label><select name="type">${["Частный клиент","Дизайн-студия","Застройщик","Мебельная компания"].map(type=>`<option ${client.type===type?"selected":""}>${type}</option>`).join("")}</select></div><div class="form-group"><label>Телефон</label><input name="phone" value="${esc(client.phone==="—"?"":client.phone)}"></div><div class="form-group"><label>Email</label><input name="email" type="email" value="${esc(client.email==="—"?"":client.email)}"></div><div class="form-group"><label>Город</label><input name="city" value="${esc(client.city==="—"?"":client.city)}"></div><div class="form-group"><label>Адрес</label><input name="address" value="${esc(client.address==="—"?"":client.address)}"></div><div class="form-group full"><label>Комментарий</label><textarea name="comment">${esc(client.comment||"")}</textarea></div></form>`,"Сохранить заказчика");
}
async function saveModal(){
  const workerForm=document.querySelector('#workerForm');
  if(workerForm){
    if(!workerForm.reportValidity())return;
    const values=new FormData(workerForm),name=String(values.get('name')).trim(),role=String(values.get('role')).trim();
    if(!name||!role){toast('Введите имя и должность');return;}
    data.workers.push({id:uid(),name,role,initials:name.split(/\s+/).map(part=>part[0]).join('').slice(0,2),color:'green'});
    saveData();closeModal();renderWorkers();return;
  }
  const editClientForm=document.querySelector("#editClientForm");
  if(editClientForm){
    if(!editClientForm.reportValidity())return;
    const client=data.clients.find(c=>c.id===editClientForm.dataset.clientId),f=new FormData(editClientForm);if(!client)return;
    client.name=String(f.get("name")).trim();client.initials=client.name.split(" ").map(x=>x[0]).join("").slice(0,2);
    for(const field of ["organization","type","phone","email","city","address","comment"])client[field]=String(f.get(field)||"").trim()||"—";
    data.leads.filter(l=>l.clientId===client.id).forEach(lead=>{lead.client=client.name;lead.phone=client.phone;lead.email=client.email;lead.organization=client.organization;});
    data.orders.filter(o=>o.clientId===client.id).forEach(order=>{order.client=client.name;order.initials=client.initials;});
    saveData();closeModal();toast("Заказчик обновлён");renderClient(client.id);return;
  }
  const editLeadForm=document.querySelector("#editLeadForm");
  if(editLeadForm){
    if(!editLeadForm.reportValidity())return;
    const lead=data.leads.find(l=>l.id===editLeadForm.dataset.leadId),f=new FormData(editLeadForm),number=String(f.get("leadNumber")).trim();
    if(!lead)return;
    const newId=number===lead.id?lead.id:leadIdFromNumber(number,f.get("direction"));
    if(!newId){toast("Введите номер заявки цифрами (до 80 символов)");return;}
    if(newId!==lead.id&&data.leads.some(l=>l.id===newId)){toast(`Заявка ${newId} уже существует`);return;}
    const linkedOrder=data.orders.find(o=>o.id===lead.orderId);
    if(linkedOrder&&(linkedOrder.reservedSheets||linkedOrder.consumedSheets||!['Расчёт','Согласование'].includes(linkedOrder.stage))){toast('Заказ уже передан в производство. Изменение исходной заявки заблокировано, чтобы не изменить выданное задание.');return;}
    const previous=clone(data),sourceParts=clone(lead.parts),cards=[...editLeadForm.querySelectorAll('.lead-part-card')],updatedParts=partsFromForm(editLeadForm,newId);
    const client=data.clients.find(c=>c.id===f.get("clientId"));
    lead.id=newId;lead.clientId=client.id;lead.client=client.name;lead.phone=client.phone;lead.email=client.email;lead.organization=client.organization;lead.subject=String(f.get("subject")).trim();lead.status=f.get("status");lead.direction=f.get("direction");lead.due=f.get("due")||"";lead.address=f.get("address")||"";lead.note=f.get("note")||"";lead.manual_note=lead.note;
    lead.parts=updatedParts;lead.amount=partsEstimate(lead.parts);
    try{
      if(linkedOrder){
        const parts=updatedParts.map((part,i)=>{
          const originalIndex=sourceParts.findIndex(p=>p.id===cards[i].dataset.sourcePartId),original=originalIndex>=0?linkedOrder.parts[originalIndex]:null;
          const updated={...part,id:original?.id||linkedOrder.id+'-'+uid()};
          if(updated.cadModel||original?.cadModel)updated.cadModel=FasadCAD.modelForPart(updated,updated.cadModel||original.cadModel);
          return updated;
        });
        if(partsEstimate(parts)<linkedOrder.paidAmount)throw Error('Новая смета меньше проведённых оплат. Сначала скорректируйте оплаты заказа.');
        Object.assign(linkedOrder,{leadId:newId,clientId:client.id,client:client.name,initials:client.initials,product:lead.subject,direction:lead.direction,parts,amount:partsEstimate(parts),dueDate:lead.due,due:lead.due?new Date(lead.due+'T00:00:00').toLocaleDateString('ru-RU'):'—',address:lead.address,manual_note:lead.manual_note,cuttingStatus:'draft'});
        linkedOrder.paid=linkedOrder.amount?Math.round(linkedOrder.paidAmount/linkedOrder.amount*100):0;
        delete linkedOrder.production;Object.assign(linkedOrder,FasadProduction.bootstrap(linkedOrder));
      }
      const saved=await saveData();if(saved===false){data=normalizeData(previous);return;}
      closeModal();toast(linkedOrder?'Заявка и связанный заказ обновлены':'Заявка обновлена');navigate('leads',newId);
    }catch(error){data=normalizeData(previous);toast(error.message);}
    return;
  }
  const receiptForm=document.querySelector("#stockReceiptForm");
  if(receiptForm){
    if(!receiptForm.reportValidity())return;
    const f=new FormData(receiptForm),stock=data.stock.find(s=>s.name===f.get("material")),qty=Number(f.get("qty"));
    if(!stock||qty<=0)return;
    stock.qty+=qty;
    data.stockMovements.unshift({kind:"＋",title:`${stock.name} · ${qty} ${stock.unit}`,note:"Приход на склад",time:new Date().toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})});
    saveData();closeModal();toast(`${qty} ${stock.unit} добавлено на склад`);renderStock();return;
  }
  const paymentForm=document.querySelector("#paymentForm");
  if(paymentForm){
    if(!paymentForm.reportValidity())return;
    const order=data.orders.find(o=>o.id===paymentForm.dataset.orderId),amount=Number(new FormData(paymentForm).get("amount"));
    if(!order||amount<=0)return;
    const paidBefore=order.paidAmount;
    const applied=Math.min(amount,Math.max(0,order.amount-paidBefore));
    order.paidAmount=paidBefore+applied;
    order.paid=order.amount?Math.min(100,Math.round(order.paidAmount/order.amount*100)):100;
    order.payments=order.payments||[];
    order.payments.unshift({amount:applied,date:new Date().toLocaleDateString("ru-RU")});
    const client=data.clients.find(c=>c.id===order.clientId);
    if(client)client.balance=Math.max(0,client.balance-applied);
    saveData();closeModal();toast(`Оплата ${money(applied)} добавлена`);renderOrder(order.id);return;
  }
  const form=document.querySelector("#newOrderForm");
  if(form){
    if(!form.reportValidity())return;
    const previous=clone(data);
    const f=new FormData(form),clientName=String(f.get("client")).trim();
    let client=data.clients.find(c=>c.id===f.get("clientId"))||data.clients.find(c=>c.name.toLowerCase()===clientName.toLowerCase());
    const lead=data.leads.find(l=>l.id===form.dataset.leadId);
    if(lead?.orderId){toast(`Для заявки уже создан заказ ${lead.orderId}`);return;}
    if(!client){client={id:`C-${Math.max(0,...data.clients.map(c=>Number(c.id.slice(2))||0))+1}`,name:clientName,initials:clientName.split(" ").map(x=>x[0]).join("").slice(0,2),organization:lead?.organization||"",phone:lead?.phone||"—",email:lead?.email||"—",city:"—",address:lead?.address||"—",comment:"",orders:0,revenue:0,balance:0,type:"Частный клиент"};data.clients.unshift(client);}
    const newId=FasadRules.orderNumber(f.get('orderNumber')||lead?.id,f.get('direction'),partsFromForm(form,'NUMBER'));
    if(!newId){data=normalizeData(previous);toast('Введите номер заказа вручную');return;}
    if(data.orders.some(order=>order.id===newId)){data=normalizeData(previous);toast(`Заказ ${newId} уже существует`);return;}
    const orderParts=partsFromForm(form,newId);
    if(!orderParts.length){toast("Добавьте хотя бы одну позицию заказа");return;}
    const amount=partsEstimate(orderParts);
    const initialPayment=FasadRules.round2(Math.min(amount,Math.max(0,Number(f.get("initialPayment"))||0)));
    data.orders.unshift({id:newId,leadId:lead?.id||null,clientId:client.id,client:client.name,initials:client.initials,product:f.get("product"),direction:f.get("direction"),stage:"Расчёт",status:"Новый",due:new Date(`${f.get("due")}T00:00:00`).toLocaleDateString("ru-RU"),amount,paid:amount?Math.round(initialPayment/amount*100):0,paidAmount:initialPayment,payments:initialPayment?[{id:crypto.randomUUID(),amount:initialPayment,date:new Date().toLocaleDateString("ru-RU"),method:f.get("paymentMethod")}]:[],manager:f.get("manager"),material:false,risk:false,area:0,parts:orderParts,materialSpec:{...FasadFactorySettings.snapshot(data.factorySettings,"МДФ 16 мм"),...lead?.materialSpec},materialSpecs:clone(lead?.materialSpecs||materialSnapshots(data.factorySettings)),cuttingStatus:"draft",productionDone:0});
    Object.assign(data.orders[0],FasadProduction.bootstrap(data.orders[0]));
    if(lead){lead.status="В заказе";lead.orderId=newId;}
    const created=data.orders[0];created.manual_note=String(f.get('manual_note')??(lead?FasadRules.note(lead):''));created.address=lead?.address||client.address||'';created.dueDate=String(f.get('due')||'');
    if(lead?.filmCutting)window.FasadProduct.copyFilm(lead,created);
    if(lead?.manualLayout){created.manualLayout=clone(lead.manualLayout);const positions={};for(const [key,value] of Object.entries(created.manualLayout.positions||{})){const index=lead.parts.findIndex(p=>key.startsWith(p.id+'#'));if(index>=0)positions[created.parts[index].id+key.slice(lead.parts[index].id.length)]=value;}created.manualLayout.positions=positions;created.manualLayout.signature=FasadCuttingLayout.signature(created);}
    const saved=await saveData();if(saved===false){data=normalizeData(previous);return;}closeModal();toast("Заказ создан и добавлен в очередь");navigate("orders",created.id);return;
  }
  const clientForm=document.querySelector("#newClientForm");
  if(clientForm){
    if(!clientForm.reportValidity())return;
    const f=new FormData(clientForm),name=String(f.get("name")).trim();
    const client={id:`C-${Math.max(0,...data.clients.map(c=>Number(c.id.slice(2))||0))+1}`,name,initials:name.split(" ").map(x=>x[0]).join("").slice(0,2),organization:f.get("organization")||"",phone:f.get("phone")||"—",email:f.get("email")||"—",city:f.get("city")||"—",address:f.get("address")||"—",comment:f.get("comment")||"",orders:0,revenue:0,balance:0,type:f.get("type"),createdAt:new Date().toISOString().slice(0,10)};
    data.clients.unshift(client);saveData();closeModal();toast("Клиент добавлен");navigate("clients",client.id);return;
  }
  closeModal();
}

function currentCuttingOrder(){const record=data.orders.find(o=>o.id===app.dataset.cuttingOrder)||data.leads.find(l=>l.id===app.dataset.cuttingOrder);return window.FasadProduct?.cuttingRecord(record)||record;}
function changeCuttingParts(record,change){
  const owner=data.orders.find(o=>o.id===record.id)||data.leads.find(o=>o.id===record.id)||record;
  if(owner.consumedSheets){toast('После списания материала детали менять нельзя');return false;}
  const before=clone(record.parts),adjustment=Number(owner.amount||0)-partsEstimate(before);
  change();const amount=FasadRules.round2(partsEstimate(record.parts)+adjustment);
  if(amount<Number(owner.paidAmount||0)||amount<0){record.parts=before;owner.parts=before;toast('Смета не может стать меньше проведённых оплат');return false;}
  owner.parts=record.parts;owner.amount=amount;record.amount=amount;owner.cuttingStatus='draft';record.cuttingStatus='draft';
  if(data.orders.includes(owner))owner.paid=amount?Math.round(Number(owner.paidAmount||0)/amount*100):0;
  return true;
}
function selectedPlacement(order){
  const result=calculateOrderNesting(order);
  for(const [sheetIndex,sheet] of result.sheets.entries()){
    const placement=sheet.placements.find(item=>FasadCuttingLayout.key(item)===selectedLayoutKey);
    if(placement)return {placement,sheetIndex,result};
  }
  return null;
}
function changeManualPlacement(order,key,patch){
  if(order.consumedSheets){toast("После списания листов раскладку менять нельзя");return false;}
  const base=calculateNesting(order.parts,order.materialSpec,order.materialSpecs);
  try{
    order.manualLayout=FasadCuttingLayout.revise(order,base,key,patch);
    order.cuttingStatus="draft";saveData();updateCuttingResults(order);
    return true;
  }catch(error){toast(error.message);return false;}
}
function moveSelectedToNextSheet(order){
  const selected=selectedPlacement(order);
  if(!selected){toast("Сначала выберите деталь на карте");return;}
  if(selected.result.sheets.length<2){toast("В раскрое пока один лист");return;}
  const target=[...selected.result.sheets.keys()].map(offset=>(selected.sheetIndex+offset+1)%selected.result.sheets.length)
    .find(index=>index!==selected.sheetIndex&&selected.result.sheets[index].materialKey===selected.result.sheets[selected.sheetIndex].materialKey);
  if(target===undefined){toast("Нет другого листа той же толщины и цвета");return;}
  const sheet=selected.result.sheets[target],spec=sheet.spec||order.materialSpec;
  const xs=[spec.margin,...sheet.placements.map(p=>p.x+p.placedWidth+spec.kerf)];
  const ys=[spec.margin,...sheet.placements.map(p=>p.y+p.placedHeight+spec.kerf)];
  for(const y of ys)for(const x of xs){
    const base=calculateNesting(order.parts,order.materialSpec,order.materialSpecs);
    try{
      const updated=FasadCuttingLayout.revise(order,base,selectedLayoutKey,{sheetIndex:target,x,y,rotated:selected.placement.rotated});
      order.manualLayout=updated;order.cuttingStatus="draft";saveData();updateCuttingResults(order);toast(`Деталь перенесена на лист ${target+1}`);return;
    }catch{/* Try the next available position. */}
  }
  toast("На другом листе нет свободного места с нужным пропилом");
}
function releaseCutting(order){
  if(order.materialSpec.mode==='film'){toast('Заявка поставщику показана под картами плёнки. Распил МДФ запускается отдельно.');return;}
  if(data.leads.includes(order)){newOrderModal(order);return;}
  const result=calculateOrderNesting(order);
  if(!result.sheets.length||result.oversized.length){toast("Сначала исправьте детали, которые не помещаются на лист");return;}
  try{
    const counts=new Map();
    result.sheets.forEach(sheet=>counts.set(sheet.materialName,(counts.get(sheet.materialName)||0)+1));
    const outcome=FasadProduction.releaseCutting(order,data.stock,[...counts].map(([materialName,count])=>({materialName,count})));
    Object.assign(order,outcome.order);data.stock=outcome.stock;data.stockMovements.unshift(...outcome.movements);
    saveData();toast(`${order.id}: ${result.sheets.length} листа зарезервировано, задание отправлено на распил`);renderCutting(order.id);
  }catch(error){toast(error.message);}
}
function advanceOrder(order){
  const route=FasadProduction.routeFor(order),position=route.indexOf(order.stage);
  if(position<0||position===route.length-1){toast("Заказ уже прошёл маршрут");return;}
  if(route[position+1]==="Распил"){navigate("cutting",order.id);toast("Рассчитайте карту и зарезервируйте листы для распила");return;}
  if(position>=2){navigate("production-stage",order.id);return;}
  try{const outcome=FasadProduction.completeStage(order,data.stock);Object.assign(order,outcome.order);data.stock=outcome.stock;data.stockMovements.unshift(...outcome.movements);saveData();toast(`${order.id} передан на этап «${order.stage}»`);renderOrder(order.id);}catch(error){toast(error.message);}
}
function downloadCnc(order){
  const machine=data.machines.find(item=>item.id===order.cncMachineId);
  if(!machine){toast("Выберите станок для задания ЧПУ");return;}
  const result=calculateOrderNesting(order);
  if(!result.sheets.length||result.oversized.length){toast("Проверьте карту раскроя перед выгрузкой задания");return;}
  const job={previewOnly:true,format:"fasad_cnc_preview_v1",warning:"Черновик задания, не управляющая программа станка",program:`CNC-${order.id.replace("F-","")}-01`,order:order.id,machine:{id:machine.id,name:machine.name,controller:machine.controller},material:order.materialSpec,createdAt:new Date().toISOString(),sheets:result.sheets.map((sheet,index)=>({sheet:index+1,parts:sheet.placements.map(p=>({id:p.id,name:p.name,number:p.number,x:p.x,y:p.y,width:p.placedWidth,height:p.placedHeight,sourceWidth:p.width,sourceHeight:p.height,rotation:p.rotated?90:0,edge:p.edge}))}))};
  const url=URL.createObjectURL(new Blob([JSON.stringify(job,null,2)],{type:"application/json"}));
  const link=document.createElement("a");link.href=url;link.download=`CNC_${order.id}_${machine.id}.preview.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast(`Черновик ЧПУ для «${machine.name}» сформирован`);
}
function printOrder(order){
  const content=`<!doctype html><html lang="ru"><meta charset="utf-8"><title>Бланк ${order.id}</title><style>body{font:14px Arial;margin:30px;color:#172033}h1{font-size:24px}table{border-collapse:collapse;width:100%;margin-top:22px}th,td{border:1px solid #bdc5cc;padding:9px;text-align:left}th{background:#f1f3f5}small{color:#607080}</style><h1>Заказ ${order.id}</h1><p><b>Клиент:</b> ${esc(order.client)}<br><b>Изделие:</b> ${esc(order.product)}<br><b>Материал:</b> ${order.materialSpec.name}<br><b>Срок:</b> ${order.due}</p><table><thead><tr><th>Деталь</th><th>Высота</th><th>Ширина</th><th>Количество</th><th>Кромка</th></tr></thead><tbody>${order.parts.map(p=>`<tr><td>${esc(p.name)}</td><td>${p.height}</td><td>${p.width}</td><td>${p.qty}</td><td>${p.edge}</td></tr>`).join("")}</tbody></table><p>Всего: ${orderPartCount(order)} деталей · ${FasadRules.area(orderPartArea(order))} м²</p><small>Фасад Портал · демонстрационный бланк</small></html>`;
  const windowRef=window.open("","_blank");
  if(!windowRef){toast("Разрешите всплывающее окно для печати бланка");return;}
  windowRef.document.write(content);windowRef.document.close();windowRef.focus();windowRef.print();
}
function downloadReport(){
  const rows=[["Заказ","Клиент","Направление","Этап","Деталей","Площадь м2","Листов","Сумма","Оплачено"]];
  data.orders.forEach(o=>rows.push([o.id,o.client,o.direction,o.stage,orderPartCount(o),FasadRules.area(orderPartArea(o)),calculateOrderNesting(o).sheets.length,o.amount,o.paidAmount]));
  const csv="\uFEFF"+rows.map(row=>row.map(value=>`"${String(value).replaceAll('"','""')}"`).join(";")).join("\r\n");
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;link.download="fasad-demo-report.csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast("Отчёт CSV сформирован из текущих данных");
}

document.addEventListener("click",event=>{
  const route=event.target.closest("[data-route]"); if(route){navigate(route.dataset.route);return}
  const order=event.target.closest("[data-order]"); if(order){closeModal();navigate("orders",order.dataset.order);return}
  const client=event.target.closest("[data-client]"); if(client){closeModal();navigate("clients",client.dataset.client);return}
  if(event.target.closest("[data-close]")){closeModal();return}
  if(event.target.closest("[data-modal-save]")){saveModal();return}
  const action=event.target.closest("[data-action]")?.dataset.action;
  if(action==="new-worker"){openModal('Новый работник','Справочник исполнителей. Учётная запись для входа создаётся отдельно.', '<form id="workerForm" class="form-grid"><div class="form-group full"><label>Имя<input name="name" maxlength="120" required></label></div><div class="form-group full"><label>Должность<input name="role" maxlength="120" required></label></div></form>','Добавить');return;}
  if(action==="load-cad-sample"){loadCadSample();return}
  if(action==="reset-manual-layout"){const o=currentCuttingOrder();if(o){if(o.consumedSheets){toast("После списания листов раскладку менять нельзя");return}o.manualLayout=null;o.cuttingStatus="draft";saveData();updateCuttingResults(o);toast("Автоматический раскрой восстановлен");}return}
  if(action==="rotate-piece"){const o=currentCuttingOrder(),selected=o&&selectedPlacement(o);if(!selected){toast("Сначала выберите деталь на карте");return}if(changeManualPlacement(o,selectedLayoutKey,{rotated:!selected.placement.rotated}))toast("Поворот детали сохранён");return}
  if(action==="move-piece-sheet"){const o=currentCuttingOrder();if(o)moveSelectedToNextSheet(o);return}
  if(action==="open-cad"){const button=event.target.closest("[data-part-id]");navigate("cad",`${button.dataset.id}/${button.dataset.partId}`);return}
  if(action&&FasadCADUI.action(action))return;
  if(action==="new-order"){const clientId=location.hash.startsWith("#clients/")?location.hash.split("/")[1]:null;newOrderModal(data.clients.find(c=>c.id===clientId)?.name||"");return}
  if(action==="new-client"){openModal("Новый заказчик","Контакт появится в базе заказчиков и будет доступен в заявках",'<form class="form-grid" id="newClientForm"><div class="form-group full"><label>Имя или компания</label><input name="name" required></div><div class="form-group"><label>Организация</label><input name="organization"></div><div class="form-group"><label>Тип</label><select name="type"><option>Частный клиент</option><option>Дизайн-студия</option><option>Застройщик</option><option>Мебельная компания</option></select></div><div class="form-group"><label>Телефон</label><input name="phone"></div><div class="form-group"><label>Email</label><input name="email" type="email"></div><div class="form-group"><label>Город</label><input name="city"></div><div class="form-group full"><label>Адрес</label><input name="address"></div><div class="form-group full"><label>Комментарий</label><textarea name="comment"></textarea></div></form>');return}
  if(action==="edit-client"){const client=data.clients.find(c=>c.id===event.target.closest("[data-id]").dataset.id);if(client)editClientModal(client);return}
  if(action==="stock-receipt"){openModal("Приход материала","Остаток и история склада обновятся сразу",`<form class="form-grid" id="stockReceiptForm"><div class="form-group full"><label>Материал</label><select name="material">${data.stock.map(s=>`<option value="${esc(s.name)}">${esc(s.name)} · ${s.unit}</option>`).join("")}</select></div><div class="form-group full"><label>Количество</label><input name="qty" type="number" min="1" value="10" required></div></form>`,"Провести приход");return}
  if(action==="worker-details"){const w=data.workers.find(x=>x.id===event.target.closest("[data-id]").dataset.id);if(w){const reports=FasadProduction.reports(data).filter(row=>row.workerId===w.id),active=data.orders.flatMap(order=>order.production?.stages||[]).filter(stage=>stage.status==="in_progress"&&stage.workerId===w.id).length;openModal(esc(w.name),esc(w.role),`<div class="detail-grid"><div class="detail"><small>Активных заданий</small><strong>${active}</strong></div><div class="detail"><small>Отчётов</small><strong>${reports.length}</strong></div><div class="detail"><small>Годных деталей</small><strong>${reports.reduce((sum,row)=>sum+Number(row.done||0),0)}</strong></div><div class="detail"><small>Брак</small><strong>${reports.reduce((sum,row)=>sum+Number(row.defects||0),0)}</strong></div></div><p class="form-note">Показатели рассчитаны из отчётов по этапам текущих заказов.</p>`,"Закрыть");}return}
  if(action==="lead-to-order"){const l=data.leads.find(x=>x.id===event.target.closest("[data-lead]").dataset.lead);newOrderModal(l||"");return}
  if(action==="open-lead-cutting"){navigate("cutting",event.target.closest("[data-id]").dataset.id);return}
  if(action==="edit-lead"){const lead=data.leads.find(l=>l.id===event.target.closest("[data-id]").dataset.id);if(lead)editLeadModal(lead);return}
  if(action==="advance-order"){const o=data.orders.find(x=>x.id===event.target.closest("[data-id]").dataset.id);if(o)advanceOrder(o);return}
  if(action==="open-cutting"){navigate("cutting",event.target.closest("[data-id]").dataset.id);return}
  if(action==="print-order"){const id=decodeURIComponent(location.hash.split("/")[1]||""),o=data.orders.find(x=>x.id===id);if(o)printOrder(o);return}
  if(action==="add-payment"){const o=data.orders.find(x=>x.id===event.target.closest("[data-id]").dataset.id);if(o){const due=Math.max(0,o.amount-o.paidAmount);if(!due){toast("Заказ уже оплачен полностью");return}openModal("Оплата по заказу",`${o.id} · осталось ${money(due)}`,`<form class="form-grid" id="paymentForm" data-order-id="${o.id}"><div class="form-group full"><label>Сумма оплаты, ₽</label><input name="amount" type="number" min="1" max="${Math.ceil(due)}" value="${Math.ceil(due)}" required></div></form>`,"Добавить оплату");}return}
  if(action==="download-cnc"){const o=currentCuttingOrder();if(o)downloadCnc(o);return}
  if(action==="add-cnc-machine"){
    const name=prompt("Название станка");
    if(!name?.trim())return;
    const controller=prompt("Управляющая система / контроллер (необязательно)")?.trim()||"Не настроен";
    const machine={id:`M-${Date.now().toString(36)}`,name:name.trim(),controller};
    data.machines.push(machine);
    const order=currentCuttingOrder();
    if(order)order.cncMachineId=machine.id;
    saveData();
    if(order)renderCutting(order.id);
    toast(`Станок «${machine.name}» добавлен`);
    return;
  }
  if(action==="print-cutting"){const o=currentCuttingOrder();if(!o||!calculateOrderNesting(o).sheets.length){toast("Сначала добавьте детали для раскроя");return}window.print();return}
  if(action==="print-batch"){if(!batchSelectedIds.size){toast("Выберите заказы для раскроя");return}window.print();return}
  if(action==="download-report"){downloadReport();return}
  if(event.target.id==="importExcelButton"){document.querySelector("#importExcelFile")?.click();return}
  if(event.target.id==="addLeadPart"){document.querySelector("#leadPartsList")?.insertAdjacentHTML("beforeend",leadPartRow());refreshLeadTotal(document.querySelector("#leadForm"));return}
  if(event.target.id==="addEditLeadPart"){document.querySelector("#editLeadPartsList")?.insertAdjacentHTML("beforeend",leadPartRow());refreshLeadTotal(document.querySelector("#editLeadForm"));return}
  if(event.target.closest(".lead-part-row button")){const form=event.target.closest("form");event.target.closest(".lead-part-card").remove();if(form)refreshLeadTotal(form);return}
  if(event.target.id==="addPart"){const o=currentCuttingOrder();if(!o)return;if(!changeCuttingParts(o,()=>o.parts.push({id:uid(),name:"Новая деталь",height:600,width:400,qty:1,price:0,edge:"4 стороны",grain:false})))return;saveData();renderCutting(o.id);toast("Деталь добавлена и карта пересчитана");return}
  if(event.target.id==="calculateCutting"){const o=currentCuttingOrder();if(o){updateCuttingResults(o);saveData();toast("Карта пересчитана по актуальным деталям")};return}
  if(event.target.id==="releaseCutting"){const o=currentCuttingOrder();if(o)releaseCutting(o);return}
  if(event.target.closest(".part-row button")){const row=event.target.closest(".part-row"),o=currentCuttingOrder();if(!o)return;if(!changeCuttingParts(o,()=>o.parts=o.parts.filter(p=>p.id!==row.dataset.partId)))return;row.remove();saveData();updateCuttingResults(o);toast("Деталь удалена, карта обновлена");return}
  const leadRowTarget=event.target.closest("[data-open-lead]");if(leadRowTarget){navigate("leads",leadRowTarget.dataset.openLead);return}
});
document.addEventListener("change",async event=>{
  if(event.target.id!=="importExcelFile")return;
  const input=event.target,file=input.files?.[0];
  if(!file)return;
  try{
    if(file.size>4*1024*1024)throw Error("Файл больше 4 МБ; разбейте заказ на несколько файлов");
    if(!/\.(xlsx|xls|csv)$/i.test(file.name))throw Error("Выберите файл Excel .xlsx, .xls или .csv");
    const workbook=XLSX.read(new Uint8Array(await file.arrayBuffer()),{type:"array",sheetRows:5000});
    let imported=null;
    for(const name of workbook.SheetNames){
      try{
        const rows=XLSX.utils.sheet_to_json(workbook.Sheets[name],{header:1,defval:"",blankrows:true});
        const candidate=FasadExcelOrderImport.importRows(rows);
        if(!imported||candidate.sourceRows>imported.sourceRows)imported=candidate;
      }catch{/* Other sheets can contain instructions or a summary. */}
    }
    if(!imported)throw Error("Не найдены позиции: проверьте заголовки «Длина» и «Ширина»");
    const list=document.querySelector("#leadPartsList"),form=document.querySelector("#leadForm");
    if(!list||!form)throw Error("Откройте форму новой заявки и повторите импорт");
    const cards=[...list.querySelectorAll(".lead-part-card")];
    if(cards.length===1&&!["partName","partHeight","partWidth"].some(name=>cards[0].querySelector(`[name="${name}"]`)?.value.trim()))list.innerHTML="";
    list.insertAdjacentHTML("beforeend",imported.parts.map(leadPartRow).join(""));
    [...list.querySelectorAll(".lead-part-card")].forEach((card,index)=>{
      if(card.querySelector(".lead-part-collapse"))return;
      const read=name=>card.querySelector(`[name="${name}"]`)?.value.trim()||"";
      const summary=[read("partName"),`${read("partHeight")} × ${read("partWidth")} мм`,`${read("partQty")} шт.`,read("partColor")].filter(Boolean).join(" · ");
      card.querySelector(".lead-part-card-head")?.insertAdjacentHTML("beforeend",`<span class="lead-part-summary" aria-live="polite">${esc(summary)}</span><button type="button" class="lead-part-collapse" aria-expanded="${index===0}">${index===0?"Свернуть":"Развернуть"}</button>`);
      if(index>0)card.classList.add("is-collapsed");
    });
    refreshLeadTotal(form);
    toast(`Загружено ${imported.sourceRows} строк · ${imported.parts.length} позиций${imported.warnings.length?` · пропущено ${imported.warnings.length} ошибочных строк`:""}`);
  }catch(error){toast(error.message||"Не удалось прочитать Excel");}
  finally{input.value="";}
});
document.addEventListener("submit",async event=>{
  if(event.target.id==="factorySettingsForm"){
    event.preventDefault();if(!event.target.reportValidity())return;
    const form=event.target,materials={};
    for(const [name,spec] of Object.entries(data.factorySettings.materials)){
      const suffix=spec.thickness;
      materials[name]={sheetWidth:Number(form.elements.namedItem(`sheetWidth${suffix}`).value),sheetHeight:Number(form.elements.namedItem(`sheetHeight${suffix}`).value),margin:Number(form.elements.namedItem(`margin${suffix}`).value),kerf:Number(form.elements.namedItem(`kerf${suffix}`).value),allowRotation:form.elements.namedItem(`allowRotation${suffix}`).checked};
    }
    try{
      data.factorySettings=FasadFactorySettings.revise(data.factorySettings,{companyName:form.elements.namedItem("companyName").value,materials});
      Object.assign(MATERIAL_PRESETS,data.factorySettings.materials);
      saveData();renderSettings();document.querySelector("#factoryName").textContent=data.factorySettings.companyName;
      toast(`Настройки сохранены · версия ${data.factorySettings.version}`);
    }catch(error){toast(error.message||"Проверьте параметры листов");}
    return;
  }
  if(event.target.id==="leadForm"){
    event.preventDefault();if(!event.target.reportValidity())return;
    const f=new FormData(event.target),id=leadIdFromNumber(f.get("leadNumber"),f.get("direction"));
    if(!id){toast("Введите номер заявки цифрами (до 80 символов)");return;}
    if(data.leads.some(l=>l.id===id)){toast(`Заявка ${id} уже существует`);return;}
    const previous=clone(data);event.target.querySelectorAll('button[type="submit"]').forEach(b=>b.disabled=true);const client=resolveLeadClient(event.target),parts=partsFromForm(event.target,id),mode=event.submitter?.dataset.submitMode||"lead";
    const lead={id,clientId:client.id,client:client.name,phone:client.phone,email:client.email,organization:client.organization,address:client.address,subject:String(f.get("subject")).trim(),source:f.get("source"),direction:f.get("direction"),status:"Новая",date:"Только что",due:f.get("due")||"",note:f.get("note")||"",amount:partsEstimate(parts),parts,materialSpec:FasadFactorySettings.snapshot(data.factorySettings,"МДФ 16 мм"),materialSpecs:materialSnapshots(data.factorySettings),cuttingStatus:"draft"};
    lead.manual_note=lead.note;data.leads.unshift(lead);const draft=window.FasadDrafts?.capture(event.target);const saved=await saveData();if(saved===false){data=normalizeData(previous);return;}window.FasadDrafts?.submitted(draft);toast(`Заявка ${id} сохранена`);
    if(mode==="cutting"){navigate("cutting",id);return;}
    if(mode==="cad"&&parts[0]){navigate("cad",`${id}/${parts[0].id}`);return;}
    renderWorkspace();
    if(mode==="order")newOrderModal(lead);
  }
});
document.addEventListener("input",event=>{
  if(FasadCADUI.input(event.target,"input"))return;
  if(event.target.closest(".lead-part-card")){const form=event.target.closest("form");if(form)refreshLeadTotal(form)}
  if(event.target.name==="client"&&event.target.closest("#leadForm")){const select=document.querySelector("#leadClientSelect"),chosen=data.clients.find(c=>c.id===select?.value);if(chosen&&chosen.name!==event.target.value)select.value="";}
  if(event.target.id==="clientSearch"){const q=event.target.value.toLowerCase();document.querySelector("#clientsBody").innerHTML=clientRows(data.clients.filter(c=>`${c.name} ${c.phone} ${c.email}`.toLowerCase().includes(q)))}
  if(event.target.id==="leadSearch"){const q=event.target.value.toLowerCase(),status=document.querySelector("#leadStatusFilter")?.value;document.querySelector("#leadsBody").innerHTML=data.leads.filter(l=>(status==="Все статусы"||l.status===status)&&`${l.id} ${l.client} ${l.phone} ${l.subject}`.toLowerCase().includes(q)).map(leadRow).join("")}
  if(event.target.id==="orderSearch"){const q=event.target.value.toLowerCase();const list=data.orders.filter(o=>(activeOrderFilter==="Все"||o.status===activeOrderFilter)&&`${o.id} ${o.client} ${o.product}`.toLowerCase().includes(q));document.querySelector("#ordersBody").innerHTML=list.map(orderRow).join("")}
  if(event.target.id==="stockSearch"){const q=event.target.value.toLowerCase();document.querySelector("#stockBody").innerHTML=stockRows(data.stock.filter(s=>s.name.toLowerCase().includes(q)))}
  const field=event.target.dataset.partField,row=event.target.closest(".part-row"),order=currentCuttingOrder();
  if(field&&row&&order){const part=order.parts.find(p=>p.id===row.dataset.partId);if(part){if(!changeCuttingParts(order,()=>part[field]=field==="name"||field==="edge"?event.target.value:field==="grain"?event.target.checked:Math.max(0,Number(event.target.value)||0))){renderCutting(order.id);return;}saveData();updateCuttingResults(order);}}
  if(order&&event.target.id==="cutKerf"){order.materialSpec.kerf=Math.max(0,Number(event.target.value)||0);delete order.materialSpec.gapX;delete order.materialSpec.gapY;order.cuttingStatus="draft";saveData();updateCuttingResults(order)}
  if(order&&event.target.id==="cutMargin"){order.materialSpec.margin=Math.max(0,Number(event.target.value)||0);for(const edge of ['Left','Right','Top','Bottom'])delete order.materialSpec['margin'+edge];order.cuttingStatus="draft";saveData();updateCuttingResults(order)}
  if(order&&["cutSheetWidth","cutSheetHeight"].includes(event.target.id)){
    const key=event.target.id==="cutSheetWidth"?"sheetWidth":"sheetHeight";
    order.materialSpec[key]=Math.min(5000,Math.max(100,Number(event.target.value)||100));
    order.cuttingStatus="draft";saveData();updateCuttingResults(order);
  }
});
document.addEventListener("change",event=>{
  if(FasadCADUI.input(event.target,"change"))return;
  if(event.target.id==="cutOverlayMode"){cuttingOverlayMode=event.target.value;const order=currentCuttingOrder();if(order)updateCuttingResults(order);return;}
  if(event.target.id==="batchSelectAll"){
    batchSelectedIds.clear();
    if(event.target.checked)data.orders.forEach(order=>batchSelectedIds.add(order.id));
    renderBatchCutting();return;
  }
  if(event.target.classList.contains("batch-order-check")){
    if(event.target.checked)batchSelectedIds.add(event.target.value);else batchSelectedIds.delete(event.target.value);
    renderBatchCutting();return;
  }
  if(event.target.id==="leadStatusFilter"){const q=document.querySelector("#leadSearch")?.value.toLowerCase()||"",status=event.target.value;document.querySelector("#leadsBody").innerHTML=data.leads.filter(l=>(status==="Все статусы"||l.status===status)&&`${l.id} ${l.client} ${l.phone} ${l.subject}`.toLowerCase().includes(q)).map(leadRow).join("");return}
  if(event.target.id==="leadClientSelect"){
    const client=data.clients.find(c=>c.id===event.target.value),form=document.querySelector("#leadForm");
    if(client&&form){for(const [key,value] of Object.entries({client:client.name,organization:client.organization,phone:client.phone,email:client.email,address:client.address})){const input=form.elements.namedItem(key);if(input)input.value=value==="—"?"":value;}}
    return;
  }
  if(event.target.id==="cuttingOrderSelect"){navigate("cutting",event.target.value);return}
  const order=currentCuttingOrder();
  if(order&&event.target.id==="cncMachineSelect"){order.cncMachineId=event.target.value||null;saveData();return}
  if(order&&event.target.id==="cutAllowRotation"){
    order.materialSpec.allowRotation=event.target.checked;
    order.cuttingStatus="draft";saveData();updateCuttingResults(order);return;
  }
  if(order&&event.target.id==="materialPreset"){order.materialSpec=FasadFactorySettings.snapshot(data.factorySettings,event.target.value);order.cuttingStatus="draft";saveData();renderCutting(order.id);toast("Материал изменён, карта пересчитана по текущей версии условий");}
});
document.addEventListener("click",event=>{
  const tab=event.target.closest("#orderTabs [data-filter]");if(tab){activeOrderFilter=tab.dataset.filter;renderOrders()}
});
let layoutDrag=null;
function pointInSheet(svg,event){
  const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}
document.addEventListener("pointerdown",event=>{
  if(currentRoute!=="cutting"||event.button!==0)return;
  const group=event.target.closest("#cuttingMaps .layout-piece"),order=currentCuttingOrder();
  if(!group||!order||order.consumedSheets)return;
  selectedLayoutKey=group.dataset.layoutKey;
  document.querySelectorAll("#cuttingMaps .layout-piece").forEach(node=>node.classList.toggle("selected",node===group));
  const label=document.querySelector("#selectedPiece");if(label)label.textContent=`Выбрана ${selectedLayoutKey} · перетащите для перемещения`;
  const svg=group.closest("svg"),point=pointInSheet(svg,event);
  layoutDrag={svg,group,order,key:selectedLayoutKey,sheetIndex:Number(group.dataset.sheetIndex),x:Number(group.dataset.x),y:Number(group.dataset.y),start:point,pointerId:event.pointerId};
  svg.setPointerCapture(event.pointerId);event.preventDefault();
});
document.addEventListener("pointermove",event=>{
  const drag=layoutDrag;if(!drag||event.pointerId!==drag.pointerId)return;
  const point=pointInSheet(drag.svg,event),dx=point.x-drag.start.x,dy=point.y-drag.start.y;
  const result=calculateOrderNesting(drag.order),sheet=result.sheets[drag.sheetIndex],piece=sheet.placements.find(p=>FasadCuttingLayout.key(p)===drag.key);
  drag.candidate=FasadCuttingLayout.nearest(piece,{...sheet,spec:sheet.spec||drag.order.materialSpec},drag.x+dx,drag.y+dy,piece.rotated,{...drag.order.snapSettings,...(event.shiftKey?{enabled:false}:{})});
  const candidate=drag.candidate;drag.group.setAttribute("transform",`translate(${candidate.x-drag.x} ${candidate.y-drag.y})`);
  drag.group.classList.toggle('snap-invalid',!candidate.valid);drag.group.classList.toggle('snap-active',candidate.valid&&candidate.snapped);
  const label=document.querySelector('#selectedPiece');if(label)label.textContent=candidate.valid?(candidate.snapped?'Примагничено: ':'Положение: ')+`X ${candidate.x}, Y ${candidate.y} мм`:'Недопустимо: граница листа или зазор';
});
document.addEventListener("pointerup",event=>{
  const drag=layoutDrag;if(!drag||event.pointerId!==drag.pointerId)return;
  layoutDrag=null;drag.group.removeAttribute("transform");drag.group.classList.remove('snap-invalid','snap-active');
  const point=pointInSheet(drag.svg,event),dx=point.x-drag.start.x,dy=point.y-drag.start.y;
  if(Math.abs(dx)+Math.abs(dy)<0.5)return;
  const sheet=calculateOrderNesting(drag.order).sheets[drag.sheetIndex],piece=sheet.placements.find(p=>FasadCuttingLayout.key(p)===drag.key);
  const candidate=FasadCuttingLayout.nearest(piece,{...sheet,spec:sheet.spec||drag.order.materialSpec},drag.x+dx,drag.y+dy,piece.rotated,{...drag.order.snapSettings,...(event.shiftKey?{enabled:false}:{})});
  if(!candidate.valid){toast('Недопустимое положение: деталь возвращена на место');return;}
  if(changeManualPlacement(drag.order,drag.key,{sheetIndex:drag.sheetIndex,x:candidate.x,y:candidate.y}))toast(candidate.snapped?'Деталь примагничена и сохранена':"Ручная раскладка сохранена");
});
document.addEventListener("pointercancel",event=>{if(layoutDrag&&event.pointerId===layoutDrag.pointerId){layoutDrag.group.removeAttribute("transform");layoutDrag.group.classList.remove('snap-invalid','snap-active');layoutDrag=null;}});
document.querySelector("#nav").addEventListener("click",event=>{const b=event.target.closest("[data-route]");if(b)navigate(b.dataset.route)});
document.querySelector("#mobileMenu").addEventListener("click",()=>document.querySelector("#sidebar").classList.toggle("open"));
document.querySelector("#quickCreate").addEventListener("click",()=>newOrderModal());
document.querySelector("#resetDemo").addEventListener("click",()=>{const previous=data;try{const raw=localStorage.getItem("fasad-demo-data");if(raw)localStorage.setItem(`fasad-demo-backup-${new Date().toISOString()}`,raw);data=normalizeData(FasadKP.cleanDemo(data));saveData();toast("Демонстрационные записи удалены, рабочие сохранены");renderRoute()}catch{data=previous;toast("Не удалось создать резервную копию; данные не очищены")}});
document.querySelector("#exportDemo").addEventListener("click",()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="fasad-workspace.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
document.querySelector("#helpButton").addEventListener("click",()=>openModal("Как работать с демо","Данные хранятся в этом браузере",'<div class="form-note">Создайте клиента, добавьте артикул в справочник, затем заказ и КП. Данные этого локального интерфейса не передаются в серверную базу.</div>',"Понятно"));
document.querySelector("#notificationButton").addEventListener("click",()=>openModal("Уведомления","Текущие события",'<div class="empty">Новых уведомлений нет</div>',"Закрыть"));
document.querySelector("#globalSearch").addEventListener("focus",()=>{});
document.querySelector("#globalSearch").addEventListener("keydown",event=>{
  if(event.key!=="Enter")return;
  const q=event.target.value.toLowerCase();
  const orders=data.orders.filter(o=>`${o.id} ${o.client} ${o.product}`.toLowerCase().includes(q));
  const clients=data.clients.filter(c=>`${c.name} ${c.phone}`.toLowerCase().includes(q));
  const results=[
    ...orders.map(o=>`<div class="activity-row clickable" data-order="${o.id}"><span class="activity-icon">▤</span><div><b>${o.id} · ${o.product}</b><p>${o.client}</p></div><button class="link">Открыть</button></div>`),
    ...clients.map(c=>`<div class="activity-row clickable" data-client="${c.id}"><span class="activity-icon">◎</span><div><b>${c.name}</b><p>${c.phone}</p></div><button class="link">Открыть</button></div>`)
  ];
  openModal("Результаты поиска",`Найдено: ${results.length}`,`<div class="activity-list">${results.join("")||'<div class="empty">Ничего не найдено</div>'}</div>`,"Закрыть");
});
window.addEventListener("hashchange",()=>{if(lastRenderedHash!==location.hash)renderRoute();});
document.addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){event.preventDefault();document.querySelector("#globalSearch").focus()}if(event.key==="Escape")closeModal()});
if(!location.hash)location.hash="workspace";else renderRoute();




