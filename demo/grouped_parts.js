/* Global position grouping for order blanks and imported spreadsheet rows. */
(function(root){
  'use strict';
  const norm=value=>String(value??'').normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('ru-RU');
  const article=value=>norm(value).replace(/^арт(?:икул)?\.?\s*/,'').replace(/\s+/g,'');
  const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
  function group(parts,options={}){
    const carry=new Set(options.carryFields||[]),last={},groups=new Map();
    for(const part of parts||[]){
      if(!(Number(part.height)>0&&Number(part.width)>0&&Number(part.qty)>0))continue;
      const fields={article:part.article,color:part.color,milling:part.milling,thickness:part.thickness};
      for(const field of Object.keys(fields)){
        if(String(fields[field]??'').trim())last[field]=fields[field];
        else if(carry.has(field))fields[field]=last[field]??'';
      }
      const key=JSON.stringify([Number(part.height),Number(part.width),article(fields.article),
        norm(fields.color),norm(fields.milling),Number(fields.thickness||0),part.grain===true,part.no_rotation===true,
        norm(part.edge),norm(part.kind),norm(part.unit),Number(part.price||0),stable(part.cadModel||null)]);
      if(!groups.has(key))groups.set(key,{height:Number(part.height),width:Number(part.width),
        article:String(fields.article||'').trim(),color:String(fields.color||'').trim(),
        milling:String(fields.milling||'').trim(),thickness:Number(fields.thickness||0),
        grain:part.grain===true,no_rotation:part.no_rotation===true,edge:part.edge||'',kind:part.kind||'',unit:part.unit||'шт',price:Number(part.price||0),cadModel:part.cadModel||null,
        quantity:0,rows:0,areaSqm:0});
      const item=groups.get(key),quantity=Number(part.qty);
      item.quantity+=quantity;item.rows++;
      item.areaSqm+=Number(part.height)*Number(part.width)*quantity/1e6;
    }
    return [...groups.values()];
  }
  const api=Object.freeze({group});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.FasadGroupedParts=api;
})(typeof window==='undefined'?globalThis:window);
