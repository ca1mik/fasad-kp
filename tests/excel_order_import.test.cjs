const test = require('node:test');
const assert = require('node:assert/strict');
global.FasadGroupedParts = require('../demo/grouped_parts.js');
const {importRows} = require('../demo/excel_order_import.js');

test('Excel blank carries color to next explicit color and merges distant matching rows', () => {
  const header = ['№','Длина','Ширина','','м2','Мм','Фрезеровка','Цвет'];
  const rows = [header,[1,2312,1055,3,'',16,'Арт.110','Белый софт']];
  for(let index=0;index<123;index++)rows.push([index+2,400+index,300,1,'',16,'Арт.200','']);
  rows.push([125,2312,1055,2,'',16,'Арт.110','']);
  rows.push([126,2312,1055,1,'',19,'Арт.110','']);
  rows.push([127,2312,1055,1,'',16,'Арт.110','Эвкалипт']);
  const result=importRows(rows);
  assert.equal(result.sourceRows,127);
  assert.equal(result.parts.length,126);
  assert.equal(result.parts[0].qty,5);
  assert.equal(result.parts[0].color,'Белый софт');
  assert.equal(result.parts.at(-1).color,'Эвкалипт');
  assert.equal(result.parts.at(-2).thickness,19);
});

test('Excel import reports invalid quantities instead of silently dropping details', () => {
  const rows=[['№','Длина','Ширина','Кол-во','Мм','Фрезеровка','Цвет'],
    [1,700,400,501,16,'Арт.110','Белый'],[2,700,400,1,16,'Арт.110','']];
  const result=importRows(rows);
  assert.equal(result.parts.length,1);
  assert.equal(result.parts[0].qty,1);
  assert.match(result.warnings[0],/Строка 2/);
});

test('blank group cells inherit article, milling, thickness and color across distant rows',()=>{
  const rows=[['Длина','Ширина','Количество','Толщина','Артикул','Фрезеровка','Цвет'],[700,400,2,19,'110','Рамка','Белый']];
  for(let i=0;i<130;i++)rows.push([200+i,180,1,'','','','']);
  rows.push([700,400,3,'','','',''],[700,400,1,'','','—','Серый'],[700,400,2,'','','','']);
  const result=importRows(rows);assert.equal(result.parts[0].qty,5);assert.equal(result.parts[0].article,'110');assert.equal(result.parts[0].milling,'Рамка');assert.equal(result.parts[0].thickness,19);
  assert.equal(result.parts.at(-1).qty,3);assert.equal(result.parts.at(-1).color,'Серый');assert.equal(result.parts.at(-1).milling,'');
});
