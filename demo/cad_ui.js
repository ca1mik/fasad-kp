/* CAD editor for the local demo. Geometry and export are provided by FasadCAD. */
(function(root){
  'use strict';
  let context=null;
  const fields=[
    ['inset','Отступ от края, мм'],['bandWidth','Ширина рамки, мм'],
    ['radius','Радиус рамки, мм'],['grooveWidth','Ширина паза, мм'],
    ['grooveCount','Количество пазов'],['grooveSpacing','Шаг пазов, мм'],
    ['depth','Глубина, мм']
  ];
  const copy=value=>JSON.parse(JSON.stringify(value));
  function find(orderId,partId){
    const owner=[...data.orders,...data.leads].find(item=>item.id===orderId);
    const part=owner?.parts.find(item=>item.id===partId);
    return owner&&part?{owner,part}:null;
  }
  function formValue(value){return esc(String(value??''));}
  function preview(){
    if(!context)return;
    const warning=document.querySelector('#cadValidation'),area=document.querySelector('#cadPreview'),section=document.querySelector('#cadSection'),save=document.querySelector('#cadSave');
    if(!warning||!area)return;
    try{
      FasadCAD.validate(context.draft);
      area.innerHTML=FasadCAD.drawingSvg(context.draft,{grid:context.grid});
      const back=document.querySelector('#cadBackPreview');
      if(back)back.innerHTML=FasadCAD.drawingSvg(context.draft,{view:'back'});
      const svg=area.querySelector('svg');
      if(svg){svg.style.width=`${context.zoom*100}%`;svg.style.maxHeight='none';}
      if(section)section.innerHTML=FasadCAD.sectionSvg(context.draft);
      warning.textContent='Геометрия корректна. Вид спереди в миллиметрах.';
      warning.classList.remove('cad-error');
      save.disabled=false;
    }catch(error){
      area.innerHTML='';const back=document.querySelector('#cadBackPreview');if(back)back.innerHTML='';if(section)section.innerHTML='';warning.textContent=error.message;warning.classList.add('cad-error');save.disabled=true;
    }
    showRelevantParameters();
    renderHoleList();
  }
  function showRelevantParameters(){
    const relevant={smooth:[],frame:['inset','bandWidth','depth'],rounded_frame:['inset','bandWidth','radius','depth'],vertical_grooves:['inset','grooveWidth','grooveCount','grooveSpacing','depth'],horizontal_grooves:['inset','grooveWidth','grooveCount','grooveSpacing','depth'],diamond:['inset','depth'],custom_contour:['depth']}[context?.draft.template]||[];
    document.querySelectorAll('[data-cad-param]').forEach(input=>{input.closest('.form-group').hidden=!relevant.includes(input.dataset.cadParam);});
  }
  function renderHoleList(){
    const list=document.querySelector('#cadHoleList');
    if(!list||!context)return;
    list.innerHTML=context.draft.holes.length?context.draft.holes.map((hole,index)=>`<div class="cad-hole-row"><span>№${index+1}: X ${formValue(hole.x)} · Y ${formValue(hole.y)} · ⌀ ${formValue(Number(hole.radius)*2)} · глубина ${formValue(hole.depth)} мм</span><button type="button" class="link" data-action="cad-remove-hole-${index}">Удалить</button></div>`).join(''):'<p class="muted">Отверстий пока нет. Фрезеровку рамки можно смотреть без них.</p>';
  }
  function organizeCadPage(owner,part){
    const header=app.querySelector('.page-head'),actions=header.querySelector('.head-actions');
    header.querySelector('h1').textContent=part.name;
    header.querySelector('.lead').textContent=`${owner.id} · ${part.height} × ${part.width} × ${part.thickness||16} мм`;
    actions.querySelector('[data-action="cad-back"]').textContent=data.orders.some(item=>item.id===owner.id)?'← К заказу':'← К заявке';
    const tools=document.createElement('details');tools.className='cad-toolbar-more';tools.innerHTML='<summary class="button">Инструменты и экспорт</summary><div></div>';
    for(const name of ['cad-undo','cad-redo','cad-zoom-out','cad-zoom-in','cad-grid','cad-svg','cad-dxf','cad-print'])tools.querySelector('div').append(actions.querySelector(`[data-action="${name}"]`));
    actions.insertBefore(tools,actions.querySelector('#cadSave'));

    const layout=app.querySelector('.cad-layout'),drawing=layout.querySelector('.cad-drawing'),editor=layout.querySelector('article:not(.cad-drawing)');
    layout.prepend(drawing);layout.classList.add('cad-guided-layout');editor.classList.add('cad-editor');
    const intro=document.createElement('section');intro.className='cad-intro';
    intro.innerHTML=`<div><b>1. Осмотрите фасад</b><p>Заготовка <strong>${formValue(part.height)} × ${formValue(part.width)} × ${formValue(part.thickness||16)} мм</strong>. Оранжевая линия показывает фрезеровку; синие круги — отверстия.</p></div><div><b>2. Настройте рисунок</b><p>Шаблон и размеры фрезеровки меняют чертёж сразу. Сохраните его после проверки.</p></div><div><b>3. Проверьте сверление</b><p>Добавьте отверстие, выберите станок и посмотрите геометрию перемещений.</p></div>`;
    layout.before(intro);
    drawing.querySelector('h2').textContent='Вид с лицевой стороны';
    for(const [id,label] of [['cadBackPreview','Оборотная сторона'],['cadSection','Сечение фасада']]){
      const view=drawing.querySelector(`#${id}`),title=view.previousElementSibling,details=document.createElement('details');
      details.className='cad-view-details';details.innerHTML=`<summary>${label}</summary>`;
      title.replaceWith(details);details.append(view);
    }
    drawing.querySelector('.cad-scale-note').textContent='Размеры на чертеже указаны в миллиметрах. Для печати 1:1 этот экран не предназначен.';
    drawing.querySelector('.form-note').remove();

    editor.querySelector('h2').textContent='Рисунок и материал';
    editor.querySelector('.form-note').textContent='Выберите шаблон. На фасаде справа сразу будет видно изменение.';
    const grid=editor.querySelector('.form-grid'),advanced=document.createElement('details');
    advanced.className='cad-advanced';advanced.innerHTML='<summary>Дополнительная геометрия для технолога</summary><div class="form-grid"></div>';
    for(const id of ['cadOuterRadius','cadHoles','cadCutouts','cadPockets','cadContour'])advanced.querySelector('.form-grid').append(grid.querySelector(`#${id}`).closest('.form-group'));
    editor.insertBefore(advanced,editor.querySelector('#cadValidation'));
    const holePanel=document.createElement('section');holePanel.className='cad-hole-panel';
    holePanel.innerHTML=`<h3>Отверстия для сверления</h3><p>Координаты считаются от левого верхнего угла фасада. Добавленные отверстия появятся на чертеже.</p><div class="cad-hole-inputs"><label>X, мм<input id="cadHoleX" type="number" min="0" value="50"></label><label>Y, мм<input id="cadHoleY" type="number" min="0" value="50"></label><label>Диаметр, мм<input id="cadHoleDiameter" type="number" min="0.1" step="0.1" value="5"></label><label>Глубина, мм<input id="cadHoleDepth" type="number" min="0.1" step="0.1" value="10"></label></div><button type="button" class="button" data-action="cad-add-hole">＋ Добавить отверстие</button><div id="cadHoleList"></div>`;
    editor.insertBefore(holePanel,advanced);
    editor.querySelector('#cadValidation').textContent='Проверка геометрии';
    editor.lastElementChild.remove();

    const cam=app.querySelector('.cad-cam'),camGrid=cam.querySelector('.form-grid');
    cam.querySelector('h2').textContent='Проверка сверления для станка';
    cam.querySelector('.form-note').textContent='Это геометрический предпросмотр. Он не создаёт управляющую программу ЧПУ и не заменяет проверку технолога.';
    const machineMore=document.createElement('details');machineMore.className='cad-machine-more';machineMore.innerHTML='<summary>Рабочая зона и крепление станка</summary><div class="form-grid"></div>';
    for(const id of ['cadWorkLength','cadWorkWidth','cadWorkZ','cadSafeZ','cadClamps'])machineMore.querySelector('.form-grid').append(camGrid.querySelector(`#${id}`).closest('.form-group'));
    camGrid.after(machineMore);
    const run=cam.querySelector('[data-action="cad-cam-preview"]');run.textContent='Проверить сверление';run.classList.add('primary');
    run.insertAdjacentHTML('beforebegin','<button type="button" class="button cad-demo-settings" data-action="cad-demo-settings">Подставить параметры для просмотра</button>');
    const result=cam.querySelector('#cadCamResult'),raw=document.createElement('details');raw.className='cad-raw-result';raw.innerHTML='<summary>Технические данные расчёта</summary>';result.replaceWith(raw);raw.append(result);
  }
  function render(orderId,partId){
    const record=find(orderId,partId);
    if(!record){navigate('orders');return;}
    const {owner,part}=record;
    const model=FasadCAD.modelForPart({...part,material:owner.materialSpec?.name||''},part.cadModel,false);
    context={orderId,partId,draft:model,history:[copy(model)],historyIndex:0,zoom:1,grid:false};
    crumbs.textContent=`${owner.id} / Чертёж / ${part.name}`;
    app.innerHTML=pageHead('CAD / фасад',`${esc(part.name)} · ${esc(owner.id)}`,
      `Заготовка ${part.height} × ${part.width} × ${part.thickness||16} мм. Начало координат — левый верхний угол лицевой стороны.`,
      `<button class="button" data-action="cad-back">← К заказу</button><button class="button" data-action="cad-undo" title="Отменить изменение">↶</button><button class="button" data-action="cad-redo" title="Повторить изменение">↷</button><button class="button" data-action="cad-zoom-out" title="Уменьшить">−</button><button class="button" data-action="cad-zoom-in" title="Увеличить">＋</button><button class="button" data-action="cad-grid">Сетка 50 мм</button><button class="button" data-action="cad-svg">↓ SVG</button><button class="button" data-action="cad-dxf">↓ DXF</button><button class="button" data-action="cad-print">Печать / PDF</button><button class="button primary" id="cadSave" data-action="cad-save">Сохранить чертёж</button>`)+
      `<section class="cad-layout"><article class="panel pad"><h2>Параметры фасада</h2><p class="form-note">Шаблон остаётся связанным с этой позицией. Размеры меняются в заказе или раскрое.</p>
      <div class="form-grid"><div class="form-group full"><label for="cadTemplate">Шаблон</label><select id="cadTemplate" data-cad-field="template">${Object.entries(FasadCAD.templates).map(([key,label])=>`<option value="${key}" ${model.template===key?'selected':''}>${label}</option>`).join('')}</select></div>
      <div class="form-group"><label for="cadMaterial">Материал фасада</label><input id="cadMaterial" data-cad-field="material" value="${formValue(model.material)}"></div>
      <div class="form-group"><label for="cadGrain">Направление текстуры</label><select id="cadGrain" data-cad-field="grainDirection"><option value="none" ${model.grainDirection==='none'?'selected':''}>Без направления</option><option value="along_length" ${model.grainDirection==='along_length'?'selected':''}>Вдоль длины</option><option value="along_width" ${model.grainDirection==='along_width'?'selected':''}>Вдоль ширины</option></select></div>
      <div class="form-group"><label for="cadSide">Сторона обработки</label><select id="cadSide" data-cad-field="side"><option value="front" ${model.side==='front'?'selected':''}>Лицевая</option><option value="back" ${model.side==='back'?'selected':''}>Оборотная</option></select></div>
      <div class="form-group"><label for="cadOuterRadius">Внешний радиус, мм</label><input id="cadOuterRadius" data-cad-field="outerRadius" type="number" min="0" step="0.1" value="${formValue(model.outerRadius)}"></div>
      ${fields.map(([key,label])=>`<div class="form-group"><label for="cad-${key}">${label}</label><input id="cad-${key}" data-cad-param="${key}" type="number" min="0" step="${key==='grooveCount'?'1':'0.1'}" value="${formValue(model.params[key])}"></div>`).join('')}
      <div class="form-group full"><label for="cadHoles">Отверстия: JSON-массив {x,y,radius,depth,side}</label><textarea id="cadHoles" data-cad-array="holes" rows="3" spellcheck="false">${formValue(JSON.stringify(model.holes))}</textarea></div>
      <div class="form-group full"><label for="cadCutouts">Вырезы: JSON-массив {x,y,w,h}</label><textarea id="cadCutouts" data-cad-array="cutouts" rows="3" spellcheck="false">${formValue(JSON.stringify(model.cutouts))}</textarea></div>
      <div class="form-group full"><label for="cadPockets">Карманы: JSON-массив {x,y,w,h,depth,side}</label><textarea id="cadPockets" data-cad-array="pockets" rows="3" spellcheck="false">${formValue(JSON.stringify(model.pockets))}</textarea></div>
      <div class="form-group full"><label for="cadContour">Индивидуальный контур: JSON-массив точек {x,y}</label><textarea id="cadContour" data-cad-array="customContour" rows="3" spellcheck="false">${formValue(JSON.stringify(model.customContour))}</textarea></div></div>
      <p id="cadValidation" class="form-note" role="status"></p><p class="form-note">Слои: внешний контур, фрезеровка, отверстия, вырезы. DXF — геометрия в мм; это не управляющая программа станка.</p></article>
      <article class="panel pad cad-drawing"><h2>Вид спереди</h2><div id="cadPreview" class="cad-preview"></div><h3>Вид сзади</h3><div id="cadBackPreview" class="cad-preview"></div><h3>Сечение через середину ширины</h3><div id="cadSection" class="cad-section"></div><p class="cad-scale-note">Размеры указаны в мм. Печатный масштаб зависит от настроек браузера и принтера; этот PDF не является шаблоном 1:1.</p><p class="form-note">Виды сверху, снизу, слева и справа пока не рассчитаны.</p></article></section>
      <article class="panel pad cad-cam"><h2>CAM: предпросмотр сверления</h2><p class="form-note">Только отдельная заготовка и лицевые отверстия. Укажите данные конкретного станка и сверла. Выход — геометрический JSON без G-кода, подачи и оборотов.</p>
      <div class="form-grid"><div class="form-group"><label>Станок</label><select id="cadMachine"><option value="">Выберите станок</option>${data.machines.map(machine=>`<option value="${esc(machine.id)}">${esc(machine.name)} · ${esc(machine.controller)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Номер сверла в станке</label><input id="cadToolId" placeholder="Например, T3"></div>
      ${[['cadToolDiameter','Диаметр сверла, мм'],['cadToolLength','Рабочая длина сверла, мм'],['cadToolStep','Максимальный шаг по глубине, мм'],['cadWorkLength','Рабочая длина X, мм'],['cadWorkWidth','Рабочая ширина Y, мм'],['cadWorkZ','Ход Z, мм'],['cadSafeZ','Безопасная высота Z, мм']].map(([id,label])=>`<div class="form-group"><label for="${id}">${label}</label><input id="${id}" type="number" min="0.001" step="0.001" placeholder="Укажите ${label.toLowerCase()}"></div>`).join('')}
      <div class="form-group full"><label for="cadClamps">Зоны крепления: JSON-массив {x,y,w,h}</label><textarea id="cadClamps" rows="2" spellcheck="false">[]</textarea></div></div>
      <button class="button" data-action="cad-cam-preview">Рассчитать предпросмотр</button><p id="cadCamStatus" class="form-note" role="status"></p><pre id="cadCamResult" class="cad-cam-result"></pre></article>`;
    organizeCadPage(owner,part);
    preview();
    const area=document.querySelector('#cadPreview');
    let drag=null;
    area.addEventListener('pointerdown',event=>{if(event.button!==0)return;drag={x:event.clientX,y:event.clientY,left:area.scrollLeft,top:area.scrollTop};area.setPointerCapture(event.pointerId);});
    area.addEventListener('pointermove',event=>{if(drag){area.scrollLeft=drag.left+drag.x-event.clientX;area.scrollTop=drag.top+drag.y-event.clientY;}});
    area.addEventListener('pointerup',()=>{drag=null;});
  }
  function commit(){
    if(!context)return;
    const current=JSON.stringify(context.draft);
    if(current===JSON.stringify(context.history[context.historyIndex]))return;
    context.history=context.history.slice(0,context.historyIndex+1);
    context.history.push(copy(context.draft));context.historyIndex++;
  }
  function sync(){
    const model=context.draft;
    document.querySelectorAll('[data-cad-field]').forEach(node=>{node.value=model[node.dataset.cadField];});
    document.querySelectorAll('[data-cad-param]').forEach(node=>{node.value=model.params[node.dataset.cadParam];});
    document.querySelectorAll('[data-cad-array]').forEach(node=>{node.value=JSON.stringify(model[node.dataset.cadArray]);});
    preview();
  }
  function input(target,eventType='input'){
    if(!context)return false;
    const field=target.dataset.cadField,param=target.dataset.cadParam,array=target.dataset.cadArray;
    if(!field&&!param&&!array)return false;
    try{
      if(field){
        context.draft[field]=field==='outerRadius'?Number(target.value):target.value;
        if(field==='template'&&target.value==='custom_contour'&&!context.draft.customContour.length){
          const m=Math.min(20,context.draft.length/10,context.draft.width/10),L=context.draft.length,W=context.draft.width;
          context.draft.customContour=[{x:m,y:m},{x:L-m,y:m},{x:L-m,y:W-m},{x:m,y:W-m}];
          document.querySelector('#cadContour').value=JSON.stringify(context.draft.customContour);
        }
      }
      if(param)context.draft.params[param]=Number(target.value);
      if(array){const value=JSON.parse(target.value);if(!Array.isArray(value))throw Error('Нужен JSON-массив');context.draft[array]=value;}
      preview();
      if(eventType==='change')commit();
    }catch(error){const warning=document.querySelector('#cadValidation');warning.textContent=`${array}: ${error.message}`;warning.classList.add('cad-error');document.querySelector('#cadSave').disabled=true;}
    return true;
  }
  function download(name,body,type){
    const url=URL.createObjectURL(new Blob([body],{type}));
    const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function camPreview(){
    const selected=document.querySelector('#cadMachine').value;
    const configured=data.machines.find(machine=>machine.id===selected);
    if(!configured)throw Error('Выберите конкретный станок');
    const value=id=>Number(document.getElementById(id).value);
    const tool={type:'drill',machineId:document.getElementById('cadToolId').value.trim(),diameter:value('cadToolDiameter'),workingLength:value('cadToolLength'),maxStep:value('cadToolStep')};
    const machine={id:configured.id,name:configured.name,controller:configured.controller,workLength:value('cadWorkLength'),workWidth:value('cadWorkWidth'),workZ:value('cadWorkZ'),safeZ:value('cadSafeZ'),clamps:JSON.parse(document.getElementById('cadClamps').value)};
    const preview=FasadCAM.planDrilling(context.draft,tool,machine);
    document.getElementById('cadCamStatus').textContent=`Проверено: ${preview.operations.length} отверстий, ${preview.motions.length} геометрических перемещений. Программа станка не создана.`;
    document.getElementById('cadCamStatus').classList.remove('cad-error');
    document.getElementById('cadCamResult').textContent=JSON.stringify(preview,null,2);
  }
  function action(name){
    if(!name.startsWith('cad-'))return false;
    if(!context)return true;
    if(name==='cad-back'){navigate(data.orders.some(item=>item.id===context.orderId)?'orders':'leads',context.orderId);return true;}
    if(name==='cad-undo'||name==='cad-redo'){
      const next=context.historyIndex+(name==='cad-undo'?-1:1);
      if(next>=0&&next<context.history.length){context.historyIndex=next;context.draft=copy(context.history[next]);sync();}
      return true;
    }
    if(name==='cad-zoom-in'||name==='cad-zoom-out'){
      context.zoom=Math.max(0.5,Math.min(4,context.zoom+(name==='cad-zoom-in'?0.25:-0.25)));
      const svg=document.querySelector('#cadPreview svg');if(svg)svg.style.width=`${context.zoom*100}%`;
      return true;
    }
    if(name==='cad-grid'){context.grid=!context.grid;preview();return true;}
    try{
      if(name==='cad-demo-settings'){
        const demo={cadToolId:'T1 (демо)',cadToolDiameter:String(context.draft.holes[0]?.radius*2||5),cadToolLength:'30',cadToolStep:'3',cadWorkLength:'2800',cadWorkWidth:'2070',cadWorkZ:'100',cadSafeZ:'20'};
        document.getElementById('cadMachine').value=data.machines[0]?.id||'';
        for(const [id,value] of Object.entries(demo))document.getElementById(id).value=value;
        document.getElementById('cadCamStatus').textContent='Подставлены условные размеры для просмотра. Для реального станка укажите его фактические параметры.';
        return true;
      }
      if(name==='cad-add-hole'){
        const next=copy(context.draft);
        next.holes.push({x:Number(document.getElementById('cadHoleX').value),y:Number(document.getElementById('cadHoleY').value),radius:Number(document.getElementById('cadHoleDiameter').value)/2,depth:Number(document.getElementById('cadHoleDepth').value),side:'front'});
        FasadCAD.validate(next);context.draft=next;commit();sync();toast('Отверстие добавлено на чертёж');return true;
      }
      if(name.startsWith('cad-remove-hole-')){
        const index=Number(name.slice('cad-remove-hole-'.length));
        if(!Number.isInteger(index)||index<0||index>=context.draft.holes.length)throw Error('Отверстие не найдено');
        context.draft.holes.splice(index,1);commit();sync();return true;
      }
      FasadCAD.validate(context.draft);
      const record=find(context.orderId,context.partId);
      if(!record)throw Error('Позиция больше не найдена');
      if(name==='cad-save'){
        record.part.cadModel=JSON.parse(JSON.stringify(context.draft));
        record.part.grain=context.draft.grainDirection!=='none';
        record.owner.cuttingStatus='draft';
        saveData();toast('Чертёж сохранён у позиции заказа');
      }else if(name==='cad-svg')download(`fasad-${context.partId}.svg`,FasadCAD.drawingSvg(context.draft),'image/svg+xml;charset=utf-8');
      else if(name==='cad-dxf')download(`fasad-${context.partId}.dxf`,FasadCAD.dxf(context.draft),'application/dxf;charset=utf-8');
      else if(name==='cad-print')window.print();
      else if(name==='cad-cam-preview')camPreview();
    }catch(error){const status=document.getElementById('cadCamStatus');if(name==='cad-cam-preview'&&status){status.textContent=error.message;status.classList.add('cad-error');}else toast(error.message);}
    return true;
  }
  root.FasadCADUI={render,input,action};
})(window);
