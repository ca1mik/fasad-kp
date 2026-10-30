const test=require('node:test');
const assert=require('node:assert/strict');
const CAD=require('../demo/fasad_cad.js');

const part={id:'P-1',height:700,width:400,thickness:16};
test('parametric frame follows facade dimensions',()=>{
  const model=CAD.modelForPart(part,{template:'rounded_frame',params:{inset:40,bandWidth:8,radius:20,depth:3}});
  const first=CAD.build(model);
  assert.deepEqual(first.milling.map(p=>[p.x,p.y,p.w,p.h,p.r]),[[40,40,620,320,20],[48,48,604,304,12]]);
  const resized=CAD.modelForPart({...part,height:900,width:500,cadModel:model});
  assert.deepEqual(CAD.build(resized).milling.map(p=>[p.w,p.h]),[[820,420],[804,404]]);
  assert.equal(resized.partId,'P-1');
});
test('grooves center and invalid geometry is rejected',()=>{
  const model=CAD.modelForPart(part,{template:'vertical_grooves',params:{inset:30,grooveWidth:6,grooveCount:3,grooveSpacing:80,depth:2}});
  assert.deepEqual(CAD.build(model).milling.map(p=>[p.x,p.y,p.w,p.h]),[[267,30,6,340],[347,30,6,340],[427,30,6,340]]);
  assert.throws(()=>CAD.modelForPart({...part,width:60,cadModel:{template:'frame',params:{inset:40}}}),/Рамка/);
  assert.throws(()=>CAD.modelForPart(part,{template:'smooth',outerRadius:201}),/Радиус/);
  assert.throws(()=>CAD.modelForPart(part,{template:'smooth',params:{depth:16}}),/Глубина/);
  assert.throws(()=>CAD.modelForPart(part,{template:'smooth',holes:[{x:699,y:5,radius:4,depth:3}]}),/Отверстие/);
});
test('coordinates transform without rounding accumulation',()=>{
  const model=CAD.modelForPart(part);
  assert.deepEqual(CAD.pointOnSheet({x:25,y:30},{x:100,y:200,rotation:0},model),{x:125,y:230});
  assert.deepEqual(CAD.pointOnSheet({x:25,y:30},{x:100,y:200,rotation:90},model),{x:470,y:225});
  assert.deepEqual(CAD.pointOnSheet({x:25,y:30},{x:100,y:200,rotation:180},model),{x:775,y:570});
  assert.deepEqual(CAD.pointOnSheet({x:25,y:30},{x:100,y:200,rotation:270},model),{x:130,y:875});
  assert.match(CAD.overlaySvg(CAD.modelForPart(part,{template:'frame'}),{x:100,y:200,rotated:true}),/translate\(500 200\) rotate\(90\)/);
});
test('SVG and DXF carry mm geometry and separate operation layers',()=>{
  const model=CAD.modelForPart(part,{template:'frame',holes:[{x:100,y:50,radius:5,depth:8}],cutouts:[{x:200,y:100,w:20,h:40}]});
  const svg=CAD.drawingSvg(model);
  assert.match(svg,/data-units="mm"/);
  assert.match(svg,/width="810mm"/);
  assert.match(svg,/class="cad-holes"[^>]*cx="100" cy="50" r="5"/);
  const dxf=CAD.dxf(model);
  assert.match(dxf,/\$ACADVER\n1\nAC1015/);
  assert.match(dxf,/\$INSUNITS\n70\n4/);
  assert.match(dxf,/0\nCIRCLE\n100\nAcDbEntity\n8\nHOLES\n100\nAcDbCircle\n10\n100\n20\n350\n40\n5/);
  assert.match(dxf,/0\nLWPOLYLINE\n100\nAcDbEntity\n8\nCUTOUTS/);
  assert.equal((dxf.match(/\n8\nMILLING\n/g)||[]).length,2);
  const section=CAD.sectionSvg(model);
  assert.match(section,/data-section-y="200"/);
  assert.match(section,/data-z-exaggeration="8"/);
  assert.match(section,/x="40" y="0" width="8" height="16"/);
});
test('back projection mirrors geometry and filters front-side operations',()=>{
  const model=CAD.modelForPart(part,{template:'frame',side:'back',holes:[{x:100,y:50,radius:3,depth:8,side:'front'}]});
  const front=CAD.drawingSvg(model);
  const back=CAD.drawingSvg(model,{view:'back'});
  assert.equal((front.match(/<rect class="cad-milling"/g)||[]).length,0);
  assert.equal((back.match(/<rect class="cad-milling"/g)||[]).length,2);
  assert.match(back,/transform="translate\(700 0\) scale\(-1 1\)"/);
  assert.match(front,/class="cad-holes"/);
  assert.doesNotMatch(back,/class="cad-holes"/);
});
test('custom contour rejects self-intersection and pockets stay independent of blank',()=>{
  const outline=[{x:20,y:20},{x:680,y:20},{x:680,y:380},{x:20,y:380}];
  const model=CAD.modelForPart(part,{template:'custom_contour',customContour:outline,pockets:[{x:100,y:100,w:50,h:30,depth:4}]});
  const geometry=CAD.build(model);
  assert.equal(geometry.outer.type,'polygon');
  assert.deepEqual([geometry.blank.w,geometry.blank.h],[700,400]);
  assert.equal(geometry.pockets[0].depth,4);
  assert.match(CAD.overlaySvg(model,{x:10,y:20,rotated:true},'operations'),/cad-pockets/);
  assert.match(CAD.sectionSvg(model),/Точное сечение этого профиля пока не поддерживается/);
  assert.throws(()=>CAD.modelForPart(part,{template:'custom_contour',customContour:[{x:20,y:20},{x:680,y:380},{x:680,y:20},{x:20,y:380}]}),/самопересекается/);
  assert.throws(()=>CAD.modelForPart(part,{pockets:[{x:695,y:10,w:20,h:10,depth:4}]}),/Карман/);
  assert.throws(()=>CAD.modelForPart(part,{template:'custom_contour',customContour:outline,holes:[{x:10,y:50,radius:3,depth:4}]}),/индивидуальный контур/);
  assert.throws(()=>CAD.modelForPart(part,{holes:[{x:100,y:50,radius:6,depth:4},{x:108,y:50,radius:6,depth:4}]}),/Отверстия пересекаются/);
});
