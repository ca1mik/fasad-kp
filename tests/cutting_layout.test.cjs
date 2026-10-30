const test=require('node:test');
const assert=require('node:assert/strict');
const Layout=require('../demo/cutting_layout.js');
const spec={name:'MDF',sheetWidth:1000,sheetHeight:800,margin:10,kerf:4,allowRotation:true};
const parts=[{id:'P1',height:200,width:100,qty:1,grain:false},{id:'P2',height:200,width:100,qty:1,grain:false}];
const order={materialSpec:spec,parts};
const base={sheets:[{placements:[
  {...parts[0],number:1,x:10,y:10,placedWidth:200,placedHeight:100,rotated:false},
  {...parts[1],number:1,x:214,y:10,placedWidth:200,placedHeight:100,rotated:false}
]}],parts:2};

test('manual coordinates persist as an exact mm override with kerf',()=>{
  const manual=Layout.revise(order,base,'P2#1',{sheetIndex:0,x:500,y:120,rotated:true});
  const result=Layout.apply(order,base,manual);
  const moved=result.sheets[0].placements[1];
  assert.deepEqual([moved.x,moved.y,moved.placedWidth,moved.placedHeight,moved.rotated],[500,120,100,200,true]);
  assert.equal(Layout.apply({...order,manualLayout:manual},base).sheets[0].placements[1].x,500);
  assert.equal(Layout.apply({...order,parts:[{...parts[0],height:210},parts[1]],manualLayout:manual},base),base);
});
test('collision, edge and grain constraints reject invalid manual coordinates',()=>{
  assert.throws(()=>Layout.revise(order,base,'P2#1',{x:205,y:10}),/пропил/);
  assert.throws(()=>Layout.revise(order,base,'P2#1',{x:900,y:10}),/поле листа/);
  const grained={...base,sheets:[{placements:[base.sheets[0].placements[0],{...base.sheets[0].placements[1],grain:true}]}]};
  assert.throws(()=>Layout.revise({...order,parts:[parts[0],{...parts[1],grain:true}]},grained,'P2#1',{rotated:true}),/пропил/);
  assert.throws(()=>Layout.revise(order,base,'P2#1',{sheetIndex:1}),/пропил/);
});
test('part may move to another existing sheet while keeping its unique ID',()=>{
  const twoSheets={sheets:[{placements:[base.sheets[0].placements[0]]},{placements:[base.sheets[0].placements[1]]}],parts:2};
  const manual=Layout.revise(order,twoSheets,'P2#1',{sheetIndex:0,x:300,y:10});
  const result=Layout.apply(order,twoSheets,manual);
  assert.deepEqual(result.sheets.map(sheet=>sheet.placements.length),[2,0]);
  assert.equal(Layout.key(result.sheets[0].placements[1]),'P2#1');
});

test('new compatible manual sheet persists with exact gap and updated usage',()=>{
  const extended={...order,manualLayout:{signature:Layout.signature(order),positions:{},sheets:[{templateIndex:0}]}};
  extended.manualLayout=Layout.revise(extended,base,'P2#1',{sheetIndex:1,x:10,y:10,rotated:true});
  const result=Layout.apply(extended,base);
  assert.deepEqual(result.sheets.map(sheet=>sheet.placements.length),[1,1]);
  assert.equal(result.sheets[1].placements[0].placedWidth,100);
  assert.equal(extended.manualLayout.sheets.length,1);
  const exact=Layout.revise(order,base,'P2#1',{x:214,y:10});
  assert.ok(Layout.apply(order,base,exact));
  assert.throws(()=>Layout.revise(order,base,'P2#1',{x:213,y:10}));
});

test('Portable snap uses one neighbour gap and respects independent axes and margins',()=>{
  const config={...spec,gapX:65,gapY:20,marginLeft:30,marginRight:40,marginTop:50,marginBottom:60};
  const a={...parts[0],number:1,x:30,y:50,placedWidth:200,placedHeight:100,rotated:false};
  const b={...parts[1],number:1,x:600,y:400,placedWidth:200,placedHeight:100,rotated:false};
  const sheet={spec:config,placements:[a,b]};
  const right=Layout.nearest(b,sheet,304,50,false,{tolerance:25,edges:false});
  assert.deepEqual([right.x,right.y,right.snapped,right.kind],[295,50,true,'gap']);
  assert.equal(right.x-a.x-a.placedWidth,65);
  const below=Layout.nearest(b,sheet,30,177,false,{tolerance:25,edges:false});
  assert.equal(below.y,170);
  assert.equal(below.y-a.y-a.placedHeight,20);
  assert.equal(Layout.check(b,sheet,294,50,false),false);
  assert.equal(Layout.check(b,sheet,760,600,false),true);
  assert.equal(Layout.check(b,sheet,761,600,false),false);
  const off=Layout.nearest(b,sheet,304,50,false,{enabled:false});
  assert.deepEqual([off.x,off.y,off.snapped],[304,50,false]);
});

test('Portable edge magnet ignores distant neighbours and rejects invalid candidates',()=>{
  const config={...spec,marginLeft:30,marginRight:40,marginTop:50,marginBottom:60};
  const piece={...parts[0],number:1,x:400,y:400,placedWidth:200,placedHeight:100,rotated:false};
  const sheet={spec:config,placements:[piece]};
  const corner=Layout.nearest(piece,sheet,25,46,false,{tolerance:25});
  assert.deepEqual([corner.x,corner.y,corner.valid,corner.kind],[30,50,true,'edge']);
  const free=Layout.nearest(piece,sheet,400,400,false,{tolerance:25});
  assert.equal(free.snapped,false);
  assert.equal(Layout.nearest(piece,sheet,-100,-100,false,{tolerance:25}).valid,false);
  const disabled=Layout.nearest(piece,sheet,25,46,false,{edges:false,parts:false,tolerance:25});
  assert.equal(disabled.valid,false);
});
