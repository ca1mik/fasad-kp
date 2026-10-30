/* Restricted 2.5D drilling preview. Never emits machine commands. */
(function(root){
  'use strict';
  const finite=value=>Number.isFinite(value)&&value>0;
  const intersect=(x,y,r,zone)=>{
    const nearestX=Math.max(zone.x,Math.min(x,zone.x+zone.w));
    const nearestY=Math.max(zone.y,Math.min(y,zone.y+zone.h));
    return (x-nearestX)**2+(y-nearestY)**2<=r*r;
  };
  function planDrilling(model,tool,machine){
    root.FasadCAD.validate(model);
    if(tool?.type!=='drill'||![tool.diameter,tool.workingLength,tool.maxStep].every(finite)||!String(tool.machineId||'').trim())throw Error('Для сверления укажите сверло, диаметр, рабочую длину, шаг и номер инструмента');
    if(![machine?.workLength,machine?.workWidth,machine?.workZ,machine?.safeZ].every(finite))throw Error('Укажите рабочую зону станка и безопасную высоту');
    if(model.length>machine.workLength||model.width>machine.workWidth||model.thickness>machine.workZ)throw Error('Фасад выходит за рабочую зону станка');
    if(machine.safeZ>machine.workZ)throw Error('Безопасная высота превышает ход оси Z');
    if(!model.holes.length)throw Error('Добавьте отверстия в модель для предпросмотра сверления');
    if(!Array.isArray(machine.clamps||[]))throw Error('Зоны крепления должны быть массивом');
    const zones=machine.clamps||[],motions=[],operations=[];
    for(const [index,hole] of model.holes.entries()){
      if((hole.side||model.side)!=='front')throw Error('Оборотное сверление требует отдельной установки и переналадки');
      if(Math.abs(hole.radius*2-tool.diameter)>1e-6)throw Error(`Отверстие ${index+1}: диаметр сверла не совпадает с диаметром отверстия`);
      if(hole.depth>tool.workingLength)throw Error(`Отверстие ${index+1}: превышена рабочая длина сверла`);
      if(hole.depth>model.thickness)throw Error(`Отверстие ${index+1}: глубина превышает толщину фасада`);
      if(zones.some(zone=>!['x','y','w','h'].every(key=>Number.isFinite(zone[key]))||zone.w<=0||zone.h<=0))throw Error('Некорректная зона крепления');
      if(zones.some(zone=>intersect(hole.x,hole.y,hole.radius,zone)))throw Error(`Отверстие ${index+1} пересекает зону крепления`);
      const steps=Math.ceil(hole.depth/tool.maxStep),path=[];
      path.push({kind:'rapid',x:hole.x,y:hole.y,z:machine.safeZ});
      for(let step=1;step<=steps;step++){
        path.push({kind:'feed',x:hole.x,y:hole.y,z:-Math.min(hole.depth,step*tool.maxStep)});
        path.push({kind:'rapid',x:hole.x,y:hole.y,z:machine.safeZ});
      }
      operations.push({kind:'drilling',hole:index+1,x:hole.x,y:hole.y,depth:hole.depth,passes:steps});
      motions.push(...path);
    }
    return {format:'fasad_drilling_preview_v1',previewOnly:true,scenario:'individual_blank',tool:{...tool},machine:{...machine},operations,motions,
      warnings:['Подача, обороты, постпроцессор, крепление и кинематика не проверены. Это только геометрический предпросмотр.']};
  }
  const api=Object.freeze({planDrilling});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.FasadCAM=api;
})(typeof window==='undefined'?globalThis:window);
