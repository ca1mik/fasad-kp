/* Settings for this browser-only demo. Each new order keeps a copy of its cutting rules. */
(function (root) {
  "use strict";

  const BASE = Object.freeze({
    version: 1,
    companyName: "Фасад Профи",
    materials: {
      "МДФ 16 мм": {name:"МДФ 16 мм",thickness:16,sheetWidth:2800,sheetHeight:2070,price:0,stockName:"МДФ 16 мм",kerf:4,margin:8,allowRotation:true},
      "МДФ 19 мм": {name:"МДФ 19 мм",thickness:19,sheetWidth:2800,sheetHeight:2070,price:0,stockName:"МДФ 19 мм",kerf:4,margin:8,allowRotation:true}
    }
  });
  const copy = value => JSON.parse(JSON.stringify(value));

  function defaults() { return copy(BASE); }

  function validateMaterial(name, source) {
    const base = BASE.materials[name];
    if (!base) throw new Error("Неизвестный материал");
    const value = {...base, ...source, name, stockName:name, thickness:base.thickness, price:base.price};
    for (const [key,min,max] of [["sheetWidth",100,5000],["sheetHeight",100,5000],["margin",0,100],["kerf",0,20]]) {
      const number = Number(value[key]);
      if (!Number.isFinite(number) || number < min || number > max || !Number.isInteger(number)) {
        throw new Error(`${name}: ${key} должен быть целым числом от ${min} до ${max}`);
      }
      value[key] = number;
    }
    if (value.sheetWidth <= value.margin * 2 + value.kerf || value.sheetHeight <= value.margin * 2 + value.kerf) {
      throw new Error(`${name}: рабочая зона листа должна быть положительной`);
    }
    value.allowRotation = value.allowRotation === true;
    return value;
  }

  function normalize(source) {
    const result = defaults();
    if (!source || typeof source !== "object") return result;
    const companyName = String(source.companyName || "").trim();
    if (companyName && companyName.length <= 255) result.companyName = companyName;
    if (Number.isSafeInteger(source.version) && source.version > 0) result.version = source.version;
    for (const name of Object.keys(result.materials)) {
      try { result.materials[name] = validateMaterial(name, source.materials?.[name]); }
      catch { /* Corrupt browser settings must not break existing orders. */ }
    }
    return result;
  }

  function revise(current, input) {
    const name = String(input.companyName || "").trim();
    if (!name || name.length > 255) throw new Error("Укажите название предприятия до 255 символов");
    const materials = {};
    for (const key of Object.keys(BASE.materials)) materials[key] = validateMaterial(key, input.materials?.[key]);
    return {version:normalize(current).version + 1, companyName:name, materials};
  }

  function snapshot(settings, name) {
    const value = normalize(settings);
    const material = value.materials[name];
    if (!material) throw new Error("Неизвестный материал");
    return {...copy(material), settingsVersion:value.version};
  }

  const api = Object.freeze({defaults, normalize, revise, snapshot});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.FasadFactorySettings = api;
})(typeof window === "undefined" ? globalThis : window);
