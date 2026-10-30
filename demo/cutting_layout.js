/* Manual adjustments for rectangular blanks. Coordinates stay in mm. */
(function(root){
  'use strict';
  const key=placement=>`${placement.id}#${placement.number}`;
  function rules(spec){
    return {left:Number(spec.marginLeft??spec.margin??0),right:Number(spec.marginRight??spec.margin??0),top:Number(spec.marginTop??spec.margin??0),bottom:Number(spec.marginBottom??spec.margin??0),gapX:Number(spec.gapX??spec.kerf??0),gapY:Number(spec.gapY??spec.kerf??0)};
  }
  function check(part,sheet,x,y,rotated,spec=sheet.spec){
    const r=rules(spec),width=rotated?part.width:part.height,height=rotated?part.height:part.width;
    if(![x,y,width,height,...Object.values(r)].every(Number.isFinite)||x<r.left||y<r.top||x+width>spec.sheetWidth-r.right||y+height>spec.sheetHeight-r.bottom)return false;
    if(rotated&&(part.grain!==false||part.no_rotation===true||spec.allowRotation===false))return false;
    return !(sheet.placements||[]).some(other=>key(other)!==key(part)&&!(x+width+r.gapX<=other.x||other.x+other.placedWidth+r.gapX<=x||y+height+r.gapY<=other.y||other.y+other.placedHeight+r.gapY<=y));
  }
  // Same candidate geometry as Portable: one shared gap, nearest valid edge,
  // neighbour side or alignment, with gap candidates preferred over alignment.
  function nearest(part,sheet,x,y,rotated,options={}){
    const spec=sheet.spec,r=rules(spec),rawX=Math.round(x),rawY=Math.round(y),tolerance=Number(options.tolerance??25);
    const width=rotated?part.width:part.height,height=rotated?part.height:part.width;
    const xs=[],ys=[];
    if(options.edges!==false){xs.push({value:r.left,kind:'edge'},{value:spec.sheetWidth-r.right-width,kind:'edge'});ys.push({value:r.top,kind:'edge'},{value:spec.sheetHeight-r.bottom-height,kind:'edge'});}
    if(options.parts!==false)for(const other of sheet.placements||[]){
      if(key(other)===key(part))continue;
      if(rawY<other.y+other.placedHeight+tolerance&&rawY+height>other.y-tolerance){
        xs.push({value:other.x+other.placedWidth+r.gapX,kind:'gap'},{value:other.x-width-r.gapX,kind:'gap'},{value:other.x,kind:'align'},{value:other.x+other.placedWidth-width,kind:'align'});
      }
      if(rawX<other.x+other.placedWidth+tolerance&&rawX+width>other.x-tolerance){
        ys.push({value:other.y+other.placedHeight+r.gapY,kind:'gap'},{value:other.y-height-r.gapY,kind:'gap'},{value:other.y,kind:'align'},{value:other.y+other.placedHeight-height,kind:'align'});
      }
    }
    const raw={x:rawX,y:rawY,rotated,snapped:false,valid:check(part,sheet,rawX,rawY,rotated)};
    if(options.enabled===false||!Number.isFinite(tolerance)||tolerance<=0)return raw;
    const candidates=[];
    for(const cx of [{value:rawX,kind:'raw'},...xs.filter(p=>Math.abs(p.value-rawX)<=tolerance)])for(const cy of [{value:rawY,kind:'raw'},...ys.filter(p=>Math.abs(p.value-rawY)<=tolerance)]){
      const distance=Math.hypot(cx.value-rawX,cy.value-rawY);
      if(distance>tolerance||(cx.kind==='raw'&&cy.kind==='raw'))continue;
      if(!check(part,sheet,cx.value,cy.value,rotated))continue;
      const kinds=[cx.kind,cy.kind],kind=kinds.includes('gap')?'gap':kinds.includes('edge')?'edge':'align';
      candidates.push({x:cx.value,y:cy.value,rotated,valid:true,snapped:true,kind,score:distance+(kind==='gap'?0:kind==='edge'?8:16)});
    }
    candidates.sort((a,b)=>a.score-b.score);
    return candidates[0]||raw;
  }
  const signature=order=>JSON.stringify({
    sheet:[order.materialSpec.name,order.materialSpec.sheetWidth,order.materialSpec.sheetHeight,order.materialSpec.margin,order.materialSpec.kerf,order.materialSpec.allowRotation!==false,...(Object.keys(order.materialSpec).some(k=>/^(gap[XY]|margin(Left|Right|Top|Bottom))$/.test(k))?[rules(order.materialSpec)]:[])],
    ...(order.materialSpecs?{materialSpecs:Object.values(order.materialSpecs).map(spec=>[spec.name,spec.sheetWidth,spec.sheetHeight,spec.margin,spec.kerf,spec.allowRotation!==false,...(Object.keys(spec).some(k=>/^(gap[XY]|margin(Left|Right|Top|Bottom))$/.test(k))?[rules(spec)]:[])])}:{}),
    parts:order.parts.map(part=>[part.id,part.height,part.width,part.qty,part.grain!==false,part.thickness,part.color,...(order.parts.some(p=>p.no_rotation===true)?[part.no_rotation===true]:[])])
  });
  function apply(order,base,manual=order.manualLayout){
    if(!manual||manual.signature!==signature(order))return base;
    const sheets=base.sheets.map(sheet=>({...sheet,placements:[]}));
    for(const extra of manual.sheets||[]){
      const template=base.sheets[extra.templateIndex];
      if(!template)return null;
      sheets.push({...template,placements:[]});
    }
    const known=new Set();
    for(const [originalIndex,sheet] of base.sheets.entries())for(const placement of sheet.placements){
      const id=key(placement),override=manual.positions?.[id];known.add(id);
      const target=override?.sheetIndex??originalIndex;
      if(!Number.isInteger(target)||target<0||target>=sheets.length||
         sheets[target].materialKey!==sheet.materialKey)return null;
      const spec=sheets[target].spec||order.materialSpec,r=rules(spec);
      const rotated=override?.rotated??placement.rotated;
      if(typeof rotated!=='boolean'||rotated&&!(spec.allowRotation!==false&&placement.grain===false))return null;
      const width=rotated?placement.width:placement.height,height=rotated?placement.height:placement.width;
      const x=override?.x??placement.x,y=override?.y??placement.y;
      if(![x,y,width,height].every(Number.isFinite)||x<r.left||y<r.top||x+width>spec.sheetWidth-r.right||y+height>spec.sheetHeight-r.bottom)return null;
      sheets[target].placements.push({...placement,x,y,rotated,placedWidth:width,placedHeight:height});
    }
    if(Object.keys(manual.positions||{}).some(id=>!known.has(id)))return null;
    for(const sheet of sheets){
      const r=rules(sheet.spec||order.materialSpec);
      for(let i=0;i<sheet.placements.length;i++)for(let j=i+1;j<sheet.placements.length;j++){
        const a=sheet.placements[i],b=sheet.placements[j];
        const apart=a.x+a.placedWidth+r.gapX<=b.x||b.x+b.placedWidth+r.gapX<=a.x||a.y+a.placedHeight+r.gapY<=b.y||b.y+b.placedHeight+r.gapY<=a.y;
        if(!apart)return null;
      }
    }
    const sheetArea=sheets.reduce((sum,sheet)=>{const spec=sheet.spec||order.materialSpec;return sum+spec.sheetWidth*spec.sheetHeight;},0);
    const partArea=sheets.reduce((sum,sheet)=>sum+sheet.placements.reduce((n,p)=>n+p.placedWidth*p.placedHeight,0),0);
    return {...base,sheets,efficiency:sheetArea?Math.round(partArea/sheetArea*100):0,waste:Math.max(0,(sheetArea-partArea)/1e6),cost:sheets.reduce((sum,sheet)=>sum+Number((sheet.spec||order.materialSpec).price||0),0)};
  }
  function revise(order,base,placementKey,patch){
    const current=order.manualLayout?.signature===signature(order)?order.manualLayout:{signature:signature(order),positions:{}};
    const existing=current.positions[placementKey]||{};
    const candidate={...current,signature:current.signature,positions:{...current.positions,[placementKey]:{...existing,...patch}}};
    if(!apply(order,base,candidate))throw Error('Деталь выходит за поле листа, пересекает другую деталь или нарушает пропил');
    return candidate;
  }
  const api=Object.freeze({key,signature,apply,revise,rules,check,nearest});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.FasadCuttingLayout=api;
})(typeof window==='undefined'?globalThis:window);
