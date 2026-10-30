/* Loaded only by /work/. Standalone demo keeps its existing local storage. */
(async () => {
  'use strict';
  const assetVersion=new URL(document.currentScript.src).searchParams.get('v')||'';
  let session, revision=0, pending=null, saving=false, locked=false, loaded=false;
  const veil=document.createElement('div');
  veil.id='serverVeil';
  veil.style.cssText='position:fixed;inset:0;z-index:100000;background:#172d38ef;display:grid;place-items:center;color:#172d38;font:15px/1.5 Arial';
  document.body.append(veil);
  const style=document.createElement('style');
  style.textContent='#serverVeil section{background:white;padding:30px;border-radius:16px;width:min(540px,92vw)}#serverVeil input{display:block;width:100%;padding:12px;margin:8px 0 16px;border:1px solid #cad5db;border-radius:8px}#serverVeil button{margin:8px 8px 0 0;padding:11px 15px;border:0;border-radius:8px;cursor:pointer}#serverVeil h2{margin-top:0}#serverVeil [role=alert]{color:#a82929}.server-state{display:flex;gap:12px;align-items:center;flex-wrap:wrap}';
  document.head.append(style);
  function escape(value){const node=document.createElement('span');node.textContent=String(value);return node.innerHTML;}
  function show(html){veil.innerHTML='<section>'+html+'</section>';veil.style.display='grid';}
  async function request(path,method='GET',body){
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),20000);
    try{
      const response=await fetch('/api'+path,{method,signal:controller.signal,credentials:'same-origin',cache:'no-store',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'&&session?{'X-CSRF-Token':session.csrf_token}:{})},body:body?JSON.stringify(body):undefined});
      const value=await response.json();
      if(!response.ok){const err=Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));err.status=response.status;throw err;}
      return value;
    }finally{clearTimeout(timeout);}
  }
  function download(value){
    const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='fasad-workspace-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function fatal(error){
    locked=true;
    show('<h2>Сохранение остановлено</h2><p role="alert">'+escape(error.message)+'</p><p>Текущие изменения остаются в этой вкладке. Выгрузите копию перед загрузкой актуальной версии. Если связь оборвалась, проверьте результат на сервере после обновления.</p><button id="saveCopy">Скачать мои изменения</button><button id="reloadWorkspace">Загрузить с сервера</button>');
    veil.querySelector('#saveCopy').onclick=()=>download(pending||window.FasadWorkspace.initialData);
    veil.querySelector('#reloadWorkspace').onclick=()=>{if(confirm('Несохранённые изменения будут закрыты. Вы скачали копию?')){pending=null;location.reload();}};
  }
  let saveFlight=null;
  function save(value){
    if(locked)return Promise.resolve(false);
    pending=JSON.parse(JSON.stringify(value));
    if(saving)return saveFlight;
    saving=true;show('<h2>Сохраняем на сервере…</h2><p>Дождитесь подтверждения записи.</p>');
    saveFlight=(async()=>{
    try{
      while(pending){
        const snapshot=pending;
        const result=await request('/workspace','PUT',{expected_revision:revision,data:snapshot});
        revision=result.revision;
        if(pending===snapshot)pending=null;
        window.FasadWorkspace.initialData=snapshot;
      }
      const status=document.querySelector('#serverStatus');if(status)status.textContent='Сохранено на сервере · версия '+revision;
      veil.style.display='none';
      return true;
    }catch(error){fatal(error);return false;}finally{saving=false;}
    })();return saveFlight;
  }
  window.addEventListener('beforeunload',event=>{if(pending){event.preventDefault();event.returnValue='';}});
  async function script(src){await new Promise((resolve,reject)=>{const tag=document.createElement('script');tag.src=src+'?v='+encodeURIComponent(assetVersion);tag.onload=resolve;tag.onerror=()=>reject(Error('Не удалось загрузить '+src));document.body.append(tag);});}
  async function start(){
    const snapshot=await request('/workspace');revision=snapshot.revision;
    window.FasadWorkspace={initialData:snapshot.data,save,userId:String(session.user.id??session.user.username)};
    await script('app.js');
    for(const name of ['kp_ui.js','quotes.js','demo_extras.js','portable_workflow.js','product_logic.js','cutting_exports.js','lead_drafts.js'])await script(name);
    // Server mode starts with no invented employees or machine profiles.
    if(!snapshot.data){data.workers=[];data.machines=[];}
    const ribbon=document.querySelector('.demo-ribbon');
    ribbon.innerHTML='<div class="server-state"><strong>Рабочее место предприятия</strong><span id="serverStatus">Серверная база · версия '+revision+'</span></div><div><button id="workspaceExport">Экспорт</button>'+(session.user.role==='admin'?'<button id="workspaceBackup">Резервная копия</button>':'')+(session.user.role==='admin'&&!revision?'<button id="workspaceImport">Перенести данные</button>':'')+'<button id="workspaceRefresh">Обновить</button><button id="workspaceLogout">Выйти</button></div>';
    document.querySelector('.sidebar-foot .user strong').textContent=session.user.username;
    document.querySelector('.sidebar-foot .user small').textContent=session.user.role==='admin'?'Администратор':'Менеджер';
    document.querySelector('.factory-label small').textContent='Общая серверная база';
    document.querySelector('#exampleOrders').hidden=true;
    document.querySelector('#helpButton').addEventListener('click',event=>{event.stopImmediatePropagation();openModal('Рабочее место предприятия','Данные сохраняются на сервере','<p>Изменения общие для администратора и менеджеров. При конфликте скачайте свою копию и загрузите актуальную версию. CAD и карты сохраняются вместе с заказами.</p>','Понятно');},true);
    document.querySelector('#workspaceExport').onclick=()=>download(data);
    if(document.querySelector('#workspaceBackup'))document.querySelector('#workspaceBackup').onclick=async()=>{
      try{const result=await request('/workspace/backup','POST');const link=document.createElement('a');link.href='/api/workspace/backup/'+encodeURIComponent(result.name);link.download=result.name;link.click();}catch(error){alert(error.message);}
    };
    const access=document.createElement('a');access.href='/';access.textContent='Сотрудники и доступы';access.style.cssText='display:block;padding:14px;color:inherit';document.querySelector('#nav').append(access);
    document.querySelector('#workspaceRefresh').onclick=()=>location.reload();
    document.querySelector('#workspaceLogout').onclick=async()=>{try{await request('/logout','POST');location.reload();}catch(error){fatal(error);}};
    if(document.querySelector('#workspaceImport'))document.querySelector('#workspaceImport').onclick=importFile;
    loaded=true;veil.style.display='none';
    setInterval(async()=>{
      if(saving||locked||!loaded)return;
      try{const result=await request('/workspace/version');if(result.revision!==revision){document.querySelector('#serverStatus').textContent='Есть изменения другого сотрудника. Нажмите «Обновить»; сохранение старой версии будет отклонено.';}}catch(error){document.querySelector('#serverStatus').textContent=error.status===401?'Сессия истекла. Обновите страницу для входа.':'Сервер недоступен. Изменения пока не подтверждены.';}
    },10000);
  }
  function importFile(){
    const input=document.createElement('input');input.type='file';input.accept='.json,application/json';
    input.onchange=async()=>{
      try{
        const file=input.files[0];if(!file)return;if(file.size>10_000_000)throw Error('Файл превышает 10 МБ');
        const value=JSON.parse(await file.text());
        for(const key of ['leads','clients','orders','priceItems'])if(!Array.isArray(value[key]))throw Error('Неверный формат файла: '+key);
        if(!confirm('Перенести в пустую серверную базу: клиентов '+value.clients.length+', заявок '+value.leads.length+', заказов '+value.orders.length+'? Исходный файл сохранится.'))return;
        show('<h2>Переносим данные…</h2>');
        await request('/workspace/import','POST',{expected_revision:revision,data:value});location.reload();
      }catch(error){alert(error.message);veil.style.display='none';}
    };input.click();
  }
  async function login(){
    let setup=false;
    try{setup=!(await request('/setup')).configured;}catch{}
    show('<h2>'+(setup?'Первый запуск Fasad Flow':'Вход в Fasad Flow')+'</h2><p>'+(setup?'Создайте администратора предприятия. Пароль - от 12 символов.':'Общее рабочее место администратора и менеджеров.')+'</p><form id="workspaceLogin"><label>Логин<input name="username" autocomplete="username" required></label><label>Пароль<input name="password" type="password" autocomplete="'+(setup?'new-password':'current-password')+'" '+(setup?'minlength="12"':'')+' required></label><button>'+(setup?'Создать и войти':'Войти')+'</button><p role="alert" id="loginError"></p></form><a href="/">Кабинет дилера / рабочее место детали</a>');
    document.querySelector('#workspaceLogin').onsubmit=async event=>{
      event.preventDefault();const form=event.target,button=form.querySelector('button');button.disabled=true;
      try{const credentials={username:form.username.value,password:form.password.value};if(setup){await request('/setup','POST',credentials);setup=false;}session=await request('/login','POST',credentials);await start();}catch(error){if(document.querySelector('#loginError'))document.querySelector('#loginError').textContent=error.message;else fatal(error);}finally{button.disabled=false;}
    };
  }
  try{session=await request('/me');await start();}catch(error){if(error.status===401)await login();else fatal(error);}
})();
