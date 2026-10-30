const app=document.querySelector('#app');
const account=document.querySelector('#account');
let session=null, tab='orders', data={orders:[],price:[],dealers:[],dealerPrices:[],settings:null};
const scannedId=new URL(location.href).searchParams.get('part')||'';
if(scannedId)tab='parts';
const E=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rub=k=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format((Number(k)||0)/100);
const status={draft:'Черновик',submitted:'На проверке',confirmed:'В производстве',ready:'Готов к отгрузке'};

async function api(path,{method='GET',body}={}){
  const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(session&&method!=='GET'?{'X-CSRF-Token':session.csrf_token}:{})},body:body?JSON.stringify(body):undefined});
  const result=await response.json().catch(()=>({detail:'Ответ сервера не прочитан'}));
  if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));
  return result;
}
function message(text,error=false){const box=document.querySelector('#message');if(box){box.textContent=text;box.className=error?'error':'success';box.hidden=false;}}
function loginView(error=''){
  account.textContent='';
  app.innerHTML=`<section class="card login"><h1>Вход в Fasad</h1><p class="muted">Серверное рабочее место предприятия</p><form id="login" class="stack"><label>Имя пользователя<input name="username" autocomplete="username" required></label><label>Пароль<input name="password" type="password" autocomplete="current-password" required></label><button class="primary">Войти</button></form><p id="message" ${error?'class="error"':'hidden'}>${E(error)}</p></section>`;
}
async function refresh(){
  const role=session.user.role;
  if((role!=='admin'&&role!=='manager'&&['price','dealers','settings'].includes(tab))||(role!=='admin'&&tab==='settings'))tab='orders';
  const requests=[api('/orders'),api('/price'),api('/settings')];
  if(role==='admin'||role==='manager')requests.push(api('/dealers'),api('/dealer-prices'));
  const values=await Promise.all(requests);
  [data.orders,data.price,data.settings]=values;
  data.dealers=values[3]||[];
  data.dealerPrices=values[4]||[];
  render();
}
function shell(){
  const role=session.user.role;
  const tabs=[['orders','Заказы'],['new','Новый заказ'],['parts','Детали / сканер']];
  if(role==='admin'||role==='manager')tabs.push(['price','Прайс'],['dealers','Дилеры']);
  if(role==='admin')tabs.push(['settings','Настройки']);
  account.innerHTML=`<span>${E(session.user.username)} · ${E(role)}</span> <button id="logout" class="small">Выйти</button>`;
  app.innerHTML=`<div class="head"><div><h1>${E(data.settings.companyName)}</h1><span class="muted">Версия условий ${data.settings.version}</span>${['admin','manager'].includes(role)?'<p><a href="/work/">Открыть полное рабочее место: заявки, клиенты, CAD, раскрой и склад →</a></p>':''}</div></div><nav class="tabs">${tabs.map(([id,title])=>`<button data-tab="${id}" class="${tab===id?'active':''}">${title}</button>`).join('')}</nav><div id="view"></div><p id="message" hidden></p>`;
}
function render(){shell();if(tab==='orders')ordersView();else if(tab==='new')newOrderView();else if(tab==='parts')partsView();else if(tab==='price')priceView();else if(tab==='dealers')dealersView();else if(tab==='settings')settingsView();}
function ordersView(){
  const rows=data.orders.map(o=>`<tr><td><strong>${E(o.id)}</strong><small>${E(o.client_name)}</small></td><td>${o.parts.length} позиций · ${o.parts.reduce((n,p)=>n+p.quantity,0)} деталей</td><td>${rub(o.total_kopecks)}</td><td><span class="badge ${E(o.status)}">${status[o.status]||E(o.status)}</span></td><td>${E(o.due_date||'—')}</td><td><div class="actions"><button class="small" data-view-order="${E(o.id)}">Открыть</button>${o.status==='draft'?`<button class="small" data-submit="${E(o.id)}">Отправить</button>`:''}${o.status==='submitted'&&session.user.role!=='dealer'?`<button class="small" data-confirm="${E(o.id)}">Подтвердить</button>`:''}</div></td></tr>`).join('');
  document.querySelector('#view').innerHTML=`<section class="card"><h2>Заказы</h2><p class="muted">${data.orders.length} заказов в серверной базе</p><div class="table-wrap"><table><thead><tr><th>Номер / клиент</th><th>Объём</th><th>Сумма</th><th>Статус</th><th>Срок</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="6">Заказов пока нет</td></tr>'}</tbody></table></div></section><section id="orderDetail"></section>`;
}
async function showOrder(id){
  const o=data.orders.find(row=>row.id===id);if(!o)return;
  const parts=o.parts.map(p=>`<tr><td>${p.ordinal}</td><td>${E(p.article)} · ${E(p.name)}</td><td>${p.length_mm} × ${p.width_mm} × ${p.thickness_mm} мм</td><td>${E(p.color)}</td><td>${E(p.milling)}</td><td>${p.quantity}</td><td>${rub(p.line_kopecks)}</td></tr>`).join('');
  document.querySelector('#orderDetail').innerHTML=`<section class="card"><h2>${E(o.id)} · ${E(o.client_name)}</h2><p class="muted">Условия версии ${o.settings_version}; состояние ${status[o.status]||E(o.status)}; срок ${E(o.due_date||'не указан')}</p><div class="table-wrap"><table><thead><tr><th>№</th><th>Артикул</th><th>Размер</th><th>Цвет</th><th>Фрезеровка</th><th>Шт.</th><th>Стоимость</th></tr></thead><tbody>${parts}</tbody></table></div><p>Сумма ${rub(o.subtotal_kopecks)} · скидка ${rub(o.discount_kopecks)} · <strong>${rub(o.total_kopecks)}</strong></p><div id="productionDetail"></div></section>`;
  document.querySelector('#orderDetail').scrollIntoView({behavior:'smooth'});
  if(o.status==='confirmed'||o.status==='ready'){
    const [counts,instances]=await Promise.all([api(`/orders/${encodeURIComponent(id)}/completeness`),api(`/orders/${encodeURIComponent(id)}/instances`)]);
    const target=document.querySelector('#productionDetail');if(!target)return;
    target.innerHTML=`<h3>Комплектность</h3><p>Нужно ${counts.required} · готово ${counts.completed} · в работе ${counts.in_progress} · ожидают ${counts.queued} · брак ${counts.defects} · не хватает ${counts.missing}</p>${counts.ready&&o.status==='confirmed'&&['admin','manager'].includes(session.user.role)?`<button class="primary" data-ready="${E(id)}">Готов к отгрузке</button>`:''}<div class="table-wrap"><table><thead><tr><th>ID детали</th><th>Состояние</th><th>Этикетка</th></tr></thead><tbody>${instances.map(p=>`<tr><td>${E(p.id)}${p.replacement_for?`<small>Замена ${E(p.replacement_for)}</small>`:''}</td><td>${E(p.state)}</td><td><a href="/api/parts/${encodeURIComponent(p.id)}/label" target="_blank" rel="noopener">Печать QR</a> · <button class="small" data-open-part="${E(p.id)}">Открыть</button></td></tr>`).join('')}</tbody></table></div>`;
  }
}

