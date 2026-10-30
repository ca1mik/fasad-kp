const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window:{}};
vm.runInNewContext(fs.readFileSync('demo/production_flow.js','utf8'),context);
const flow=context.window.FasadProduction;
const order={id:'F-MIX',direction:'Эмаль',stage:'Расчёт',status:'Новый',
  materialSpec:{name:'МДФ 16 мм',stockName:'МДФ 16 мм',thickness:16,sheetWidth:2800,sheetHeight:2070,kerf:4,margin:10},
  parts:[
    {id:'P1',name:'Белый',height:700,width:400,qty:1,grain:true,thickness:16,color:'Белый софт'},
    {id:'P2',name:'Зелёный',height:600,width:300,qty:1,grain:true,thickness:19,color:'Эвкалипт'}
  ]};
const stock=[{name:'МДФ 16 мм',qty:5,reserved:0},{name:'МДФ 19 мм',qty:4,reserved:0}];
const plan=[{materialName:'МДФ 16 мм',count:2},{materialName:'МДФ 19 мм',count:1}];

test('mixed thickness reserves and consumes each material atomically',()=>{
  const released=flow.releaseCutting(order,stock,plan);
  assert.deepEqual(Array.from(released.stock,item=>item.reserved),[2,1]);
  assert.equal(released.order.reservedSheets,3);
  assert.equal(flow.isCuttingCurrent(released.order),true);
  assert.equal(flow.isCuttingCurrent({...released.order,parts:[{...order.parts[0],color:'Графит'},order.parts[1]]}),false);
  let reported=flow.reportPart(released.order,{partId:'P1',done:1,workerId:'W-1'});
  reported=flow.reportPart(reported,{partId:'P2',done:1,workerId:'W-1'});
  const completed=flow.completeStage(reported,released.stock,{workerId:'W-1'});
  assert.deepEqual(Array.from(completed.stock,item=>item.qty),[3,3]);
  assert.deepEqual(Array.from(completed.stock,item=>item.reserved),[0,0]);
  assert.equal(completed.order.consumedSheets,3);
  assert.equal(completed.movements.length,2);
  assert.deepEqual(Array.from(stock,item=>item.qty),[5,4]);
});

test('shortage in second material does not reserve first material',()=>{
  assert.throws(()=>flow.releaseCutting(order,[stock[0],{...stock[1],qty:0}],plan),/недостаточно/);
  assert.equal(stock[0].reserved,0);
});
