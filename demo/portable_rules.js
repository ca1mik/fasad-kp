/* Shared, DOM-free production rules. Geometry stays in millimetres. */
(function(root){
  'use strict';
  const round2=value=>Math.round((Number(value)+Number.EPSILON)*100)/100;
  const area=value=>new Intl.NumberFormat('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2}).format(round2(value));
  const filmSpec=()=>({name:'Плёнка ПВХ',stockName:'Плёнка ПВХ',mode:'film',thickness:16,sheetWidth:3100,sheetHeight:1300,margin:150,marginLeft:150,marginRight:200,marginTop:65,marginBottom:65,kerf:65,gapX:65,gapY:65,allowRotation:true,price:0});
  function film(sheet){
    if(!sheet.placements?.length)return {occupied:0,length:0,area:0};
    const left=Number(sheet.spec?.marginLeft??sheet.spec?.margin??150);
    const occupied=Math.max(0,...sheet.placements.map(p=>Number(p.x)+Number(p.placedWidth??(p.rotated?p.width:p.height))-left));
    const length=occupied===0?0:occupied>=2500?3100:occupied+350;
    return {occupied,length,area:length*1300/1e6};
  }
  function filmTotals(sheets){
    const maps=sheets.map(film),groups=new Map();
    sheets.forEach((sheet,i)=>{const key=String(sheet.color||'Без цвета');groups.set(key,(groups.get(key)||0)+maps[i].area);});
    return {maps,area:maps.reduce((n,map)=>n+map.area,0),groups:[...groups].map(([color,area])=>({color,area}))};
  }
  function manualNumber(value){const number=String(value??'').trim();return number.length>0&&number.length<=80&&!/[<>"'\x00-\x1f]/.test(number)?number:null;}
  function orderNumber(number,direction,parts=[]){
    const base=manualNumber(number);if(!base)return null;
    // Existing literal numbers beginning with letters remain literal, as in Portable.
    if(!/^\d+(?:[ -]\d+)*(?:[ -]?[A-Za-zА-Яа-яЁё]{1,3})?$/.test(base))return base;
    const digits=base.replace(/[ -]?[A-Za-zА-Яа-яЁё]{1,3}$/,'');
    const kinds=parts.flatMap(p=>[String(p.kind||'').toLowerCase(),String(p.milling||'').toLowerCase()]);
    const suffix=direction==='ПВХ'?'П':direction==='Шпон'?'Ш':kinds.some(k=>/фрез/.test(k))?'Ф':kinds.some(k=>/мыло/.test(k))?'М':'';
    return suffix?digits+'-'+suffix:digits;
  }
  function note(record){
    if(Object.hasOwn(record,'manual_note'))return String(record.manual_note??'');
    if(Object.hasOwn(record.raw_payload||{},'manual_note'))return String(record.raw_payload.manual_note??'');
    return String(record.note??'');
  }
  root.FasadRules={round2,area,filmSpec,film,filmTotals,manualNumber,orderNumber,note};
})(typeof window==='undefined'?globalThis:window);
