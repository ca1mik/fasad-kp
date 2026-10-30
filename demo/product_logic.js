/* Portable workflows layered on the existing staff workspace. */
(function(){
  'use strict';
  function parent(id){return data.orders.find(o=>o.id===id)||data.leads.find(o=>o.id===id);}
  function cuttingRecord(record){
    if(!record||record.cuttingMode!=='film')return record;
    const film=record.filmCutting||={materialSpec:FasadRules.filmSpec(),cuttingStatus:'draft'};
    Object.assign(film,{id:record.id,clientId:record.clientId,client:record.client,address:record.address,product:record.product,subject:record.subject,parts:record.parts,cuttingMode:'film'});
    return film;
  }
  window.FasadProduct={cuttingRecord};
  FasadProduct.copyFilm=function(lead,created){
    const film=clone(lead.filmCutting);Object.assign(film,{id:created.id,parts:created.parts,clientId:created.clientId,client:created.client});
    if(film.manualLayout){const positions={};for(const [key,value] of Object.entries(film.manualLayout.positions||{})){const index=lead.parts.findIndex(p=>key.startsWith(p.id+'#'));if(index>=0)positions[created.parts[index].id+key.slice(lead.parts[index].id.length)]=value;}film.manualLayout.positions=positions;film.manualLayout.signature=FasadCuttingLayout.signature(film);}
    created.filmCutting=film;
  };
  const selectedMaps=new Map();
  function filmMetrics(order,result,index=selectedMaps.get(order.id)||0){
    index=Math.max(0,Math.min(index,result.sheets.length-1));selectedMaps.set(order.id,index);
    const sheet=result.sheets[index],spec=sheet?.spec||order.materialSpec,r=FasadCuttingLayout.rules(spec),map=sheet?FasadRules.film(sheet):{occupied:0,area:0};
    return `<label>Выбранная карта <select id="filmMapSelect">${result.sheets.map((s,i)=>`<option value="${i}" ${i===index?'selected':''}>Карта ${i+1} · ${esc(s.color||'Без цвета')}</option>`).join('')}</select></label><section class="stats" style="grid-template-columns:repeat(auto-fit,minmax(145px,1fr));margin:12px 0">${stat('Лист',`${spec.sheetWidth} × ${spec.sheetHeight}`,'мм')}${stat('Рабочая зона',`${spec.sheetWidth-r.left-r.right} × ${spec.sheetHeight-r.top-r.bottom}`,'мм')}${stat('Длина по деталям',`${map.occupied} мм`,'выбранная карта')}${stat('S карты для заказа',`${FasadRules.area(map.area)} м²`,'выбранная карта')}${stat('S для заказа',`${FasadRules.area(FasadRules.filmTotals(result.sheets).area)} м²`,'все карты и цвета')}</section>`;
  }
  const oldResults=cuttingResultsMarkup;
  cuttingResultsMarkup=function(order,result){
    let html=oldResults(order,result);
    if(order.materialSpec.mode!=='film')return html;
    const totals=FasadRules.filmTotals(result.sheets),colors=[...new Set(result.sheets.map(s=>s.color||'Без цвета'))];
    html=`<div id="filmMetrics">${filmMetrics(order,result)}</div>`+html;
    html+=`<article class="panel pad" id="filmProcurement"><h3>S для заказа — плёнка</h3><p>Ширина 1,30 м. До 2500 мм: занятая длина + 350 мм. От 2500 мм: 3100 мм.</p><label>Показать карты цвета <select id="filmColorFilter"><option value="">Все цвета</option>${colors.map(c=>`<option>${esc(c)}</option>`).join('')}</select></label><div class="table-wrap"><table class="data-table"><thead><tr><th>Карта</th><th>Цвет</th><th>Длина по деталям</th><th>Длина для заказа</th><th>S для заказа, м²</th></tr></thead><tbody>${totals.maps.map((map,i)=>`<tr data-film-color="${esc(result.sheets[i].color||'Без цвета')}"><td>${i+1}</td><td>${esc(result.sheets[i].color||'Без цвета')}</td><td>${map.occupied} мм</td><td>${map.length} мм</td><td>${FasadRules.area(map.area)}</td></tr>`).join('')}</tbody><tfoot><tr><td colspan="4">Все карты заказа, все цвета</td><td id="filmOrderArea">${FasadRules.area(totals.area)}</td></tr></tfoot></table></div><h4>Заявка поставщику</h4>${totals.groups.map(g=>`<p>${esc(g.color)}: <strong>${FasadRules.area(g.area)} м²</strong></p>`).join('')}<button class="button" data-product="film-xlsx" data-id="${esc(order.id)}">Скачать заявку поставщику XLSX</button></article>`;
    return html;
  };
  const oldSheet=cuttingSheetSvg;
  cuttingSheetSvg=function(sheet,spec,index,owner){
    const html=oldSheet(sheet,spec,index,owner);
    if((sheet.spec||spec).mode!=='film')return html;
    const map=FasadRules.film(sheet);
    return html.replace('</article>',`<div class="panel-body"><b>S для заказа: ${FasadRules.area(map.area)} м²</b> · длина по деталям ${map.occupied} мм · к заказу ${map.length} мм</div></article>`);
  };
  const oldCutting=renderCutting;
  renderCutting=function(id){
    oldCutting(id);const record=parent(app.dataset.cuttingOrder);if(!record)return;
    const film=record.cuttingMode==='film';
    app.querySelector('.cut-flow')?.insertAdjacentHTML('beforebegin',`<div class="panel pad"><label>Расчёт материала <select id="cuttingMaterialMode"><option value="mdf" ${!film?'selected':''}>МДФ — распил и склад</option><option value="film" ${film?'selected':''}>Плёнка — раскладка и S для заказа</option></select></label></div>`);
    if(film){
      app.querySelector('#materialPreset').closest('.form-group').hidden=true;
      for(const id of ['cutSheetWidth','cutSheetHeight']){const input=app.querySelector('#'+id);input.readOnly=true;}
      app.querySelector('#releaseCutting').textContent='Заявка поставщику — под картами';
      app.querySelector('#releaseNote').textContent='Площадь плёнки рассчитана по всем картам и цветам. Распил и резерв МДФ выполняются в режиме МДФ.';
    }
  };
  renderers.cutting=renderCutting;
  const oldNewOrder=newOrderModal;
  newOrderModal=function(prefill=''){
    oldNewOrder(prefill);const form=document.querySelector('#newOrderForm');if(!form)return;
    const lead=typeof prefill==='object'?prefill:null;
    form.insertAdjacentHTML('afterbegin',`<div class="form-group full"><label>Номер заказа · ручной ввод<input name="orderNumber" maxlength="80" value="${esc(lead?.id||'')}" required></label><small>При создании заказа: ПВХ — П, шпон — Ш, фрезеровка — Ф, мыло — М. Для эмали без обработки — без буквы.</small></div>`);
    form.insertAdjacentHTML('beforeend',`<div class="form-group full"><label>Комментарий<textarea name="manual_note">${esc(lead?FasadRules.note(lead):'')}</textarea></label></div>`);
  };
  const oldPartRow=leadPartRow;
  leadPartRow=function(part={}){return oldPartRow(part).replace('<details class="lead-part-options">',`<p class="part-area-label">S деталей: <strong>${FasadRules.area(Number(part.height||0)*Number(part.width||0)*Number(part.qty??1)/1e6)}</strong> м²</p><details class="lead-part-options">`);};
  const oldLead=renderLead;
  renderLead=function(id){oldLead(id);const lead=data.leads.find(o=>o.id===id),table=app.querySelector('.table-wrap .data-table');if(!lead||!table)return;table.tHead.rows[0].insertCell(4).outerHTML='<th>S деталей, м²</th>';lead.parts.forEach((part,i)=>table.tBodies[0].rows[i].insertCell(4).textContent=FasadRules.area(part.height*part.width*part.qty/1e6));};
  function orderInfo(order){
    const client=data.clients.find(c=>c.id===order.clientId);
    return `Клиент: ${order.client}\nТелефон: ${client?.phone||'—'}\nАдрес: ${order.address||client?.address||'—'}\nРазмеры:\n`+order.parts.map(p=>`${p.height}×${p.width} — ${p.qty} шт., ${p.thickness||16} мм, ${p.color||'без цвета'}`).join('\n')+`\nВсего деталей: ${orderPartCount(order)}\nS деталей: ${FasadRules.area(orderPartArea(order))} м²\nРасчёт: ${money(order.amount)}`;
  }
  const oldOrder=renderOrder;
  renderOrder=function(id){
    oldOrder(id);const order=data.orders.find(o=>o.id===id);if(!order)return;
    app.querySelector('.order-actions')?.insertAdjacentHTML('beforeend',`<button class="button" data-product="blank-xlsx" data-id="${esc(id)}">Бланк XLSX</button>`);
    const stack=app.querySelector('.grid.asym>.stack');
    stack?.insertAdjacentHTML('beforeend',`<article class="panel pad"><h3>Информация по заказу</h3><p style="white-space:pre-wrap">${esc(orderInfo(order))}</p><h3>Комментарий</h3><p id="orderCustomerNote" style="white-space:pre-wrap">${esc(FasadRules.note(order))||'—'}</p><button class="button" data-product="edit-note" data-id="${esc(id)}">Изменить комментарий</button></article>`);
    const table=app.querySelector('.table-wrap .data-table');
    if(table){table.tHead.rows[0].insertCell(4).outerHTML='<th>S деталей, м²</th>';order.parts.forEach((part,i)=>table.tBodies[0].rows[i].insertCell(4).textContent=FasadRules.area(part.height*part.width*part.qty/1e6));table.tFoot.rows[0].cells[0].colSpan++;}
  };
  function blankRows(order){
    const client=data.clients.find(c=>c.id===order.clientId);
    const rows=[['Бланк заказа',order.id],['Клиент',order.client],['Телефон',client?.phone||''],['Адрес',order.address||client?.address||''],['Срок',order.dueDate||order.due||''],[],['№','Наименование','Длина, мм','Ширина, мм','Количество','S, м²','Толщина, мм','Фрезеровка','Цвет']];
    order.parts.forEach((p,i)=>rows.push([i+1,p.name,p.height,p.width,p.qty,p.height*p.width*p.qty/1e6,p.thickness||16,p.milling||'',p.color||'']));
    rows.push(['Итого','','','',orderPartCount(order),orderPartArea(order)],['Сумма, ₽',order.amount],[],['Комментарий',FasadRules.note(order)],[],['Размеры проверил __________________'],['Заказ принял __________________']);
    return rows;
  }
  function workbook(rows,name,areaColumn=null,start=0,end=0){
    const ws=XLSX.utils.aoa_to_sheet(rows);ws['!cols']=[{wch:15},{wch:32},{wch:15},{wch:15},{wch:14},{wch:16},{wch:16},{wch:24},{wch:26}];
    for(let i=start;i<=end;i++){if(areaColumn===null)break;const cell=ws[XLSX.utils.encode_cell({r:i,c:areaColumn})];if(cell)cell.z='0.00';}
    const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,name);return {wb,ws};
  }
  window.FasadProduct.blankWorkbook=function(order){
    const rows=blankRows(order),{wb,ws}=workbook(rows,'Бланк заказа',5,7,7+order.parts.length),noteIndex=rows.length-4;
    ws['!merges']=[{s:{r:noteIndex,c:1},e:{r:noteIndex,c:8}}];
    ws['!rows']=rows.map(()=>({hpt:22}));
    const text=FasadRules.note(order),lines=text.split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil(line.length/95)),0);
    ws['!rows'][noteIndex]={hpt:Math.max(32,lines*16)};
    ws[XLSX.utils.encode_cell({r:noteIndex,c:1})].s={alignment:{wrapText:true,vertical:'top'}};
    return wb;
  };
  // SheetJS CE preserves number formats and row heights, but drops alignment on
  // write. Add one OOXML cell style so Excel really wraps long customer notes.
  FasadProduct.blankFile=function(order){
    const zip=XLSX.CFB.read(new Uint8Array(XLSX.write(FasadProduct.blankWorkbook(order),{bookType:'xlsx',type:'array'})),{type:'array'});
    const decoder=new TextDecoder(),encoder=new TextEncoder();
    const styles=XLSX.CFB.find(zip,'/xl/styles.xml'),sheet=XLSX.CFB.find(zip,'/xl/worksheets/sheet1.xml');
    let xml=decoder.decode(styles.content),index=0;
    xml=xml.replace(/<cellXfs count="(\d+)">([\s\S]*?)<\/cellXfs>/,(_,count,body)=>{index=Number(count);return `<cellXfs count="${index+1}">${body}<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>`;});
    const address='B'+(blankRows(order).length-3);
    const sheetXml=decoder.decode(sheet.content).replace(new RegExp('<c r="'+address+'"([^>]*)>'),(_,attrs)=>`<c r="${address}"${attrs.replace(/ s="\d+"/,'')} s="${index}">`);
    XLSX.CFB.utils.cfb_add(zip,'xl/styles.xml',encoder.encode(xml));XLSX.CFB.utils.cfb_add(zip,'xl/worksheets/sheet1.xml',encoder.encode(sheetXml));
    return XLSX.CFB.write(zip,{type:'array',fileType:'zip'});
  };
  printOrder=function(order){
    const w=window.open('','_blank');if(!w){toast('Разрешите открытие окна печати');return;}
    const rows=blankRows(order),header=rows[6];
    w.document.write(`<!doctype html><html lang="ru"><meta charset="utf-8"><title>Бланк ${esc(order.id)}</title><style>body{font:13px Arial;color:#172033;margin:25px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #999;padding:6px}p{white-space:pre-wrap}h1{font-size:22px}</style><h1>Бланк заказа ${esc(order.id)}</h1>${rows.slice(1,5).map(row=>`<p>${esc(row[0])}: ${esc(row[1])}</p>`).join('')}<table><thead><tr>${header.map(v=>`<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${rows.slice(7,7+order.parts.length).map(row=>`<tr>${row.map((v,i)=>`<td>${esc(i===5?FasadRules.area(v):v)}</td>`).join('')}</tr>`).join('')}</tbody></table><p>Всего: ${orderPartCount(order)} деталей · S ${FasadRules.area(orderPartArea(order))} м² · ${money(order.amount)}</p><h3>Комментарий</h3><p>${esc(FasadRules.note(order))}</p><p>Размеры проверил __________________</p><p>Заказ принял __________________</p></html>`);
    w.document.close();w.focus();w.print();
  };
  document.addEventListener('change',async event=>{
    if(event.target.id==='cuttingMaterialMode'){const record=parent(app.dataset.cuttingOrder);record.cuttingMode=event.target.value;cuttingRecord(record);await saveData();renderCutting(record.id);}
    if(event.target.id==='filmColorFilter'){
      const value=event.target.value,result=calculateOrderNesting(currentCuttingOrder());
      app.querySelectorAll('#cuttingMaps .cut-sheet-card').forEach((card,i)=>card.hidden=Boolean(value&&(result.sheets[i].color||'Без цвета')!==value));
      app.querySelectorAll('[data-film-color]').forEach(row=>row.hidden=Boolean(value&&row.dataset.filmColor!==value));
      const selected=value?result.sheets.findIndex(sheet=>(sheet.color||'Без цвета')===value):selectedMaps.get(currentCuttingOrder().id)||0;
      document.querySelector('#filmMetrics').innerHTML=filmMetrics(currentCuttingOrder(),result,Math.max(0,selected));
    }
    if(event.target.id==='filmMapSelect'){const order=currentCuttingOrder();document.querySelector('#filmMetrics').innerHTML=filmMetrics(order,calculateOrderNesting(order),Number(event.target.value));}
    if(event.target.name==='catalogChoice'){const card=event.target.closest('.lead-part-card'),item=data.priceItems.find(p=>p.id===event.target.value);if(card&&item)card.querySelector('[name=partKind]').value=item.kind;}
  });
  document.addEventListener('input',event=>{
    const card=event.target.closest('.lead-part-card'),label=card?.querySelector('.part-area-label strong');if(!label)return;
    const read=name=>Number(card.querySelector('[name='+name+']')?.value||0);
    label.textContent=FasadRules.area(read('partHeight')*read('partWidth')*read('partQty')/1e6);
  });
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-product]');if(!button)return;
    const record=parent(button.dataset.id),action=button.dataset.product;
    if(action==='blank-xlsx'){
      const url=URL.createObjectURL(new Blob([FasadProduct.blankFile(record)],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})),link=document.createElement('a');link.href=url;link.download=`Заказ_${record.id.replace(/[\\/:*?"<>|]/g,'_')}.xlsx`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    if(action==='film-xlsx'){
      const film=record.filmCutting,totals=FasadRules.filmTotals(calculateOrderNesting(film).sheets);
      const rows=[['Заявка поставщику плёнки',record.id],['Цвет','S для заказа, м²'],...totals.groups.map(g=>[g.color,g.area]),['Итого',totals.area]];
      const {wb}=workbook(rows,'Плёнка',1,2,rows.length-1);XLSX.writeFile(wb,`Плёнка_${record.id.replace(/[\\/:*?"<>|]/g,'_')}.xlsx`);
    }
    if(action==='edit-note')openModal('Комментарий заказа','Только пожелания клиента, без сводки размеров',`<form id="orderNoteForm" data-id="${esc(record.id)}"><textarea name="manual_note" rows="8" style="width:100%">${esc(FasadRules.note(record))}</textarea></form>`,'Сохранить комментарий');
  });
  document.addEventListener('click',async event=>{
    const form=document.querySelector('#orderNoteForm');if(!form||!event.target.closest('[data-modal-save]'))return;
    event.stopImmediatePropagation();event.preventDefault();const record=parent(form.dataset.id),before=record.manual_note;record.manual_note=form.manual_note.value;
    const saved=await saveData();if(saved===false){record.manual_note=before;return;}closeModal();renderOrder(record.id);
  },true);
  // Restore the active screen after installing the render wrappers.
  renderRoute();
})();
