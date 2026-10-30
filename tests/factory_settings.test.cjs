const test = require('node:test');
const assert = require('node:assert/strict');
const settings = require('../demo/factory_settings.js');

test('new settings create versioned cutting snapshots without changing older orders', () => {
  const original = settings.defaults();
  const oldOrder = settings.snapshot(original, 'МДФ 16 мм');
  const changed = settings.revise(original, {
    companyName: 'Фабрика А',
    materials: {
      'МДФ 16 мм': {sheetWidth:2440, sheetHeight:1220, margin:8, kerf:4, allowRotation:false},
      'МДФ 19 мм': original.materials['МДФ 19 мм'],
    },
  });
  const newOrder = settings.snapshot(changed, 'МДФ 16 мм');
  assert.equal(oldOrder.sheetWidth, 2800);
  assert.equal(oldOrder.settingsVersion, 1);
  assert.equal(newOrder.sheetWidth, 2440);
  assert.equal(newOrder.settingsVersion, 2);
  assert.equal(newOrder.allowRotation, false);
  assert.equal(original.materials['МДФ 16 мм'].sheetWidth, 2800);
});

test('invalid sheet geometry is rejected and old settings survive', () => {
  const original = settings.defaults();
  assert.throws(() => settings.revise(original, {
    companyName: 'Тест',
    materials: {
      'МДФ 16 мм': {sheetWidth:100, sheetHeight:100, margin:50, kerf:4},
      'МДФ 19 мм': original.materials['МДФ 19 мм'],
    },
  }), /рабочая зона/);
  assert.equal(original.version, 1);
  assert.equal(original.materials['МДФ 16 мм'].sheetWidth, 2800);
});
