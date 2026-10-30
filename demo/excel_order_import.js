/* Convert an Excel order blank to editable positions. The file is parsed locally. */
(function(root){
  'use strict';
  const normalized=value=>String(value??'').normalize('NFKC').trim().toLocaleLowerCase('ru-RU');
  const number=value=>Number(String(value??'').replace(/\s/g,'').replace(',','.'));
  function columns(rows){
    for(let index=0;index<Math.min(rows.length,40);index++){
      const cells=(rows[index]||[]).map(normalized);
      const find=pattern=>cells.findIndex(cell=>pattern.test(cell));
      const height=find(/^(длина|высота)(,|\s|$)/);
      const width=find(/^ширина(,|\s|$)/);
      if(height<0||width<0)continue;
      const quantity=find(/^(кол-?во|количество|шт\.?)(,|\s|$)/);
      const thickness=find(/^(мм|толщ|толщина)(,|\s|$)/);
      const milling=find(/^(фрезеровка|фреза|рисунок)(,|\s|$)/);
      const color=find(/^цвет(,|\s|$)/);
      const article=find(/^(артикул|арт\.)(,|\s|$)/);
      return {start:index+1,height,width,quantity:quantity<0?width+1:quantity,
        thickness,milling,color,article};
    }
    throw Error('Не найдены заголовки «Длина» и «Ширина» на первых 40 строках');
  }
  function importRows(rows){
    if(!Array.isArray(rows)||rows.length>5000)throw Error('В файле должно быть не более 5000 строк');
    const cols=columns(rows),parts=[],warnings=[];
    let color='',thickness=16,article='',milling='';
    for(let index=cols.start;index<rows.length;index++){
      const row=rows[index]||[];
      const height=number(row[cols.height]),width=number(row[cols.width]);
      if(!(height>0&&width>0))continue;
      const qty=number(row[cols.quantity]);
      if(!Number.isSafeInteger(qty)||qty<1||qty>500){warnings.push(`Строка ${index+1}: количество должно быть от 1 до 500`);continue;}
      if(![height,width].every(value=>Number.isSafeInteger(value)&&value<=5000)){
        warnings.push(`Строка ${index+1}: размеры должны быть целыми от 1 до 5000 мм`);continue;
      }
      if(cols.color>=0&&String(row[cols.color]??'').trim())color=String(row[cols.color]).trim();
      if(cols.thickness>=0&&String(row[cols.thickness]??'').trim()){
        const parsed=number(row[cols.thickness]);
        if(!Number.isSafeInteger(parsed)||parsed<1||parsed>100){warnings.push(`Строка ${index+1}: неверная толщина`);continue;}
        thickness=parsed;
      }
      const rawMilling=String(cols.milling>=0?row[cols.milling]??'':'').trim();
      const match=rawMilling.match(/(?:^|\s)(?:арт(?:икул)?|art(?:icle)?)\.?\s*([\w-]+)/iu);
      const nextArticle=String(cols.article>=0?row[cols.article]??'':match?.[1]||'').trim();
      if(nextArticle)article=nextArticle;
      const nextMilling=rawMilling.replace(/(?:^|\s)(?:арт(?:икул)?|art(?:icle)?)\.?\s*[\w-]+/iu,'').trim();
      // Blank cells continue a group. An explicit dash clears optional milling.
      if(rawMilling)milling=/^(?:—|-|нет|без фрезеровки)$/iu.test(nextMilling)?'':nextMilling;
      parts.push({name:article?`Фасад арт. ${article}`:'Фасад',height,width,qty,
        article,color,milling,thickness,price:0,sourceRow:index+1});
    }
    if(!parts.length)throw Error(warnings[0]||'В файле не найдены позиции с размерами и количеством');
    const groups=root.FasadGroupedParts.group(parts);
    if(groups.length>500)throw Error('Слишком много разных позиций: максимум 500 групп');
    return {parts:groups.flatMap(group=>{
      const chunks=[];
      for(let remaining=group.quantity;remaining>0;remaining-=500)chunks.push({
        name:group.article?`Фасад арт. ${group.article}`:'Фасад',height:group.height,width:group.width,
        qty:Math.min(500,remaining),article:group.article,color:group.color,
        milling:group.milling,thickness:group.thickness,price:0});
      return chunks;
    }),
      sourceRows:parts.length,warnings};
  }
  const api=Object.freeze({importRows});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.FasadExcelOrderImport=api;
})(typeof window==='undefined'?globalThis:window);
