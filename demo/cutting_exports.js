/* All-sheet exports derive from the same current nesting as the screen. */
(function(){
  'use strict';
  function allMaps(){
    const order=currentCuttingOrder();if(!order)throw Error('Сначала откройте раскрой заказа');
    const result=calculateOrderNesting(order);if(!result.sheets.length)throw Error('Нет карт для экспорта');
    if(result.oversized.length)toast('Часть деталей не помещается. Предупреждение включено в экспорт.');
    return {order,result};
  }
  function saveFile(name,bytes,type){const url=URL.createObjectURL(new Blob([bytes],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
  function safeId(value){return String(value).replace(/[\\/:*?"<>|]/g,'_');}
  const style='<style>.board{fill:#eadbb6;stroke:#8b7147;stroke-width:3}.piece{fill:#fff5d7;stroke:#785f39;stroke-width:3}.sheet-work-zone{fill:none;stroke:#517d77;stroke-width:2;stroke-dasharray:12 8}.layout-piece text{fill:#172033}text{font-family:Arial,sans-serif}</style>';
  function sheetSvg(order,sheet,index,result){
    const holder=document.createElement('div');holder.innerHTML=cuttingSheetSvg(sheet,sheet.spec,index,order);
    const svg=holder.querySelector('svg'),spec=sheet.spec||order.materialSpec;
    // Draw map and context in one image so the downloadable PDF includes labels.
    const width=1800,header=180,height=header+width*spec.sheetHeight/spec.sheetWidth;
    const title=`Заказ ${order.id} · Лист ${index+1} из ${result.sheets.length}`;
    const info=`${sheet.materialName||spec.name} · ${sheet.thickness||spec.thickness} мм · ${sheet.color||'без цвета'} · ${sheet.placements.length} деталей`;
    const area=spec.mode==='film'?`S карты для заказа ${FasadRules.area(FasadRules.film(sheet).area)} м² · S всего заказа ${FasadRules.area(FasadRules.filmTotals(result.sheets).area)} м²`:'';
    const xml=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${style}<rect width="100%" height="100%" fill="white"/><text x="24" y="36" font-size="28" font-weight="bold">${esc(title)}</text><text x="24" y="72" font-size="23">${esc(info)}</text><text x="24" y="108" font-size="21">${esc(order.client||'')} · ${spec.sheetWidth} × ${spec.sheetHeight} мм</text><text x="24" y="140" font-size="20">${esc(area||`Размещено ${result.sheets.reduce((n,s)=>n+s.placements.length,0)} из ${result.parts} деталей`)}${result.oversized.length?' · НЕ РАЗМЕЩЕНО: '+result.oversized.length:''}</text><svg x="0" y="${header}" width="${width}" height="${height-header}" viewBox="0 0 ${spec.sheetWidth} ${spec.sheetHeight}">${svg.innerHTML}</svg></svg>`;
    return {xml,width,height};
  }
  function pdf(images){
    const encoder=new TextEncoder(),chunks=[],offsets=[0];let size=0;
    const add=value=>{const bytes=typeof value==='string'?encoder.encode(value):value;chunks.push(bytes);size+=bytes.length;};
    const object=(id,body)=>{offsets[id]=size;add(id+' 0 obj\n');add(body);add('\nendobj\n');};
    add('%PDF-1.4\n% FASAD all maps\n');object(1,'<< /Type /Catalog /Pages 2 0 R >>');
    object(2,`<< /Type /Pages /Count ${images.length} /Kids [${images.map((_,i)=>(3+i*3)+' 0 R').join(' ')}] >>`);
    images.forEach((image,i)=>{
      const page=3+i*3,content=page+1,imageId=page+2,scale=Math.min(802/image.width,555/image.height),w=image.width*scale,h=image.height*scale;
      const commands=`q ${w.toFixed(3)} 0 0 ${h.toFixed(3)} ${((842-w)/2).toFixed(3)} ${((595-h)/2).toFixed(3)} cm /Im0 Do Q\n`;
      object(page,`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /XObject << /Im0 ${imageId} 0 R >> >> /Contents ${content} 0 R >>`);
      object(content,`<< /Length ${encoder.encode(commands).length} >>\nstream\n${commands}endstream`);
      offsets[imageId]=size;add(`${imageId} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${image.width} /Height ${image.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${image.bytes.length} >>\nstream\n`);add(image.bytes);add('\nendstream\nendobj\n');
    });
    const start=size,count=3+images.length*3;add(`xref\n0 ${count}\n0000000000 65535 f \n`);
    for(let i=1;i<count;i++)add(String(offsets[i]).padStart(10,'0')+' 00000 n \n');
    add(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${start}\n%%EOF`);return new Blob(chunks,{type:'application/pdf'});
  }
  async function raster(map){
    const image=new Image(),url=URL.createObjectURL(new Blob([map.xml],{type:'image/svg+xml;charset=utf-8'}));
    try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Не удалось подготовить карту для PDF'));image.src=url;});
      const canvas=document.createElement('canvas');canvas.width=map.width;canvas.height=Math.ceil(map.height);const context=canvas.getContext('2d');context.fillStyle='white';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,0,0,canvas.width,canvas.height);
      return {width:canvas.width,height:canvas.height,bytes:Uint8Array.from(atob(canvas.toDataURL('image/jpeg',.96).split(',')[1]),char=>char.charCodeAt(0))};
    }finally{URL.revokeObjectURL(url);}
  }
  const oldRender=renderCutting;
  renderCutting=function(id){oldRender(id);if(!currentCuttingOrder())return;app.querySelector('.page-head .head-actions')?.insertAdjacentHTML('beforeend','<button class="button" data-cut-export="pdf">Скачать PDF · все карты</button><button class="button" data-cut-export="svg">Скачать SVG · все карты</button>');};
  renderers.cutting=renderCutting;
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-cut-export]');if(!button)return;button.disabled=true;
    try{
      const {order,result}=allMaps(),maps=result.sheets.map((sheet,i)=>sheetSvg(order,sheet,i,result)),name=`Раскрой_${safeId(order.id)}_${order.materialSpec.mode==='film'?'плёнка':'МДФ'}`;
      if(button.dataset.cutExport==='svg'){
        let y=0;const content=maps.map(map=>{const start=y;y+=map.height+30;return `<svg x="0" y="${start}" width="${map.width}" height="${map.height}" viewBox="0 0 ${map.width} ${map.height}">${map.xml.replace(/^<svg[^>]*>/,'').replace(/<\/svg>$/,'')}</svg>`;}).join('');
        saveFile(name+'.svg',`<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="${y}" viewBox="0 0 1800 ${y}">${content}</svg>`,'image/svg+xml;charset=utf-8');
      }else{const images=[];for(const map of maps)images.push(await raster(map));saveFile(name+'.pdf',pdf(images),'application/pdf');}
      toast(`Экспортировано карт: ${maps.length}`);
    }catch(error){toast(error.message);}finally{button.disabled=false;}
  });
  renderRoute();
})();
