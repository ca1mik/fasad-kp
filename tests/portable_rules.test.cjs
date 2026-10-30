const {test}=require('node:test');
const assert=require('node:assert/strict');
require('../demo/portable_rules.js');
const r=FasadRules;
const sheet=(length,color='A',rotated=false)=>({spec:r.filmSpec(),color,placements:length?[{x:150,height:rotated?100:length,width:rotated?length:100,rotated,placedWidth:length}]:[]});
test('film procurement uses occupied length with exact 2500 boundary, rotation and empty maps',()=>{
  for(const [length,expected] of [[1000,1.755],[2000,3.055],[2499,3.7037],[2500,4.03],[2744,4.03],[0,0]])assert.equal(r.film(sheet(length)).area,expected);
  assert.equal(r.film(sheet(2000,'A',true)).occupied,2000);
  assert.equal(r.area(r.film(sheet(1000)).area),'1,76');
  assert.equal(r.area(r.film(sheet(2000)).area),'3,06');
  assert.equal(r.area(r.filmTotals([sheet(2000),sheet(2744,'B'),sheet(0)]).area),'7,09');
});
test('areas round only for display, half upwards and after summation',()=>{
  assert.equal(r.area(.105),'0,11');assert.equal(r.area(.01),'0,01');
  assert.equal(r.area(.01001+.01001+.01499),'0,04');
  assert.equal(r.area(r.filmTotals([sheet(1000),sheet(1000)]).area),'3,51');
});
test('manual identifiers keep leading zeroes and letters; order suffix follows work priority',()=>{
  assert.equal(r.manualNumber(' 00012-А '),'00012-А');assert.equal(r.manualNumber('А/0042'),'А/0042');assert.equal(r.manualNumber(''),null);
  assert.equal(r.orderNumber('00012','Эмаль',[]),'00012');
  assert.equal(r.orderNumber('00012-Э','ПВХ',[{kind:'Фрезеровка'}]),'00012-П');
  assert.equal(r.orderNumber('00012','Шпон',[{kind:'Мыло'}]),'00012-Ш');
  assert.equal(r.orderNumber('00012','Эмаль',[{kind:'Мыло'},{kind:'Фрезеровка'}]),'00012-Ф');
  assert.equal(r.orderNumber('00012','Эмаль',[{milling:'Мыло R2'}]),'00012-М');
  assert.equal(r.orderNumber('А-001','ПВХ',[]),'А-001');
});
test('an explicit empty manual note never inherits generated order information',()=>{
  assert.equal(r.note({manual_note:'',note:'summary',comment:'summary'}),'');
  assert.equal(r.note({raw_payload:{manual_note:null},note:'summary'}),'');
  assert.equal(r.note({note:'Customer note'}),'Customer note');
});