function partsView(){document.querySelector('#view').innerHTML=`<section class="card"><h2>Рабочее место детали</h2><p class="muted">Сканируйте QR с этикетки или введите ID физической детали.</p><form id="partLookup" class="row"><label>ID детали<input name="partId" value="${E(scannedId)}" required></label><button class="primary">Открыть</button></form></section><section id="partDetail"></section>`;if(scannedId)showPart(scannedId).catch(err=>message(err.message,true));}
async function showPart(id){
  const part=await api(`/parts/${encodeURIComponent(id)}`);
  tab='parts';if(!document.querySelector('#partDetail'))render();
  const canWork=['admin','manager','technologist','worker'].includes(session.user.role)&&part.order_status==='confirmed';
  document.querySelector('#partDetail').innerHTML=`<section class="card"><h2>${E(part.id)}</h2><p>Заказ ${E(part.order_id)} · ${E(part.client_name)}</p><p>${E(part.part.article)} · ${part.part.length_mm} × ${part.part.width_mm} × ${part.part.thickness_mm} мм · ${E(part.part.color)} · ${E(part.part.milling)}</p><p>Этап: <strong>${E(part.current_stage||'Завершено')}</strong> · состояние <strong>${E(part.state)}</strong></p>${part.replacement_for?`<p class="notice">Переделка детали ${E(part.replacement_for)}</p>`:''}<p><a href="/api/parts/${encodeURIComponent(part.id)}/label" target="_blank" rel="noopener">Печать QR-этикетки</a></p>${canWork&&['queued','in_progress'].includes(part.state)?`<div class="actions">${part.state==='queued'?`<button class="primary" data-part-action="start" data-part-id="${E(part.id)}">Взять в работу</button>`:`<button class="primary" data-part-action="complete" data-part-id="${E(part.id)}">Этап выполнен</button>`}<button data-part-action="defect" data-part-id="${E(part.id)}">Отметить брак</button></div><label>Комментарий / причина брака<input id="partComment" maxlength="1000"></label>`:''}<h3>История</h3><div class="table-wrap"><table><thead><tr><th>Когда</th><th>Действие</th><th>Этап</th><th>Комментарий</th></tr></thead><tbody>${part.events.map(event=>`<tr><td>${E(event.at)}</td><td>${E(event.action)}</td><td>${E(event.stage_name)}</td><td>${E(event.comment)}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function partRow(){return `<div class="part-grid"><label>Артикул<select name="item" required><option value="">Выберите</option>${data.price.map(p=>`<option value="${p.id}">${E(p.article)} · ${E(p.name)} · ${rub(p.price_kopecks)}/${E(p.unit)}</option>`).join('')}</select></label><label>Длина, мм<input name="length" type="number" min="1" max="5000" required></label><label>Ширина, мм<input name="width" type="number" min="1" max="5000" required></label><label>Шт.<input name="quantity" type="number" min="1" max="10000" value="1" required></label><label>Толщ., мм<input name="thickness" type="number" min="1" max="100" value="16" required></label><label>Цвет<input name="color" placeholder="как выше"></label><label>Фрезеровка<input name="milling" placeholder="как выше"></label><button type="button" class="small" data-remove-part>Удалить</button></div>`;}
function newOrderView(){
  document.querySelector('#view').innerHTML=`<section class="card"><h2>Новый заказ</h2><p class="notice">Пустые цвет и фрезеровка берутся из предыдущей строки до следующего значения. Первая строка должна содержать оба поля. Одинаковые детали суммируются в предварительном расчёте независимо от расстояния между строками.</p><form id="orderForm" class="stack"><div class="row"><label>Клиент / объект<input name="client" required maxlength="255"></label><label>Желаемый срок<input name="due" type="date"></label>${session.user.role==='dealer'?'':`<label>Дилер<select name="dealer"><option value="">Прямой клиент</option>${data.dealers.map(d=>`<option value="${d.id}">${E(d.name)}</option>`).join('')}</select></label>`}</div><label>Комментарий<textarea name="notes" maxlength="2000" rows="2"></textarea></label><div id="parts">${partRow()}</div><div class="actions"><button type="button" data-add-part>＋ Добавить строку</button><button type="button" data-preview>Проверить расчёт</button><button class="primary">Сохранить черновик</button></div><div id="preview"></div></form></section>`;
}
function orderPayload(form){
  let color='',milling='';
  const parts=[...form.querySelectorAll('.part-grid')].map((row,index)=>{
    const get=n=>row.querySelector(`[name="${n}"]`).value.trim();
    color=get('color')||color;milling=get('milling')||milling;
    if(!color||!milling)throw Error(`Строка ${index+1}: укажите цвет и фрезеровку`);
    return {price_item_id:Number(get('item')),length_mm:Number(get('length')),width_mm:Number(get('width')),quantity:Number(get('quantity')),thickness_mm:Number(get('thickness')),color,milling};
  });
  const fd=new FormData(form);
  return {request_id:form.dataset.requestId||(form.dataset.requestId=crypto.randomUUID()),client_name:String(fd.get('client')).trim(),due_date:fd.get('due')||null,notes:String(fd.get('notes')||''),dealer_id:fd.get('dealer')?Number(fd.get('dealer')):null,parts};
}
function previewView(result){document.querySelector('#preview').innerHTML=`<section class="card"><h2>Расчёт</h2><p>${result.parts.length} строк · ${result.parts.reduce((n,p)=>n+p.quantity,0)} деталей · ${result.groups.length} групп одинаковых</p><div class="table-wrap"><table><thead><tr><th>Артикул</th><th>Размер</th><th>Толщина</th><th>Цвет</th><th>Фрезеровка</th><th>Шт.</th><th>Строки</th></tr></thead><tbody>${result.groups.map(g=>`<tr><td>${E(g.article)}</td><td>${g.length_mm} × ${g.width_mm}</td><td>${g.thickness_mm} мм</td><td>${E(g.color)}</td><td>${E(g.milling)}</td><td>${g.quantity}</td><td>${g.source_ordinals.join(', ')}</td></tr>`).join('')}</tbody></table></div><p>Позиции: ${rub(result.subtotal_kopecks)} · скидка: ${rub(result.discount_kopecks)}</p><div class="amount">Итого ${rub(result.total_kopecks)}</div><p class="muted">Технологические условия версии ${result.settings_version}. После сохранения они останутся в заказе.</p></section>`;}
function priceView(){
  document.querySelector('#view').innerHTML=`<section class="card"><h2>Прайс</h2><div class="table-wrap"><table><thead><tr><th>Артикул</th><th>Наименование</th><th>Вид работы</th><th>Ед.</th><th>Цена</th></tr></thead><tbody>${data.price.map(p=>`<tr><td>${E(p.article)}</td><td>${E(p.name)}</td><td>${E(p.kind)}</td><td>${E(p.unit)}</td><td>${rub(p.price_kopecks)}</td></tr>`).join('')}</tbody></table></div></section><section class="card"><h2>Добавить позицию</h2><form id="priceForm" class="row"><label>Артикул<input name="article" required></label><label>Название<input name="name" required></label><label>Работа<input name="kind" required></label><label>Ед.<select name="unit"><option>шт</option><option>м²</option></select></label><label>Цена, ₽<input name="rub" type="number" min="0" step="0.01" required></label><button class="primary">Сохранить</button></form></section>`;
}
function dealersView(){
  document.querySelector('#view').innerHTML=`<section class="card"><h2>Дилеры</h2><div class="table-wrap"><table><thead><tr><th>Организация</th><th>Скидка</th></tr></thead><tbody>${data.dealers.map(d=>`<tr><td>${E(d.name)}</td><td>${(d.discount_bp/100).toFixed(2)}%</td></tr>`).join('')}</tbody></table></div></section><section class="card"><h2>Индивидуальные цены</h2><p class="muted">Цена дилера заменяет обычную скидку для выбранного артикула. Старые заказы сохраняют свою цену.</p><div class="table-wrap"><table><thead><tr><th>Дилер</th><th>Артикул</th><th>Цена</th></tr></thead><tbody>${data.dealerPrices.map(p=>`<tr><td>${E(data.dealers.find(d=>d.id===p.dealer_id)?.name||p.dealer_id)}</td><td>${E(data.price.find(i=>i.id===p.price_item_id)?.article||p.price_item_id)}</td><td>${rub(p.price_kopecks)}</td></tr>`).join('')}</tbody></table></div><form id="dealerPriceForm" class="row"><label>Дилер<select name="dealer" required><option value="">Выберите</option>${data.dealers.map(d=>`<option value="${d.id}">${E(d.name)}</option>`).join('')}</select></label><label>Артикул<select name="item" required><option value="">Выберите</option>${data.price.map(p=>`<option value="${p.id}">${E(p.article)} · ${E(p.name)}</option>`).join('')}</select></label><label>Цена, ₽<input name="rub" type="number" min="0" step="0.01" required></label><button class="primary">Сохранить цену</button></form></section>${session.user.role==='admin'?`<section class="card"><h2>Новый дилер</h2><form id="dealerForm" class="row"><label>Название<input name="name" required></label><label>Скидка, %<input name="discount" type="number" min="0" max="100" step="0.01" value="0" required></label><button class="primary">Создать</button></form></section><section class="card"><h2>Учётная запись</h2><form id="userForm" class="row"><label>Логин<input name="username" required></label><label>Пароль (от 12 символов)<input name="password" type="password" minlength="12" required></label><label>Роль<select name="role"><option value="dealer">Дилер</option><option value="manager">Менеджер</option><option value="technologist">Технолог</option><option value="worker">Сотрудник</option><option value="admin">Администратор</option></select></label><label>Дилер<select name="dealer"><option value="">Без дилера</option>${data.dealers.map(d=>`<option value="${d.id}">${E(d.name)}</option>`).join('')}</select></label><button class="primary">Создать</button></form></section>`:''}`;
}
function settingsView(){
  const s=data.settings;
  document.querySelector('#view').innerHTML=`<section class="card"><h2>Настройки производства</h2><p class="muted">Новые правила действуют только для будущих заказов. Старые снимки хранятся в заказах.</p><form id="settingsForm" class="stack"><label>Компания<input name="company" value="${E(s.companyName)}" required></label>${Object.entries(s.materials).map(([key,m])=>`<fieldset data-material="${E(key)}"><legend>${E(key)}</legend><div class="row"><label>Лист, мм (длина)<input name="sheetWidth" type="number" value="${m.sheetWidth}" required></label><label>Ширина, мм<input name="sheetHeight" type="number" value="${m.sheetHeight}" required></label><label>Пропил, мм<input name="kerf" type="number" value="${m.kerf}" required></label><label>Отступ, мм<input name="margin" type="number" value="${m.margin}" required></label><label>Поворот<select name="allowRotation"><option value="true" ${m.allowRotation?'selected':''}>Да</option><option value="false" ${!m.allowRotation?'selected':''}>Нет</option></select></label></div></fieldset>`).join('')}<h3>Маршрут изготовления</h3><p class="muted">Название этапа и допустимое число деталей в день. Изменения попадут в новые заказы.</p><div id="stages">${s.stages.map(stageRow).join('')}</div><button type="button" data-add-stage>＋ Добавить этап</button><button class="primary">Сохранить версию ${s.version+1}</button></form></section>`;
}
function stageRow(stage={name:'',capacityPerDay:100}){return `<div class="row" data-stage><label>Этап<input name="stageName" value="${E(stage.name)}" required maxlength="120"></label><label>Деталей в день<input name="stageCapacity" type="number" min="1" max="10000" value="${stage.capacityPerDay}" required></label><button type="button" data-remove-stage>Удалить этап</button></div>`;}
async function boot(){try{session=await api('/me');await refresh();}catch{session=null;loginView();}}
document.addEventListener('submit',async e=>{
  const form=e.target;if(!['login','orderForm','partLookup','priceForm','dealerForm','dealerPriceForm','userForm','settingsForm'].includes(form.id))return;
  e.preventDefault();
  try{
    if(form.id==='login'){const fd=new FormData(form);session=await api('/login',{method:'POST',body:{username:fd.get('username'),password:fd.get('password')}});tab=scannedId?'parts':'orders';await refresh();return;}
    if(form.id==='orderForm'){const order=await api('/orders',{method:'POST',body:orderPayload(form)});tab='orders';await refresh();showOrder(order.id);message(`Заказ ${order.id} сохранён как черновик`);return;}
    const fd=new FormData(form);
    if(form.id==='partLookup'){await showPart(String(fd.get('partId')).trim());return;}
    if(form.id==='priceForm')await api('/price',{method:'POST',body:{article:fd.get('article'),name:fd.get('name'),kind:fd.get('kind'),unit:fd.get('unit'),price_kopecks:Math.round(Number(fd.get('rub'))*100)}});
    if(form.id==='dealerForm')await api('/dealers',{method:'POST',body:{name:fd.get('name'),discount_bp:Math.round(Number(fd.get('discount'))*100)}});
    if(form.id==='dealerPriceForm')await api(`/dealer-prices/${Number(fd.get('dealer'))}/${Number(fd.get('item'))}`,{method:'PUT',body:{price_kopecks:Math.round(Number(fd.get('rub'))*100)}});
    if(form.id==='userForm')await api('/users',{method:'POST',body:{username:fd.get('username'),password:fd.get('password'),role:fd.get('role'),dealer_id:fd.get('role')==='dealer'&&fd.get('dealer')?Number(fd.get('dealer')):null}});
    if(form.id==='settingsForm'){
      const materials={};for(const field of form.querySelectorAll('fieldset[data-material]')){const key=field.dataset.material;const old=data.settings.materials[key];materials[key]={...old,sheetWidth:Number(field.querySelector('[name="sheetWidth"]').value),sheetHeight:Number(field.querySelector('[name="sheetHeight"]').value),kerf:Number(field.querySelector('[name="kerf"]').value),margin:Number(field.querySelector('[name="margin"]').value),allowRotation:field.querySelector('[name="allowRotation"]').value==='true'};}
      const stages=[...form.querySelectorAll('[data-stage]')].map(row=>({name:row.querySelector('[name="stageName"]').value.trim(),capacityPerDay:Number(row.querySelector('[name="stageCapacity"]').value)}));
      await api('/settings',{method:'PUT',body:{expected_version:data.settings.version,companyName:fd.get('company'),materials,stages}});
    }
    await refresh();message('Сохранено');
  }catch(err){message(err.message,true);}
});
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  try{
    if(b.dataset.tab){tab=b.dataset.tab;render();return;}
    if(b.id==='logout'){await api('/logout',{method:'POST'});session=null;tab='orders';loginView();return;}
    if(b.hasAttribute('data-add-part')){document.querySelector('#parts').insertAdjacentHTML('beforeend',partRow());return;}
    if(b.hasAttribute('data-remove-part')){if(document.querySelectorAll('.part-grid').length>1)b.closest('.part-grid').remove();return;}
    if(b.hasAttribute('data-preview')){const form=document.querySelector('#orderForm');previewView(await api('/orders/preview',{method:'POST',body:orderPayload(form)}));return;}
    if(b.hasAttribute('data-add-stage')){document.querySelector('#stages').insertAdjacentHTML('beforeend',stageRow());return;}
    if(b.hasAttribute('data-remove-stage')){if(document.querySelectorAll('[data-stage]').length>1)b.closest('[data-stage]').remove();return;}
    if(b.dataset.viewOrder){showOrder(b.dataset.viewOrder);return;}
    if(b.dataset.openPart){tab='parts';render();await showPart(b.dataset.openPart);return;}
    if(b.dataset.partAction){const comment=document.querySelector('#partComment')?.value||'';await api(`/parts/${encodeURIComponent(b.dataset.partId)}/${b.dataset.partAction}`,{method:'POST',body:{request_id:crypto.randomUUID(),comment}});await showPart(b.dataset.partId);message('Операция записана в журнал');return;}
    if(b.dataset.ready){const order=data.orders.find(o=>o.id===b.dataset.ready);await api(`/orders/${encodeURIComponent(order.id)}/ready`,{method:'POST',body:{expected_version:order.version}});await refresh();await showOrder(order.id);message('Комплектный заказ готов к отгрузке');return;}
    if(b.dataset.submit||b.dataset.confirm){const id=b.dataset.submit||b.dataset.confirm;const order=data.orders.find(o=>o.id===id);await api(`/orders/${encodeURIComponent(id)}/${b.dataset.submit?'submit':'confirm'}`,{method:'POST',body:{expected_version:order.version}});await refresh();showOrder(id);message('Статус заказа обновлён');}
  }catch(err){message(err.message,true);}
});
boot();
