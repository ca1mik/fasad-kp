/* Local recovery is separate from confirmed server records, per user and tab. */
(function(){
  'use strict';
  const user=window.FasadWorkspace?.userId||'local',prefix='fasad:lead-draft:v1:'+encodeURIComponent(user)+':';
  let tab,storageError='',current=null,restoring=false,last=null,ready=false;
  const instance=crypto.randomUUID();
  try{tab=sessionStorage.getItem(prefix+'tab')||crypto.randomUUID();sessionStorage.setItem(prefix+'tab',tab);}catch(error){tab=instance;storageError=error.message;}
  let key=prefix+tab,channel;
  function read(){try{const raw=localStorage.getItem(key);return raw?JSON.parse(raw):null;}catch(error){storageError=error.message;return null;}}
  last=read();
  try{
    channel=new BroadcastChannel('fasad-lead-drafts');
    channel.onmessage=event=>{
      const value=event.data;if(value.user!==user||value.tab!==tab||value.instance===instance)return;
      if(value.type==='claim'&&ready)channel.postMessage({type:'occupied',user,tab,instance,to:value.instance});
      if(value.type==='occupied'&&value.to===instance&&!ready){tab=crypto.randomUUID();key=prefix+tab;try{sessionStorage.setItem(prefix+'tab',tab);if(last)localStorage.setItem(key,JSON.stringify(last));}catch(error){storageError=error.message;}}
    };
    channel.postMessage({type:'claim',user,tab,instance});
  }catch{}
  setTimeout(()=>{ready=true;if(current&&last)write(last);},100);
  function controls(node,outsideCards=false){return [...node.querySelectorAll('input,select,textarea')].filter(i=>i.type!=='file'&&(!outsideCards||!i.closest('.lead-part-card'))&&(i.name||i.matches('[data-due-preset],[data-due-days],[data-due-kind]'))).map(i=>({name:i.name||Object.keys(i.dataset).find(k=>k.startsWith('due')),type:i.type,value:i.type==='checkbox'?i.checked:i.value}));}
  function snapshot(form){
    if(!form)return null;
    const fields=controls(form,true);
    return {version:1,fields,cards:[...form.querySelectorAll('.lead-part-card')].map(card=>({fields:controls(card),collapsed:card.classList.contains('is-collapsed')}))};
  }
  function equal(a,b){return JSON.stringify(a)===JSON.stringify(b);}
  function status(message,error=false){
    const panel=current?.querySelector('#leadDraftStatus');if(!panel)return;
    panel.querySelector('[role=status]').textContent=message;panel.querySelector('[role=status]').style.color=error?'#b52929':'';
  }
  function write(value){
    last=value;if(!ready)return;
    try{localStorage.setItem(key,JSON.stringify(value));storageError='';status('Черновик сохранён на этом компьютере · '+new Date().toLocaleTimeString('ru-RU'));}
    catch(error){storageError=error.message;status('Не удалось сохранить черновик. Скачайте копию перед закрытием: '+error.message,true);}
  }
  function flush(){if(current?.isConnected&&!restoring)write(snapshot(current));}
  function apply(node,fields){
    const inputs=[...node.querySelectorAll('input,select,textarea')];
    for(const field of fields||[]){const input=inputs.find(i=>i.name===field.name&&i.name||!i.name&&Object.keys(i.dataset).some(k=>k===field.name));if(!input)continue;if(input.type==='checkbox')input.checked=Boolean(field.value);else input.value=String(field.value??'');}
  }
  function restore(form,value){
    restoring=true;
    const list=form.querySelector('#leadPartsList');list.innerHTML=(value.cards||[]).map(()=>leadPartRow()).join('');
    apply(form,value.fields);list.querySelectorAll('.lead-part-card').forEach((card,i)=>{apply(card,value.cards[i].fields);window.FasadLeadUI?.prepareLeadCard(card);const collapsed=Boolean(value.cards[i].collapsed);card.classList.toggle('is-collapsed',collapsed);const button=card.querySelector('.lead-part-collapse');if(button){button.setAttribute('aria-expanded',String(!collapsed));button.textContent=collapsed?'Развернуть':'Свернуть';}});
    refreshLeadTotal(form);restoring=false;
  }
  function attach(){
    const form=document.querySelector('#leadForm');if(!form||form===current)return;
    current=form;
    form.insertAdjacentHTML('afterbegin','<div id="leadDraftStatus" class="form-group full form-note"><span role="status"></span> <button type="button" class="link" data-draft="download">Скачать черновик</button> · <button type="button" class="link" data-draft="discard">Удалить черновик</button></div>');
    const saved=read();if(saved){last=saved;restore(form,saved);status('Черновик восстановлен. Заявка ещё не отправлена.');}else status('Автосохранение черновика включено');
    if(storageError)status('Автосохранение недоступно: '+storageError,true);
    new MutationObserver(()=>{if(!restoring)queueMicrotask(flush);}).observe(form.querySelector('#leadPartsList'),{childList:true});
  }
  document.addEventListener('input',event=>{if(event.target.closest('#leadForm'))queueMicrotask(flush);});
  document.addEventListener('change',event=>{if(event.target.closest('#leadForm'))queueMicrotask(flush);});
  document.addEventListener('click',event=>{
    const action=event.target.closest('[data-draft]')?.dataset.draft;if(!action)return;
    if(action==='discard'&&confirm('Удалить черновик этой вкладки и очистить форму?')){
      try{localStorage.removeItem(key);last=null;current=null;renderWorkspace();}catch(error){status('Не удалось удалить черновик: '+error.message,true);}
    }
    if(action==='download'){
      const url=URL.createObjectURL(new Blob([JSON.stringify(current?snapshot(current):last,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='Черновик_заявки.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  });
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')flush();});
  window.addEventListener('pagehide',flush);window.addEventListener('beforeunload',flush);
  window.FasadDrafts={capture:snapshot,forget(){current=null;last=null;},submitted(value){
    const latest=current?.isConnected?snapshot(current):last;if(!equal(latest,value)){write(latest);return;}
    try{localStorage.removeItem(key);last=null;current=null;}catch(error){status('Заявка сохранена на сервере; не удалось удалить локальную копию: '+error.message,true);}
  }};
  new MutationObserver(attach).observe(document.querySelector('#app'),{childList:true,subtree:true});attach();
})();
