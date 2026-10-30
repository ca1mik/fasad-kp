/* Price units, deadline choices and a full-size transactional cutting editor. */
(function(){
  'use strict';
  const css=document.createElement('style');
  css.textContent=`
  .cutting-layout{grid-template-columns:minmax(300px,360px) minmax(0,1fr)!important;align-items:start}
  .cut-sheet-grid{grid-template-columns:minmax(0,1fr)!important}.cut-sheet-card header strong{font-size:14px}.cut-sheet-card header span,.cut-sheet-card header b{font-size:11px}.cut-sheet-meta{font-size:12px}.sheet-area{padding:12px!important}.sheet-svg{width:100%;max-height:none!important;display:block}.sheet-svg text{font-size:30px}.due-options{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.due-options select,.due-options input{padding:9px;border:1px solid var(--line);border-radius:8px;min-width:0}.due-options input{width:80px}.due-caption{font-size:11px;color:var(--muted)}
  .layout-editor{position:fixed;inset:12px;z-index:9000;display:flex;flex-direction:column;background:var(--bg,#f3f4f5);color:var(--text,#172033);border:1px solid var(--line);border-radius:14px;box-shadow:0 0 0 40px #101b29aa;font:14px/1.45 Arial}.layout-editor header{padding:12px 18px;background:var(--panel,#fff);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.layout-editor h2{font-size:20px;margin:0}.layout-editor button{padding:10px 13px;border:1px solid #bac5cc;border-radius:8px;background:var(--panel,#fff);color:inherit;cursor:pointer;font-size:13px}.layout-editor button:disabled{opacity:.4;cursor:not-allowed}.layout-editor .editor-primary{background:#176f5b;color:white;border-color:#176f5b}.editor-tools{display:flex;gap:9px;align-items:center;flex-wrap:wrap;padding:10px 18px;background:var(--panel,#fff);border-bottom:1px solid var(--line)}.editor-tools label{display:flex;gap:5px;align-items:center}.editor-tools input{width:85px;padding:8px;border:1px solid #bac5cc;border-radius:7px}.editor-tools select{max-width:220px;padding:8px}.editor-scroll{flex:1;overflow:auto;padding:20px;background:#dbe2e5}.editor-sheet{width:950px;max-width:none;margin:0 auto 25px;background:white;border-radius:10px;padding:14px;box-shadow:0 4px 16px #17203322}.editor-sheet>div{margin-bottom:10px;color:#172033}.editor-sheet .sheet-svg{width:100%;height:auto;touch-action:none;user-select:none}.editor-sheet .layout-piece{cursor:grab}.editor-sheet .selected rect{stroke:#16866b;stroke-width:9}.editor-ghost{pointer-events:none;fill:#24946d55;stroke:#16866b;stroke-width:8}.editor-ghost.invalid{fill:#db3c3c55;stroke:#b52323}.editor-status{padding:10px 18px;background:var(--panel,#fff);border-top:1px solid var(--line);font-size:13px}.editor-status.error{color:#b52323}.editor-help{font-size:12px;color:#667783}.editor-tools input[type=range]{width:120px}.editor-selection{font-weight:700;min-width:120px}body.editor-open{overflow:hidden}
  @media(max-width:1000px){.cutting-layout{grid-template-columns:1fr!important}.layout-editor{inset:0;border-radius:0}.editor-sheet{margin-left:0}.editor-tools{padding:8px}.editor-help{display:none}}
  @media print{.layout-editor,#openManualEditor,.due-options{display:none!important}}
  .layout-settings{margin:12px 0;padding:12px;background:var(--panel,#fff);border:1px solid var(--line,#ddd);border-radius:10px}.layout-settings summary{font-size:14px;font-weight:bold;cursor:pointer}.layout-setting-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding-top:12px}.layout-setting-fields label{display:flex;flex-direction:column;gap:5px;font-size:12px}.layout-setting-fields input,.layout-setting-fields select{width:100%;min-width:0;padding:9px;border:1px solid #bac5cc;border-radius:7px;background:var(--panel,#fff);color:inherit}.layout-setting-fields .snap-check{flex-direction:row;align-items:center}.snap-check input{width:auto}.layout-setting-fields p{grid-column:1/-1;font-size:11px;margin:0;color:#657787}.layout-settings button{margin-top:12px}.layout-editor>.layout-settings{margin:0;border-radius:0;padding:8px 18px;max-height:40vh;overflow:auto;flex-shrink:0}.layout-editor .layout-setting-fields{grid-template-columns:repeat(6,minmax(100px,1fr))}.layout-piece.snap-active>.piece{stroke:#16866b!important;stroke-width:10}.layout-piece.snap-invalid>.piece{stroke:#c22!important;stroke-width:10}.sheet-work-zone{fill:none;stroke:#527a75;stroke-width:3;stroke-dasharray:12 8;pointer-events:none}
  .form-group[hidden]{display:none!important}@media(max-width:850px){.layout-editor .layout-setting-fields{grid-template-columns:repeat(2,minmax(100px,1fr))}}@media print{.layout-settings{display:none!important}}
  `;
  document.head.append(css);
  function iso(date){return [date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-');}
  function deadline(days,working,start=new Date()){
    const result=new Date(start.getFullYear(),start.getMonth(),start.getDate());
    for(let n=0;n<days;){result.setDate(result.getDate()+1);if(!working||![0,6].includes(result.getDay()))n++;}
    return iso(result);
  }
  window.FasadDeadline={deadline};
  function settingsMarkup(spec,prefs={},editor=false){
    const r=FasadCuttingLayout.rules(spec);
    const numeric=(name,label,value,max)=>'<label>'+label+'<input data-layout-param="'+name+'" type="number" min="0" max="'+max+'" step="1" value="'+value+'" required></label>';
    return '<details class="layout-settings" '+(editor?'':'open')+'><summary>Зазоры, отступы и магнит</summary><div class="layout-setting-fields"><label>Зазор: готовый вариант<select data-layout-preset="gap"><option value="">Свой размер</option>'+[0,4,10,20,65].map(n=>'<option value="'+n+'" '+(r.gapX===n&&r.gapY===n?'selected':'')+'>'+n+' мм</option>').join('')+'</select></label><label>Край: готовый вариант<select data-layout-preset="margin"><option value="">Свой размер</option>'+[0,8,10,15,20,65].map(n=>'<option value="'+n+'" '+([r.left,r.right,r.top,r.bottom].every(v=>v===n)?'selected':'')+'>'+n+' мм со всех сторон</option>').join('')+'</select></label>'+numeric('gapX','Между деталями по X, мм',r.gapX,200)+numeric('gapY','Между деталями по Y, мм',r.gapY,200)+numeric('marginLeft','Слева, мм',r.left,1000)+numeric('marginRight','Справа, мм',r.right,1000)+numeric('marginTop','Сверху, мм',r.top,1000)+numeric('marginBottom','Снизу, мм',r.bottom,1000)+'<label class="snap-check"><input type="checkbox" data-snap="enabled" '+(prefs.enabled!==false?'checked':'')+'>Магнит включён</label><label class="snap-check"><input type="checkbox" data-snap="parts" '+(prefs.parts!==false?'checked':'')+'>К соседним деталям</label><label class="snap-check"><input type="checkbox" data-snap="edges" '+(prefs.edges!==false?'checked':'')+'>К краям рабочей зоны</label><label>Зона захвата магнита, мм<input data-snap="tolerance" type="number" min="1" max="200" step="1" value="'+(prefs.tolerance??25)+'" required></label><p>Зазор задаётся один раз между кромками двух деталей. Магнит не добавляет второй отступ. Shift при перетаскивании временно отключает магнит. Применение размеров пересчитает автоматическую карту.</p></div><button type="button" class="button" data-layout-apply>Применить параметры и пересчитать</button></details>';
  }
  function settingsValues(panel,spec){
    const next={...spec},prefs={};
    for(const input of panel.querySelectorAll('[data-layout-param],[data-snap]')){
      if(!input.checkValidity()){input.reportValidity();throw Error('Проверьте размеры и отступы');}
      if(input.dataset.layoutParam)next[input.dataset.layoutParam]=Number(input.value);
      if(input.dataset.snap)prefs[input.dataset.snap]=input.type==='checkbox'?input.checked:Number(input.value);
    }
    const r=FasadCuttingLayout.rules(next);
    if(next.sheetWidth<=r.left+r.right||next.sheetHeight<=r.top+r.bottom)throw Error('Отступы полностью перекрывают рабочую зону листа');
    next.kerf=r.gapX;next.margin=r.left;
    return {spec:next,prefs};
  }
  function enhance(){
    document.querySelectorAll('input[name=due]:not([data-deadline])').forEach(input=>{
      input.dataset.deadline='1';input.min='2020-01-01';input.max='2100-12-31';
      const group=input.closest('.form-group');if(!group)return;
      group.insertAdjacentHTML('beforeend','<div class="due-options"><select aria-label="Вариант срока" data-due-preset><option value="">Выбрать срок</option><option value="7w">7 рабочих дней</option><option value="10w">10 рабочих дней</option><option value="14w">14 рабочих дней</option><option value="21w">21 рабочий день</option><option value="14c">14 календарных дней</option><option value="30c">30 календарных дней</option></select><input aria-label="Количество дней" type="number" min="1" max="365" placeholder="Дней" data-due-days><select aria-label="Тип дней" data-due-kind><option value="w">Рабочие дни</option><option value="c">Календарные дни</option></select></div><span class="due-caption">От сегодняшней даты. Рабочие дни: пн–пт, без учёта праздников. Можно выбрать дату вручную.</span>');
    });
    document.querySelectorAll('.lead-part-card').forEach(card=>{
      const label=card.querySelector('.part-price-label'),unit=card.querySelector('[name=partUnit]');
      if(label&&unit){const text='Цена за '+(unit.value==='м²'?'м²':'штуку')+', ₽';if(label.textContent!==text)label.textContent=text;}
    });
    const maps=document.querySelector('#cuttingMaps');
    const list=document.querySelector('#partsList');
    if(list&&!list.closest('.parts-editor-viewport')){const view=document.createElement('div');view.className='parts-editor-viewport';list.before(view);const columns=list.previousElementSibling?.previousElementSibling;if(columns?.classList.contains('part-columns'))view.append(columns);view.append(list);}
    const material=document.querySelector('#materialPreset');
    if(material&&!document.querySelector('#mapLayoutSettings')){
      const order=currentCuttingOrder(),panel=document.createElement('div');panel.id='mapLayoutSettings';panel.innerHTML=settingsMarkup(order.materialSpec,order.snapSettings);material.closest('article').append(panel);
      for(const id of ['cutKerf','cutMargin'])document.querySelector('#'+id).closest('.form-group').hidden=true;
    }
    if(material&&currentCuttingOrder()?.materialSpec.mode!=='film'&&!document.querySelector('#sheetFormatPreset')){
      const order=currentCuttingOrder(),size=order.materialSpec.sheetWidth+'x'+order.materialSpec.sheetHeight;
      material.closest('.form-group').insertAdjacentHTML('afterend','<div class="form-group full"><label>Формат МДФ</label><select id="sheetFormatPreset"><option value="">Свой размер</option>'+[['2750x1250','2750 × 1250 мм'],['2440x1220','2440 × 1220 мм'],['2800x2070','2800 × 2070 мм']].map(([value,text])=>'<option value="'+value+'" '+(size===value?'selected':'')+'>'+text+'</option>').join('')+'</select><span class="due-caption">Пресет: край 8 мм, один пропил 4 мм между деталями.</span></div>');
    }
    if(maps&&!document.querySelector('#openManualEditor')){
      const button=document.createElement('button');button.id='openManualEditor';button.className='button primary';button.textContent='Ручная раскладка · на весь экран';button.onclick=()=>openEditor(currentCuttingOrder());maps.before(button);
    }
  }
  new MutationObserver(enhance).observe(document.querySelector('#app'),{childList:true,subtree:true});
  new MutationObserver(enhance).observe(document.querySelector('#modalLayer'),{childList:true,subtree:true});
  document.addEventListener('change',event=>{
    const target=event.target,group=target.closest('.form-group');
    if(target.dataset.layoutPreset){const panel=target.closest('.layout-settings'),names=target.dataset.layoutPreset==='gap'?['gapX','gapY']:['marginLeft','marginRight','marginTop','marginBottom'];if(target.value!=='')for(const name of names)panel.querySelector('[data-layout-param='+name+']').value=target.value;}
    if(target.id==='sheetFormatPreset'&&target.value){const order=currentCuttingOrder();if(order.consumedSheets){toast('После списания листов формат менять нельзя');return;}const [sheetWidth,sheetHeight]=target.value.split('x').map(Number);Object.assign(order.materialSpec,{sheetWidth,sheetHeight,margin:8,kerf:4});order.cuttingStatus='draft';saveData();renderCutting(order.id);}
    if(target.matches('[data-due-preset],[data-due-days],[data-due-kind]')){
      const preset=group.querySelector('[data-due-preset]'),days=group.querySelector('[data-due-days]'),kind=group.querySelector('[data-due-kind]');
      if(target===preset&&preset.value){days.value=parseInt(preset.value,10);kind.value=preset.value.slice(-1);}
      else preset.value='';
      if(+days.value>0&&+days.value<=365){const input=group.querySelector('[name=due]');input.value=deadline(+days.value,kind.value==='w');input.dispatchEvent(new Event('input',{bubbles:true}));}
    }
    if(target.name==='partUnit'){
      const card=target.closest('.lead-part-card');card.querySelector('[name=priceItemId]').value='';card.querySelector('[name=catalogChoice]').value='';enhance();refreshLeadTotal(target.closest('form'));
    }
    if(target.name==='catalogChoice')enhance();
  });
  document.addEventListener('click',event=>{
    if(!event.target.closest('#mapLayoutSettings [data-layout-apply]'))return;
    const order=currentCuttingOrder();if(order.consumedSheets){toast('После списания листов параметры менять нельзя');return;}
    try{
      const next=settingsValues(document.querySelector('#mapLayoutSettings'),order.materialSpec),changed=JSON.stringify(FasadCuttingLayout.rules(next.spec))!==JSON.stringify(FasadCuttingLayout.rules(order.materialSpec));
      if(changed&&order.manualLayout&&!confirm('Параметры изменятся, ручная карта будет заменена автоматической. Продолжить?'))return;
      if(changed)order.materialSpec=next.spec;order.snapSettings=next.prefs;if(changed){order.manualLayout=null;order.cuttingStatus='draft';}saveData();renderCutting(order.id);toast('Зазоры, отступы и магнит сохранены');
    }catch(error){toast(error.message);}
  });
  function openEditor(source,initialKey){
    if(!source)return;if(source.consumedSheets){toast('После списания листов раскладку менять нельзя');return;}
    const order=clone(source);let base=calculateNesting(order.parts,order.materialSpec,order.materialSpecs);
    let result=FasadCuttingLayout.apply(order,base)||base,selected=initialKey||null,zoom=1,drag=null,undo=[],redo=[],dirty=false;
    const host=document.createElement('section');host.className='layout-editor';host.setAttribute('role','dialog');host.setAttribute('aria-modal','true');host.setAttribute('aria-label','Ручная раскладка');
    host.innerHTML='<header><div><h2>Ручная раскладка · '+esc(source.id)+'</h2><span class="editor-help">Перетаскивайте между листами · R поворот · Ctrl+Z/Y · Ctrl+колесо масштаб · Esc закрыть</span></div><div><button data-edit="undo">↶ Отменить</button> <button data-edit="redo">↷ Повторить</button> <button data-edit="close">Закрыть</button> <button class="editor-primary" data-edit="save">Сохранить раскладку</button></div></header><div class="editor-tools"><span class="editor-selection">Выберите деталь</span><label>Лист <select id="editorSheet"></select></label><label>X, мм <input id="editorX" type="number" step="1"></label><label>Y, мм <input id="editorY" type="number" step="1"></label><button data-edit="apply">Применить X/Y</button><button data-edit="rotate">Повернуть 90° (R)</button><button data-edit="add">＋ Лист</button><label><input id="editorSnap" type="checkbox" checked style="width:auto">Магнит</label><label>Масштаб <input id="editorZoom" type="range" min="40" max="200" value="100"><span id="editorZoomLabel">100%</span></label><button data-edit="fit">По ширине</button></div><div class="editor-scroll"></div><div class="editor-status">Изменения применяются к заказу только кнопкой «Сохранить раскладку».</div>';
    document.body.append(host);document.body.classList.add('editor-open');
    host.querySelector('.editor-tools').insertAdjacentHTML('afterend',settingsMarkup(order.materialSpec,order.snapSettings,true));
    host.querySelector('#editorSnap').checked=order.snapSettings?.enabled!==false;
    const scroll=host.querySelector('.editor-scroll'),status=host.querySelector('.editor-status');
    function say(text,error=false){status.textContent=text;status.classList.toggle('error',error);}
    function current(){for(let i=0;i<result.sheets.length;i++){const piece=result.sheets[i].placements.find(p=>FasadCuttingLayout.key(p)===selected);if(piece)return {piece,index:i,sheet:result.sheets[i]};}return null;}
    function manual(){return order.manualLayout?.signature===FasadCuttingLayout.signature(order)?clone(order.manualLayout):{signature:FasadCuttingLayout.signature(order),positions:{},sheets:[]};}
    function state(){return clone({manualLayout:order.manualLayout||null,materialSpec:order.materialSpec,snapSettings:order.snapSettings||{}});}
    function restore(snapshot){Object.assign(order,clone(snapshot));base=calculateNesting(order.parts,order.materialSpec,order.materialSpecs);host.querySelector('.layout-settings').outerHTML=settingsMarkup(order.materialSpec,order.snapSettings,true);host.querySelector('#editorSnap').checked=order.snapSettings?.enabled!==false;}
    function remember(){undo.push(state());redo=[];dirty=true;}
    function selection(){
      const item=current();host.querySelector('.editor-selection').textContent=item?item.piece.name+' · '+item.piece.height+'×'+item.piece.width+' · #'+(item.piece.physicalNumber||item.piece.number):'Выберите деталь';
      host.querySelector('#editorSheet').innerHTML=result.sheets.map((s,i)=>'<option value="'+i+'" '+(i===item?.index?'selected':'')+'>Лист '+(i+1)+' · '+esc(s.materialName||s.spec?.name||'')+'</option>').join('');
      host.querySelector('#editorX').value=item?.piece.x??'';host.querySelector('#editorY').value=item?.piece.y??'';
      for(const name of ['apply','rotate'])host.querySelector('[data-edit='+name+']').disabled=!item;
      host.querySelector('[data-edit=undo]').disabled=!undo.length;host.querySelector('[data-edit=redo]').disabled=!redo.length;
      host.querySelectorAll('.layout-piece').forEach(g=>g.classList.toggle('selected',g.dataset.layoutKey===selected));
    }
    function draw(){
      result=FasadCuttingLayout.apply(order,base)||base;
      let summary=host.querySelector('#editorFilmTotal');
      if(order.materialSpec.mode==='film'){if(!summary){summary=document.createElement('strong');summary.id='editorFilmTotal';host.querySelector('header>div').append(summary);}summary.textContent=' · S для заказа: '+FasadRules.area(FasadRules.filmTotals(result.sheets).area)+' м²';}
      scroll.innerHTML=result.sheets.map((sheet,index)=>{
        const card=document.createElement('div');card.innerHTML=cuttingSheetSvg(sheet,sheet.spec||order.materialSpec,index,order);
        const svg=card.querySelector('svg');svg.classList.remove('live');svg.dataset.editorSheet=index;
        return '<article class="editor-sheet" style="width:'+950*zoom+'px"><div><strong>Лист '+(index+1)+' · '+esc(sheet.materialName||sheet.spec?.name||'')+'</strong> · '+sheet.placements.length+' деталей · '+(sheet.spec||order.materialSpec).sheetWidth+' × '+(sheet.spec||order.materialSpec).sheetHeight+' мм · зазор '+FasadCuttingLayout.rules(sheet.spec||order.materialSpec).gapX+' / '+FasadCuttingLayout.rules(sheet.spec||order.materialSpec).gapY+' мм (X/Y)'+(order.materialSpec.mode==='film'?' · S карты для заказа '+FasadRules.area(FasadRules.film(sheet).area)+' м²':'')+'</div>'+svg.outerHTML+'</article>';
      }).join('');selection();
    }
    function commit(patch){
      if(!selected)return false;
      try{const next=FasadCuttingLayout.revise(order,base,selected,patch);remember();order.manualLayout=next;draw();say('Позиция допустима. Изменения ещё не сохранены в заказ.');return true;}catch(error){say(error.message,true);return false;}
    }
    function snap(item,index,x,y,rotated){
      const sheet=result.sheets[index];
      const nearest=FasadCuttingLayout.nearest(item,{...sheet,spec:sheet.spec||order.materialSpec},x,y,rotated,{...order.snapSettings,enabled:host.querySelector('#editorSnap').checked&&!drag?.shift});
      const patch={sheetIndex:index,...nearest};
      try{FasadCuttingLayout.revise(order,base,selected,patch);}catch{patch.valid=false;}
      return patch;
    }
    function turn(){
      const item=current();if(!item)return;
      const spec=item.sheet.spec||order.materialSpec;
      if(item.piece.grain!==false||item.piece.no_rotation===true||spec.allowRotation===false){say('Поворот запрещён: задана текстура или запрет поворота. Проверьте настройки детали и листа.',true);return;}
      const p=item.piece,rotated=!p.rotated;
      const centered={x:p.x+(p.placedWidth-p.placedHeight)/2,y:p.y+(p.placedHeight-p.placedWidth)/2};
      const candidate=snap(p,item.index,centered.x,centered.y,rotated);
      if(candidate.valid)commit(candidate);else commit({sheetIndex:item.index,x:p.x,y:p.y,rotated});
    }
    function close(){if(dirty&&!confirm('Закрыть редактор без сохранения раскладки?'))return;host.remove();document.body.classList.remove('editor-open');document.removeEventListener('keydown',keys,true);}
    function setZoom(value){zoom=Math.min(2,Math.max(.4,value));host.querySelector('#editorZoom').value=Math.round(zoom*100);host.querySelector('#editorZoomLabel').textContent=Math.round(zoom*100)+'%';host.querySelectorAll('.editor-sheet').forEach(sheet=>sheet.style.width=950*zoom+'px');}
    host.addEventListener('click',async event=>{
      if(event.target.closest('[data-layout-apply]')){
        try{
          const next=settingsValues(host.querySelector('.layout-settings'),order.materialSpec),changed=JSON.stringify(FasadCuttingLayout.rules(next.spec))!==JSON.stringify(FasadCuttingLayout.rules(order.materialSpec));
          if(changed&&order.manualLayout&&!confirm('Пересчитать карту с новыми параметрами и заменить ручные позиции?'))return;
          remember();if(changed)order.materialSpec=next.spec;order.snapSettings=next.prefs;if(changed)order.manualLayout=null;base=calculateNesting(order.parts,order.materialSpec,order.materialSpecs);host.querySelector('#editorSnap').checked=next.prefs.enabled;draw();say('Параметры применены в редакторе. Для записи в заказ нажмите «Сохранить раскладку».');
        }catch(error){say(error.message,true);}return;
      }
      const action=event.target.closest('[data-edit]')?.dataset.edit;if(!action)return;
      if(action==='close')close();
      if(action==='save'){source.manualLayout=order.manualLayout?clone(order.manualLayout):null;source.materialSpec=clone(order.materialSpec);source.snapSettings={...order.snapSettings,enabled:host.querySelector('#editorSnap').checked};source.cuttingStatus='draft';const saved=await saveData();if(saved===false){say('Сервер не подтвердил запись. Раскладка остаётся в редакторе.',true);return;}dirty=false;close();renderCutting(source.id);toast('Ручная раскладка сохранена');}
      if(action==='apply')commit({sheetIndex:Number(host.querySelector('#editorSheet').value),x:Number(host.querySelector('#editorX').value),y:Number(host.querySelector('#editorY').value)});
      if(action==='rotate')turn();
      if(action==='fit')fit();
      if(action==='add'){
        const index=current()?.index??0,template=result.sheets[index];if(!template){say('Добавьте детали перед созданием листа',true);return;}
        const templateIndex=base.sheets.findIndex(s=>s.materialKey===template.materialKey);
        remember();const next=manual();(next.sheets||=[]).push({templateIndex});order.manualLayout=next;draw();say('Добавлен пустой лист того же материала. Перетащите деталь или задайте номер листа и X/Y.');scroll.lastElementChild?.scrollIntoView({block:'end'});
      }
      if(action==='undo'&&undo.length){redo.push(state());restore(undo.pop());dirty=true;draw();}
      if(action==='redo'&&redo.length){undo.push(state());restore(redo.pop());dirty=true;draw();}
    });
    host.querySelector('#editorZoom').oninput=event=>setZoom(+event.target.value/100);
    host.querySelector('#editorSnap').onchange=event=>{dirty=true;order.snapSettings={...order.snapSettings,enabled:event.target.checked};host.querySelector('[data-snap=enabled]').checked=event.target.checked;};
    scroll.addEventListener('wheel',event=>{if(event.ctrlKey){event.preventDefault();setZoom(zoom*(event.deltaY>0?.9:1.1));}},{passive:false});
    function point(svg,event){const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;return p.matrixTransform(svg.getScreenCTM().inverse());}
    scroll.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;const g=event.target.closest('.layout-piece');if(!g)return;
      selected=g.dataset.layoutKey;selection();const item=current(),svg=g.closest('svg'),p=point(svg,event);
      drag={id:event.pointerId,group:g,item:item.piece,dx:p.x-item.piece.x,dy:p.y-item.piece.y,candidate:null};scroll.setPointerCapture(event.pointerId);event.preventDefault();
    });
    scroll.addEventListener('pointermove',event=>{
      if(!drag||drag.id!==event.pointerId)return;
      drag.shift=event.shiftKey;
      const bounds=scroll.getBoundingClientRect();if(event.clientY>bounds.bottom-50)scroll.scrollTop+=24;else if(event.clientY<bounds.top+50)scroll.scrollTop-=24;
      host.querySelector('.editor-ghost')?.remove();drag.candidate=null;
      const svg=document.elementFromPoint(event.clientX,event.clientY)?.closest('svg[data-editor-sheet]');if(!svg||!host.contains(svg))return;
      const p=point(svg,event),index=+svg.dataset.editorSheet,candidate=snap(drag.item,index,p.x-drag.dx,p.y-drag.dy,drag.item.rotated);drag.candidate=candidate;
      const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('class','editor-ghost'+(candidate.valid?'':' invalid'));rect.setAttribute('x',candidate.x);rect.setAttribute('y',candidate.y);rect.setAttribute('width',drag.item.placedWidth);rect.setAttribute('height',drag.item.placedHeight);svg.append(rect);
      host.querySelector('#editorX').value=candidate.x;host.querySelector('#editorY').value=candidate.y;
      say(candidate.valid?(candidate.snapped?'Магнит: '+(candidate.kind==='gap'?'к соседней детали':candidate.kind==='edge'?'к краю рабочей зоны':'выравнивание')+' · ':'Допустимое положение · ')+'лист '+(index+1)+' · X '+candidate.x+', Y '+candidate.y+' мм':'Недопустимо: граница, зазор, материал или текстура. При отпускании деталь останется на месте.',!candidate.valid);
    });
    scroll.addEventListener('pointerup',event=>{if(!drag||drag.id!==event.pointerId)return;const candidate=drag.candidate;drag=null;host.querySelector('.editor-ghost')?.remove();if(candidate?.valid)commit(candidate);else selection();});
    scroll.addEventListener('pointercancel',()=>{drag=null;host.querySelector('.editor-ghost')?.remove();selection();});
    function keys(event){
      if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();if(drag){drag=null;host.querySelector('.editor-ghost')?.remove();}else close();return;}
      if(event.target.matches('input,select,textarea'))return;
      if(event.key.toLowerCase()==='r'){event.preventDefault();turn();}
      if((event.ctrlKey||event.metaKey)&&['z','y'].includes(event.key.toLowerCase())){event.preventDefault();host.querySelector('[data-edit='+((event.key.toLowerCase()==='y'||event.shiftKey)?'redo':'undo')+']').click();}
    }
    function fit(){const spec=result.sheets[0]?.spec||order.materialSpec;setZoom(Math.min((scroll.clientWidth-50)/950,(scroll.clientHeight-80)/(950*spec.sheetHeight/spec.sheetWidth)));}
    host.addEventListener('toggle',event=>{if(event.target.classList.contains('layout-settings'))fit();},true);
    host.querySelector('[data-edit=fit]').textContent='Лист целиком';
    document.addEventListener('keydown',keys,true);draw();fit();
  }
  window.FasadManualEditor={open:openEditor};
  enhance();
})();
