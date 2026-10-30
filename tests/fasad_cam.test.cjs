const test=require('node:test');
const assert=require('node:assert/strict');
const CAD=require('../demo/fasad_cad.js');
const CAM=require('../demo/fasad_cam.js');
const model=CAD.modelForPart({id:'P',height:700,width:400,thickness:16},{holes:[{x:100,y:50,radius:3,depth:9}]});
const tool={type:'drill',machineId:'T3',diameter:6,workingLength:20,maxStep:4};
const machine={id:'M1',workLength:1000,workWidth:600,workZ:100,safeZ:10,clamps:[{x:300,y:300,w:40,h:40}]};

test('drilling preview has exact peck depths and no machine program',()=>{
  const result=CAM.planDrilling(model,tool,machine);
  assert.equal(result.previewOnly,true);
  assert.equal(result.operations[0].passes,3);
  assert.deepEqual(result.motions.map(move=>move.z),[10,-4,10,-8,10,-9,10]);
  assert.equal(result.motions.every(move=>move.x===100&&move.y===50),true);
  assert.equal(result.warnings.length,1);
  assert.equal(Object.hasOwn(result,'program'),false);
});
test('machine, tool, side and clamp constraints block unsafe previews',()=>{
  assert.throws(()=>CAM.planDrilling(model,{...tool,diameter:8},machine),/диаметр сверла/);
  assert.throws(()=>CAM.planDrilling(model,{...tool,workingLength:8},machine),/рабочая длина/);
  assert.throws(()=>CAM.planDrilling(model,tool,{...machine,workLength:600}),/рабочую зону/);
  assert.throws(()=>CAM.planDrilling(model,tool,{...machine,safeZ:101}),/Безопасная высота/);
  assert.throws(()=>CAM.planDrilling(model,tool,{...machine,clamps:[{x:95,y:45,w:10,h:10}]}),/зону крепления/);
  const back=CAD.modelForPart({id:'P',height:700,width:400,thickness:16},{holes:[{x:100,y:50,radius:3,depth:9,side:'back'}]});
  assert.throws(()=>CAM.planDrilling(back,tool,machine),/Оборотное сверление/);
});
