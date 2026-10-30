/* Parametric facade geometry in millimetres. No machine toolpaths are generated here. */
(function(root){
  'use strict';
  const copy=value=>JSON.parse(JSON.stringify(value));
  const defaults=Object.freeze({inset:40,bandWidth:8,radius:20,grooveWidth:6,grooveCount:1,grooveSpacing:80,depth:2});
  const templates=Object.freeze({smooth:'Гладкий',frame:'Прямоугольная рамка',rounded_frame:'Скруглённая рамка',vertical_grooves:'Вертикальные пазы',horizontal_grooves:'Горизонтальные пазы',diamond:'Ромб',custom_contour:'Индивидуальный контур'});
  const n=value=>Number(value);
  const fmt=value=>String(Math.round(value*1000)/1000);
  function modelForPart(part,source=part.cadModel,strict=true){
    const model={version:1,partId:String(part.id||''),length:n(part.height),width:n(part.width),thickness:n(part.thickness||16),
      material:String(source?.material||part.material||''),grainDirection:String(source?.grainDirection|| (part.grain===false?'none':'along_length')),template:String(source?.template||'smooth'),
      params:Object.fromEntries(Object.entries({...defaults,...(source?.params||{})}).map(([key,value])=>[key,n(value)])),outerRadius:n(source?.outerRadius||0),
      holes:copy(source?.holes||[]),cutouts:copy(source?.cutouts||[]),pockets:copy(source?.pockets||[]),customContour:copy(source?.customContour||[]),side:String(source?.side||'front')};
    if(strict)validate(model);
    return model;
  }
  function validate(model){
    const {length,width,thickness,params:p}=model;
    if(![length,width,thickness].every(Number.isFinite)||length<=0||width<=0||thickness<=0||length>5000||width>5000||thickness>100)throw Error('Габариты фасада должны быть положительными и в миллиметрах');
    if(!Object.hasOwn(templates,model.template))throw Error('Неизвестный шаблон фрезеровки');
    if(!['none','along_length','along_width'].includes(model.grainDirection))throw Error('Неизвестное направление текстуры');
    if(!['front','back'].includes(model.side))throw Error('Укажите сторону обработки');
    for(const key of Object.keys(defaults))if(!Number.isFinite(n(p[key]))||n(p[key])<0)throw Error(`Параметр ${key} должен быть неотрицательным числом`);
    if(p.depth<=0||p.depth>=thickness)throw Error('Глубина обработки должна быть больше 0 и меньше толщины фасада');
    if(model.outerRadius<0||model.outerRadius>Math.min(length,width)/2)throw Error('Радиус внешнего контура не помещается на фасаде');
    if(model.template==='frame'||model.template==='rounded_frame'){
      if(p.inset<=0||p.bandWidth<=0||2*(p.inset+p.bandWidth)>=Math.min(length,width))throw Error('Рамка не помещается на фасаде');
      if(model.template==='rounded_frame'&&(p.radius<=0||p.radius>Math.min(length-2*p.inset,width-2*p.inset)/2))throw Error('Радиус рамки не помещается на фасаде');
    }
    if(model.template.endsWith('_grooves')){
      if(p.inset<0||p.grooveWidth<=0||!Number.isInteger(n(p.grooveCount))||p.grooveCount<1||p.grooveCount>20)throw Error('Проверьте количество и ширину пазов');
      const cross=model.template==='vertical_grooves'?length:width;
      const along=model.template==='vertical_grooves'?width:length;
      if(along-2*p.inset<=0||p.grooveWidth+(p.grooveCount-1)*p.grooveSpacing>cross-2*p.inset)throw Error('Пазы не помещаются на фасаде');
      if(p.grooveCount>1&&p.grooveSpacing<p.grooveWidth)throw Error('Параллельные пазы пересекаются');
    }
    if(model.template==='diamond'&&(p.inset<=0||p.inset>=Math.min(length,width)/2))throw Error('Ромб не помещается на фасаде');
    if(model.template==='custom_contour'){
      const points=model.customContour;
      if(!Array.isArray(points)||points.length<3||points.length>100)throw Error('Индивидуальный контур должен содержать от 3 до 100 точек');
      if(model.outerRadius)throw Error('Индивидуальный контур и внешний радиус нельзя совмещать');
      if(points.some(point=>!Number.isFinite(point.x)||!Number.isFinite(point.y)||point.x<0||point.y<0||point.x>length||point.y>width))throw Error('Точки контура должны находиться внутри заготовки');
      const cross=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
      const on=(a,b,c)=>Math.abs(cross(a,b,c))<1e-9&&c.x>=Math.min(a.x,b.x)&&c.x<=Math.max(a.x,b.x)&&c.y>=Math.min(a.y,b.y)&&c.y<=Math.max(a.y,b.y);
      const intersects=(a,b,c,d)=>{
        const abC=cross(a,b,c),abD=cross(a,b,d),cdA=cross(c,d,a),cdB=cross(c,d,b);
        return (abC*abD<0&&cdA*cdB<0)||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b);
      };
      let area=0;
      for(let i=0;i<points.length;i++){
        const a=points[i],b=points[(i+1)%points.length];
        if(a.x===b.x&&a.y===b.y)throw Error('Контур содержит нулевой сегмент');
        area+=a.x*b.y-b.x*a.y;
        for(let j=i+1;j<points.length;j++){
          if(j===i+1||(i===0&&j===points.length-1))continue;
          if(intersects(a,b,points[j],points[(j+1)%points.length]))throw Error('Контур самопересекается');
        }
      }
      if(Math.abs(area)<1e-6)throw Error('Контур имеет нулевую площадь');
    }
    for(const hole of model.holes){
      const {x,y,radius,depth}=hole;
      if(![x,y,radius,depth].every(Number.isFinite)||radius<=0||x-radius<0||y-radius<0||x+radius>length||y+radius>width||depth<=0||depth>thickness)throw Error('Отверстие выходит за габариты или имеет неверную глубину');
    }
    for(const rect of model.cutouts){
      const {x,y,w,h}=rect;
      if(![x,y,w,h].every(Number.isFinite)||w<=0||h<=0||x<0||y<0||x+w>length||y+h>width)throw Error('Вырез выходит за габариты фасада');
    }
    for(const pocket of model.pockets){
      const {x,y,w,h,depth}=pocket;
      if(![x,y,w,h,depth].every(Number.isFinite)||w<=0||h<=0||x<0||y<0||x+w>length||y+h>width||depth<=0||depth>=thickness)throw Error('Карман выходит за габариты или имеет неверную глубину');
    }
    for(let i=0;i<model.holes.length;i++)for(let j=i+1;j<model.holes.length;j++){
      const a=model.holes[i],b=model.holes[j];
      if(Math.hypot(a.x-b.x,a.y-b.y)<a.radius+b.radius)throw Error('Отверстия пересекаются');
    }
    if(model.template==='custom_contour'){
      const polygon=model.customContour;
      const inside=point=>{
        let hit=false;
        for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
          const a=polygon[i],b=polygon[j];
          if(((a.y>point.y)!==(b.y>point.y))&&point.x<(b.x-a.x)*(point.y-a.y)/(b.y-a.y)+a.x)hit=!hit;
        }
        return hit;
      };
      const distance=(point,a,b)=>{
        const dx=b.x-a.x,dy=b.y-a.y,t=Math.max(0,Math.min(1,((point.x-a.x)*dx+(point.y-a.y)*dy)/(dx*dx+dy*dy)));
        return Math.hypot(point.x-a.x-t*dx,point.y-a.y-t*dy);
      };
      for(const hole of model.holes){
        if(!inside(hole)||polygon.some((a,i)=>distance(hole,a,polygon[(i+1)%polygon.length])<=hole.radius))throw Error('Отверстие пересекает индивидуальный контур');
      }
      for(const rect of [...model.cutouts,...model.pockets]){
        const corners=[{x:rect.x,y:rect.y},{x:rect.x+rect.w,y:rect.y},{x:rect.x+rect.w,y:rect.y+rect.h},{x:rect.x,y:rect.y+rect.h}];
        const cross=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
        const on=(a,b,c)=>Math.abs(cross(a,b,c))<1e-9&&c.x>=Math.min(a.x,b.x)&&c.x<=Math.max(a.x,b.x)&&c.y>=Math.min(a.y,b.y)&&c.y<=Math.max(a.y,b.y);
        const crossed=corners.some((a,i)=>polygon.some((c,j)=>{
          const b=corners[(i+1)%4],d=polygon[(j+1)%polygon.length];
          return cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b);
        }));
        if(corners.some(point=>!inside(point))||crossed)throw Error('Вырез или карман выходит за индивидуальный контур');
      }
    }
    return model;
  }
  function build(model){
    validate(model);
    const {length:L,width:W,params:p}=model;
    const blank={type:'rect',x:0,y:0,w:L,h:W,layer:'BLANK'};
    const outer=model.template==='custom_contour'?{type:'polygon',points:copy(model.customContour),layer:'OUTER'}:{type:model.outerRadius?'roundRect':'rect',x:0,y:0,w:L,h:W,r:model.outerRadius,layer:'OUTER'};
    const milling=[];
    if(model.template==='frame'||model.template==='rounded_frame'){
      const rounded=model.template==='rounded_frame';
      milling.push({type:rounded?'roundRect':'rect',x:p.inset,y:p.inset,w:L-2*p.inset,h:W-2*p.inset,r:rounded?p.radius:0,layer:'MILLING',depth:p.depth,side:model.side});
      milling.push({type:rounded?'roundRect':'rect',x:p.inset+p.bandWidth,y:p.inset+p.bandWidth,w:L-2*(p.inset+p.bandWidth),h:W-2*(p.inset+p.bandWidth),r:rounded?Math.max(0,p.radius-p.bandWidth):0,layer:'MILLING',depth:p.depth,side:model.side});
    }
    if(model.template.endsWith('_grooves')){
      const vertical=model.template==='vertical_grooves';
      for(let index=0;index<p.grooveCount;index++){
        const center=(vertical?L:W)/2+(index-(p.grooveCount-1)/2)*p.grooveSpacing;
        milling.push({type:'rect',x:vertical?center-p.grooveWidth/2:p.inset,y:vertical?p.inset:center-p.grooveWidth/2,
          w:vertical?p.grooveWidth:L-2*p.inset,h:vertical?W-2*p.inset:p.grooveWidth,layer:'MILLING',depth:p.depth,side:model.side});
      }
    }
    if(model.template==='diamond')milling.push({type:'polygon',points:[{x:L/2,y:p.inset},{x:L-p.inset,y:W/2},{x:L/2,y:W-p.inset},{x:p.inset,y:W/2}],layer:'MILLING',depth:p.depth,side:model.side});
    const pockets=model.pockets.map(c=>({type:'rect',x:c.x,y:c.y,w:c.w,h:c.h,layer:'POCKETS',depth:c.depth,side:c.side||model.side}));
    const holes=model.holes.map(h=>({type:'circle',x:h.x,y:h.y,r:h.radius,layer:'HOLES',depth:h.depth,side:h.side||model.side}));
    const cutouts=model.cutouts.map(c=>({type:'rect',x:c.x,y:c.y,w:c.w,h:c.h,layer:'CUTOUTS',depth:model.thickness,side:'through'}));
    return {blank,outer,milling,pockets,holes,cutouts,operations:[...milling,...pockets,...holes,...cutouts]};
  }
  function primitiveSvg(p){
    const attrs=`class="cad-${p.layer.toLowerCase()}" data-depth="${fmt(p.depth||0)}" data-side="${p.side||'through'}"`;
    if(p.type==='circle')return `<circle ${attrs} cx="${fmt(p.x)}" cy="${fmt(p.y)}" r="${fmt(p.r)}"/>`;
    if(p.type==='polygon')return `<polygon ${attrs} points="${p.points.map(point=>`${fmt(point.x)},${fmt(point.y)}`).join(' ')}"/>`;
    return `<rect ${attrs} x="${fmt(p.x)}" y="${fmt(p.y)}" width="${fmt(p.w)}" height="${fmt(p.h)}"${p.type==='roundRect'?` rx="${fmt(p.r)}"`:''}/>`;
  }
  function drawingSvg(model,options={}){
    const geo=build(model),pad=55,L=model.length,W=model.width;
    const view=options.view==='back'?'back':'front';
    const operations=[...geo.milling,...geo.pockets,...geo.holes,...geo.cutouts].filter(shape=>shape.side===view||shape.side==='through').map(primitiveSvg).join('');
    const grid=options.grid?`<defs><pattern id="cadGrid" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M50 0H0V50" fill="none" stroke="#c4cdd5" stroke-width="0.5"/></pattern></defs><rect x="0" y="0" width="${fmt(L)}" height="${fmt(W)}" fill="url(#cadGrid)" pointer-events="none"/>`:'';
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${fmt(L+pad*2)}mm" height="${fmt(W+pad*2)}mm" viewBox="${-pad} ${-pad} ${fmt(L+pad*2)} ${fmt(W+pad*2)}" data-units="mm" data-view="${view}"><style>.cad-outer{fill:#fff9ec;stroke:#172033;stroke-width:2}.cad-milling{fill:none;stroke:#ba7125;stroke-width:2}.cad-pockets{fill:#f8dbaa;stroke:#ba7125;stroke-width:2}.cad-holes{fill:none;stroke:#235c87;stroke-width:2}.cad-cutouts{fill:#f2f3f5;stroke:#a32331;stroke-width:2}.dimension{fill:#172033;font:20px Arial}.dim-line{stroke:#556574;stroke-width:1.5}</style><g ${view==='back'?`transform="translate(${fmt(L)} 0) scale(-1 1)"`:''}>${primitiveSvg(geo.outer)}${grid}${operations}</g><path class="dim-line" d="M0 -15V-35 M${fmt(L)} -15V-35 M0 -25H${fmt(L)} M-15 0H-35 M-15 ${fmt(W)}H-35 M-25 0V${fmt(W)}"/><text class="dimension" x="${fmt(L/2)}" y="-30" text-anchor="middle">${fmt(L)} мм</text><text class="dimension" x="-30" y="${fmt(W/2)}" text-anchor="middle" transform="rotate(-90 -30 ${fmt(W/2)})">${fmt(W)} мм</text></svg>`;
  }
  // A physical X/Z section at the centre of the facade. Rectangular grooves,
  // frame bands, through cutouts and cylindrical holes intersect this plane.
  function sectionSvg(model){
    const geo=build(model),y=model.width/2,L=model.length,T=model.thickness;
    if(['custom_contour','diamond'].includes(model.template))return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 80" aria-label="Сечение не поддерживается"><text x="10" y="40" font-size="20">Точное сечение этого профиля пока не поддерживается</text></svg>`;
    const removed=[];
    function add(x,w,depth,side){if(w>0)removed.push({x,w,depth,side});}
    if(model.template==='frame'||model.template==='rounded_frame'){
      const {inset,bandWidth,depth}=model.params;
      add(inset,bandWidth,depth,model.side);add(L-inset-bandWidth,bandWidth,depth,model.side);
    }else for(const shape of geo.milling){
      if(shape.type==='rect'&&y>=shape.y&&y<=shape.y+shape.h)add(shape.x,shape.w,shape.depth,shape.side);
    }
    for(const pocket of geo.pockets)if(y>=pocket.y&&y<=pocket.y+pocket.h)add(pocket.x,pocket.w,pocket.depth,pocket.side);
    for(const hole of geo.holes){
      const dy=Math.abs(y-hole.y);
      if(dy<=hole.r){const half=Math.sqrt(hole.r*hole.r-dy*dy);add(hole.x-half,half*2,hole.depth,hole.side);}
    }
    for(const cutout of geo.cutouts)if(y>=cutout.y&&y<=cutout.y+cutout.h)add(cutout.x,cutout.w,T,'through');
    const pad=35,scale=8,height=T*scale;
    const cavities=removed.map(item=>{
      const z=item.side==='back'?(T-item.depth)*scale:0;
      return `<rect x="${fmt(item.x)}" y="${fmt(z)}" width="${fmt(item.w)}" height="${fmt(item.depth*scale)}" fill="#fff" stroke="#ba7125" stroke-width="1"/>`;
    }).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${-pad} ${-pad} ${fmt(L+2*pad)} ${fmt(height+2*pad)}" data-units="mm" data-section-y="${fmt(y)}" data-z-exaggeration="8" aria-label="Сечение по середине ширины"><rect x="0" y="0" width="${fmt(L)}" height="${fmt(height)}" fill="#f2dfbe" stroke="#172033" stroke-width="2"/>${cavities}<text x="0" y="-10" font-size="15">Лицевая сторона · сечение Y=${fmt(y)} мм · толщина ${fmt(T)} мм</text><text x="0" y="${fmt(height+24)}" font-size="12">Оборотная сторона · толщина увеличена ×8 для читаемости</text></svg>`;
  }
  function pointOnSheet(point,placement,model){
    const angle=Number(placement.rotation??(placement.rotated?90:0));
    const x=n(point.x),y=n(point.y),left=n(placement.x),top=n(placement.y);
    if(![x,y,left,top].every(Number.isFinite))throw Error('Некорректные координаты листа');
    if(angle===0)return {x:left+x,y:top+y};
    if(angle===90)return {x:left+model.width-y,y:top+x};
    if(angle===180)return {x:left+model.length-x,y:top+model.width-y};
    if(angle===270)return {x:left+y,y:top+model.length-x};
    throw Error('Поддерживаются повороты 0°, 90°, 180° и 270°');
  }
  function overlaySvg(model,placement,mode='milling'){
    const geo=build(model);
    if(!['contours','milling','operations'].includes(mode))return '';
    const shapes=mode==='contours'?[geo.outer]:mode==='milling'?[...geo.milling,...geo.pockets].filter(shape=>shape.side==='front'):geo.operations;
    const angle=Number(placement.rotation??(placement.rotated?90:0));
    let transform=`translate(${fmt(placement.x)} ${fmt(placement.y)})`;
    if(angle===90)transform=`translate(${fmt(placement.x+model.width)} ${fmt(placement.y)}) rotate(90)`;
    else if(angle===180)transform=`translate(${fmt(placement.x+model.length)} ${fmt(placement.y+model.width)}) rotate(180)`;
    else if(angle===270)transform=`translate(${fmt(placement.x)} ${fmt(placement.y+model.length)}) rotate(270)`;
    else if(angle!==0)throw Error('Неподдерживаемый угол поворота');
    return `<g class="cad-overlay" transform="${transform}">${shapes.map(primitiveSvg).join('')}</g>`;
  }
  function dxf(model){
    const geo=build(model),out=[];
    const pair=(code,value)=>{out.push(String(code),String(value));};
    const entity=(type,layer)=>{pair(0,type);pair(100,'AcDbEntity');pair(8,layer);pair(100,type==='LWPOLYLINE'?'AcDbPolyline':type==='LINE'?'AcDbLine':'AcDbCircle');};
    const line=(x1,y1,x2,y2,layer)=>{entity('LINE',layer);pair(10,fmt(x1));pair(20,fmt(model.width-y1));pair(11,fmt(x2));pair(21,fmt(model.width-y2));};
    const arc=(cx,cy,r,start,end,layer)=>{entity('ARC',layer);pair(10,fmt(cx));pair(20,fmt(model.width-cy));pair(40,fmt(r));pair(100,'AcDbArc');pair(50,fmt(start));pair(51,fmt(end));};
    function write(p){
      if(p.type==='circle'){entity('CIRCLE',p.layer);pair(10,fmt(p.x));pair(20,fmt(model.width-p.y));pair(40,fmt(p.r));return;}
      if(p.type==='polygon'){entity('LWPOLYLINE',p.layer);pair(90,p.points.length);pair(70,1);for(const point of p.points){pair(10,fmt(point.x));pair(20,fmt(model.width-point.y));}return;}
      const {x,y,w,h}=p;
      if(p.type==='rect'||!p.r){entity('LWPOLYLINE',p.layer);pair(90,4);pair(70,1);for(const [px,py] of [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]){pair(10,fmt(px));pair(20,fmt(model.width-py));}return;}
      const r=p.r;
      line(x+r,y,x+w-r,y,p.layer);line(x+w,y+r,x+w,y+h-r,p.layer);line(x+w-r,y+h,x+r,y+h,p.layer);line(x,y+h-r,x,y+r,p.layer);
      arc(x+w-r,y+r,r,0,90,p.layer);arc(x+r,y+r,r,90,180,p.layer);
      arc(x+r,y+h-r,r,180,270,p.layer);arc(x+w-r,y+h-r,r,270,360,p.layer);
    }
    pair(0,'SECTION');pair(2,'HEADER');pair(9,'$ACADVER');pair(1,'AC1015');pair(9,'$INSUNITS');pair(70,4);pair(0,'ENDSEC');
    pair(0,'SECTION');pair(2,'ENTITIES');
    [geo.outer,...geo.milling,...geo.pockets,...geo.holes,...geo.cutouts].forEach(write);
    pair(0,'ENDSEC');pair(0,'EOF');
    return out.join('\n')+'\n';
  }
  const api=Object.freeze({templates,defaults,modelForPart,validate,build,drawingSvg,sectionSvg,pointOnSheet,overlaySvg,dxf});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.FasadCAD=api;
})(typeof window==='undefined'?globalThis:window);
