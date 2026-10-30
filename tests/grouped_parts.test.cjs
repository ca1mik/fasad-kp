const test = require('node:test');
const assert = require('node:assert/strict');
const {group} = require('../demo/grouped_parts.js');

test('sums matching details across distant rows without merging other specifications', () => {
  const first = {height:2312,width:1055,qty:3,article:'Арт.110',color:'Белый софт',milling:'Классика',thickness:16};
  const filler = Array.from({length:123}, (_, i) => ({height:100+i,width:200,qty:1,article:'Другой',color:'Серый',milling:'',thickness:16}));
  const rows = [first,...filler,{...first,qty:2,article:'арт 110',color:' белый  софт '},
    {...first,qty:1,thickness:19},{...first,qty:1,color:'Слоновая кость'},
    {...first,qty:1,milling:'Модерн'},{...first,qty:1,article:'111'},
    {...first,qty:1,width:1054}];
  const result = group(rows);
  assert.equal(result.length, 129);
  assert.equal(result[0].quantity, 5);
  assert.equal(result[0].rows, 2);
  assert.equal(result[0].areaSqm, 2312*1055*5/1e6);
});

test('spreadsheet fill-down carries color only until the next explicit color', () => {
  const row = {height:500,width:300,qty:1,article:'110',milling:'',thickness:16};
  const result = group([{...row,color:'Белый софт'},row,{...row,color:'Эвкалипт'},row], {carryFields:['color']});
  assert.deepEqual(result.map(item=>[item.color,item.quantity]), [['Белый софт',2],['Эвкалипт',2]]);
  assert.equal(group([{...row,color:'Белый софт'},row]).length, 2);
});

test('different texture, rotation lock, edge, work or CAD geometry never collapse',()=>{
  const base={height:500,width:300,qty:1,thickness:16};
  const rows=[base,{...base,grain:true},{...base,no_rotation:true},{...base,edge:'2 стороны'},{...base,kind:'Фрезеровка'},{...base,cadModel:{holes:[{x:10,y:20}]}}];
  assert.equal(group(rows).length,rows.length);
  assert.equal(group([...rows,{...base,qty:2}])[0].quantity,3);
});
