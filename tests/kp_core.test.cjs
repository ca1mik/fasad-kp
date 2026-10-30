const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');

const context = {structuredClone, crypto};
vm.createContext(context);
vm.runInContext(fs.readFileSync('demo/kp_core.js', 'utf8'), context);
const kp = context.FasadKP;

test('catalog edit checks duplicates in the same work kind and keeps order snapshots', () => {
  const items = [];
  const first = kp.savePriceItem(items, {article:'арт. 101', name:'Фасад', kind:'Эмаль', unit:'шт', price:1200});
  const savedOrderPart = kp.applyPriceItem({qty:2}, first);
  kp.savePriceItem(items, {article:'102', name:'Фасад новый', kind:'Эмаль', unit:'шт', price:1500}, first.id);
  assert.equal(savedOrderPart.article, '101');
  assert.equal(savedOrderPart.price, 1200);
  assert.equal(kp.quoteRows([savedOrderPart], items)[0].price, 1200);
  assert.equal(kp.quoteRows([{article:'102',name:'Введено вручную',price:100}], items)[0].price, 100);
  assert.throws(() => kp.savePriceItem(items, {article:'арт. 102 ', name:'Дубль', kind:'Эмаль', unit:'шт', price:1}), /уже есть/);
  kp.savePriceItem(items, {article:'102', name:'Другая работа', kind:'ПВХ', unit:'шт', price:1});
});

test('deposit topup, withdrawal, order spend and payment deletion remain balanced', () => {
  const state = {depositMovements:[]};
  const order = {id:'F-0001', clientId:'C-1', amount:500, paidAmount:0, payments:[]};
  kp.addDepositMovement(state, 'C-1', 'topup', 400);
  assert.equal(kp.depositBalance(state, 'C-1'), 400);
  assert.throws(() => kp.addDepositMovement(state, 'C-1', 'withdrawal', 20), /причину/);
  assert.throws(() => kp.addDepositMovement(state, 'C-1', 'withdrawal', 500, 'ошибка'), /недостаточно/);
  kp.addDepositMovement(state, 'C-1', 'withdrawal', 50, 'ошибка');
  const payment = kp.addOrderPayment(state, order, 200, 'deposit');
  assert.equal(kp.depositBalance(state, 'C-1'), 150);
  assert.equal(order.paidAmount, 200);
  kp.deleteOrderPayment(state, order, payment.id);
  assert.equal(kp.depositBalance(state, 'C-1'), 350);
  assert.equal(order.paidAmount, 0);
  assert.equal(order.payments.length, 0);
});

test('clean start removes identifiable sample rows and preserves working rows', () => {
  const source = {clients:[{id:'C-101',name:'Мария Крылова',phone:'+7 920 000-24-18'}, {id:'C-999',name:'Рабочий клиент'}],
    leads:[{id:'L-0281',subject:'Фасады для кухни, эмаль',client:'Марина Соколова'}, {id:'L-999',subject:'Настоящий запрос'}],
    orders:[{id:'F-1042',product:'Кухня · шпон',amount:284000}, {id:'F-2000',product:'Рабочий заказ'}],
    stock:[], priceItems:[], depositMovements:[]};
  const cleaned = kp.cleanDemo(source);
  assert.equal(cleaned.clients.length, 1);
  assert.equal(cleaned.leads.length, 1);
  assert.equal(cleaned.orders.length, 1);
  assert.equal(source.clients.length, 2);
});

test('square metre price uses dimensions while piece price uses count', () => {
  const part = {height:700, width:400, qty:2, price:1500, unit:'м²'};
  assert.equal(kp.lineQuantity(part), 0.56);
  assert.equal(kp.lineAmount(part), 840);
  assert.equal(kp.lineAmount({...part, unit:'шт'}), 3000);
});
