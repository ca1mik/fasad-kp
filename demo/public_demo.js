/* Entirely fictional examples. No backend, account or shared visitor database. */
(function(){
  'use strict';
  const key='fasad-public-test-v2';
  function seed(){
    const state=clone(initialData);state.clients=[];state.orders=[];state.leads=[];state.stock=[];state.stockMovements=[];state.depositMovements=[];
    state.factorySettings.companyName='Демонстрационный цех';
    state.workers=[{id:'DEMO-W1',name:'Тестовый технолог',role:'Технолог',initials:'ТТ',color:'green'}];
    state.machines=[{id:'DEMO-M1',name:'Учебный станок · профиль не проверен',controller:'Предпросмотр, без управляющей программы'}];
    state.priceItems=[{id:'DEMO-PRICE1',article:'DEMO-101',name:'Фасад эмаль',kind:'Эмаль',unit:'м²',price:3000},{id:'DEMO-PRICE2',article:'DEMO-102',name:'Обработка фасада',kind:'Фрезеровка',unit:'шт',price:400}];
    const base={height:720,width:400,qty:1,thickness:16,article:'DEMO-101',color:'Демо: белый',milling:'',price:3000,unit:'м²',edge:'4 стороны',grain:false};
    const add=(id,title,parts,direction='Эмаль')=>{
      const clientId='CLIENT-'+id;state.clients.push({id:clientId,name:'Тестовый заказчик '+(state.clients.length+1),initials:'ТЗ',phone:'Тестовый контакт',email:'demo@example.invalid',address:'Вымышленный адрес',city:'Демо-город',type:'Демо',demo:true});
      parts=parts.map((p,i)=>({...base,...p,id:id+'-P'+(i+1)}));
      const order={id,clientId,client:state.clients.at(-1).name,initials:'ТЗ',product:title,direction,stage:'Расчёт',status:'Новый',due:'—',amount:partsEstimate(parts),paidAmount:0,paid:0,payments:[],parts,material:false,manager:'Тестовый менеджер',materialSpec:FasadFactorySettings.snapshot(state.factorySettings,'МДФ 16 мм'),materialSpecs:materialSnapshots(state.factorySettings),cuttingStatus:'draft',manual_note:'Демонстрационный заказ. Все данные вымышлены.',demo:true};
      Object.assign(order,FasadProduction.bootstrap(order));state.orders.push(order);return order;
    };
    add('1001-Э','Обычный заказ · 8 фасадов',[{qty:6},{height:360,qty:2}]);
    add('1002-П','Повтор деталей через 120 строк',[{height:700,width:400,qty:2},...Array.from({length:120},(_,i)=>({height:200+i,width:180,qty:1})),{height:700,width:400,qty:3}],'ПВХ');
    add('1003-П','Несколько карт · цвета и толщины',[{height:2700,width:1100,qty:2},{height:2700,width:1100,color:'Демо: графит',qty:2},{height:2700,width:1100,thickness:19}],'ПВХ');
    add('1004-Ш','Смена цвета и разные толщины',[{qty:3},{height:600,color:'Демо: дуб',thickness:19,qty:2},{height:500,color:'Демо: дуб',thickness:19,qty:2}],'Шпон');
    const cad=add('1005-Ф','ЧПУ · рамка, пазы и отверстия',[{height:700,width:400,milling:'Скруглённая рамка'},{height:600,width:350,milling:'Вертикальные пазы',color:'Демо: графит'}]);
    cad.sampleKey='cad-v1';cad.parts[0].cadModel=FasadCAD.modelForPart(cad.parts[0],{template:'rounded_frame',params:{inset:40,bandWidth:8,radius:20,depth:2}});
    cad.parts[0].cadModel.holes=[{x:60,y:60,radius:2.5,depth:8,side:'front'}];
    cad.parts[1].cadModel=FasadCAD.modelForPart(cad.parts[1],{template:'vertical_grooves',params:{inset:30,grooveWidth:6,grooveCount:3,grooveSpacing:80,depth:2}});
    return normalizeData(state);
  }
  function install(){
    data=seed();localStorage.setItem('fasad-public-clean-v2','1');saveData();
  }
  if(!localStorage.getItem(key))install();
  const ribbon=document.querySelector('.demo-ribbon');
  ribbon.innerHTML='<strong>ПУБЛИЧНОЕ ДЕМО · ВЫМЫШЛЕННЫЕ ДАННЫЕ</strong><span>Изменения только в этом браузере. Не вводите реальные контакты.</span><button id="publicReset">Сбросить демо</button>';
  const fitRibbon=()=>document.documentElement.style.setProperty('--fasad-ribbon-height',Math.ceil(ribbon.getBoundingClientRect().height)+'px');
  new ResizeObserver(fitRibbon).observe(ribbon);
  document.querySelector('.sidebar-foot .user strong').textContent='Тестовый посетитель';
  document.querySelector('.sidebar-foot .user small').textContent='Локальное демо';
  const help=document.querySelector('#helpButton');help.title='О публичном демо';
  function reset(){if(!confirm('Удалить введённые в этом демо данные и восстановить вымышленные примеры?'))return;
    window.FasadDrafts?.forget();
    for(const item of Object.keys(localStorage))if(item===key||item.startsWith('fasad:public-lead-draft:'))localStorage.removeItem(item);
    install();location.hash='orders';location.reload();
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('#publicReset,#resetDemo')){event.preventDefault();event.stopImmediatePropagation();reset();}
    if(event.target.closest('#helpButton')){event.preventDefault();event.stopImmediatePropagation();openModal('Публичное демо FASAD КП','Можно изучить приложение без регистрации','<p>Все примеры вымышлены. Изменения и черновики хранятся только в вашем браузере; другие посетители их не видят. Очистка данных браузера удалит ваш ввод.</p><p>Импорт Excel выполняется на устройстве. PDF и SVG включают все карты заказа. Экспорт ЧПУ остаётся черновиком: проверенных профилей реальных станков здесь нет.</p>','Понятно');}
    if(event.target.closest('#exampleOrders')){event.preventDefault();event.stopImmediatePropagation();navigate('orders');}
  },true);
  const oldHead=pageHead;
  pageHead=function(...args){return oldHead(...args)+`<div class="public-tour panel pad"><label>Открыть пример <select id="publicExample"><option value="">Выберите сценарий</option>${data.orders.filter(o=>o.demo).map(o=>`<option value="${esc(o.id)}">${esc(o.product)}</option>`).join('')}</select></label><button class="button" data-route="workspace">Создать свою заявку</button></div>`;};
  document.addEventListener('change',event=>{if(event.target.id==='publicExample'&&event.target.value)navigate('orders',event.target.value);});
  document.head.insertAdjacentHTML('beforeend','<style>.demo-ribbon{height:auto;min-height:36px;display:flex;flex-wrap:wrap;gap:8px;padding:8px 20px;justify-content:center;align-items:center}.shell{padding-top:var(--fasad-ribbon-height,36px)}.sidebar,.topbar{top:var(--fasad-ribbon-height,36px)}.demo-ribbon span{font-size:11px;text-transform:none;letter-spacing:0}.public-tour{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}.public-tour select{max-width:100%;padding:9px;border:1px solid #ccd3dc;border-radius:8px}body{overflow-x:hidden}.modal-layer{z-index:200}@media(max-width:600px){.public-tour label,.public-tour select{width:100%}.public-tour .button{width:100%}.demo-ribbon{font-size:10px;padding:8px}.global-search{min-width:0}}@media print{.shell{padding-top:0!important}.public-tour{display:none!important}}</style>');
  fitRibbon();renderRoute();
})();
