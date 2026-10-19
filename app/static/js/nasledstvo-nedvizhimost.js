/* Модуль «Калькуляторы»: нотариальный тариф за выдачу свидетельства о праве на
   наследство на недвижимое имущество. Считает браузер: расчёт обновляется при
   каждом изменении полей ввода, введённые значения хранятся в localStorage.
   Суммы в полях ввода показываются с разделителями разрядов
   (модуль money-input.js). */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_PRICE = "calculators.nasledstvo-nedvizhimost.price";
  var STORAGE_DECEASED_SHARE = "calculators.nasledstvo-nedvizhimost.deceased-share";
  var STORAGE_HEIR_SHARE = "calculators.nasledstvo-nedvizhimost.heir-share";
  var STORAGE_RATE = "calculators.nasledstvo-nedvizhimost.rate";
  var STORAGE_REGISTRY_FEE = "calculators.nasledstvo-nedvizhimost.registry-fee";

  // Ставка федерального тарифа по умолчанию — первая строка выпадающего списка
  var DEFAULT_RATE = "0.3";

  // Госпошлина в Росреестр по умолчанию — первая строка выпадающего списка
  var DEFAULT_REGISTRY_FEE = "4000";

  var form = document.getElementById("nasledstvo-nedvizhimost-form");
  if (!form) {
    return;
  }

  var priceInput = document.getElementById("nasledstvo-nedvizhimost-price");
  var deceasedShareInput = document.getElementById("nasledstvo-nedvizhimost-deceased-share");
  var heirShareInput = document.getElementById("nasledstvo-nedvizhimost-heir-share");
  var rateInput = document.getElementById("nasledstvo-nedvizhimost-rate");
  var registryFeeInput = document.getElementById("nasledstvo-nedvizhimost-registry-fee");
  var resetButton = document.getElementById("nasledstvo-nedvizhimost-reset");
  var deceasedShareError = document.getElementById("nasledstvo-nedvizhimost-deceased-share-error");
  var heirShareError = document.getElementById("nasledstvo-nedvizhimost-heir-share-error");

  var outShareCost = document.getElementById("nasledstvo-nedvizhimost-out-share-cost");
  var outFederal = document.getElementById("nasledstvo-nedvizhimost-out-federal");
  var outRegional = document.getElementById("nasledstvo-nedvizhimost-out-regional");
  var outTotal = document.getElementById("nasledstvo-nedvizhimost-out-total");
  var outTotalWithFee = document.getElementById("nasledstvo-nedvizhimost-out-total-with-fee");

  // Ставка федерального тарифа из выпадающего списка; любое постороннее
  // значение считается ставкой по умолчанию — 0,3 %
  function readRate(input) {
    var value = input ? String(input.value || "").replace(",", ".") : "";
    return value === "0.6" ? 0.6 : 0.3;
  }

  // Госпошлина в Росреестр из выпадающего списка: 4 000 ₽ или 700 ₽.
  // Любое постороннее значение считается госпошлиной по умолчанию.
  function readRegistryFee(input) {
    var value = input ? String(input.value || "") : "";
    return value === "700" ? 700 : 4000;
  }

  // Округление до целого по правилу математического округления:
  // дробная часть меньше 0,5 — отбрасывается, 0,5 и больше — вверх.
  function roundNumber(value) {
    return Math.round(value);
  }

  // Региональный тариф — фиксированная сумма за выдачу свидетельства в
  // зависимости от стоимости доли наследника. Без стоимости (пустые или
  // некорректные поля) тарифа нет.
  function regionalTariff(shareCost) {
    if (shareCost <= 0) {
      return 0;
    }
    if (shareCost <= 1000000) {
      return 6000;
    }
    if (shareCost <= 2500000) {
      return 7000;
    }
    if (shareCost <= 5000000) {
      return 8000;
    }
    return 9000;
  }

  // Общие помощники калькуляторов: localStorage, разбор значений и вывод
  // показателей — модуль calc-core.js (подключён в шаблоне перед этим скриптом)
  var core = window.CalcCore;
  if (!core) {
    return;
  }
  var storageGet = core.storageGet;
  var storageSet = core.storageSet;
  var storageRemove = core.storageRemove;
  var saveValue = core.saveValue;
  var restoreValue = core.restoreValue;
  var readNumber = core.readNumber;
  var readShare = core.readShare;
  var render = core.render;
  var renderShareError = core.renderShareError;

  // Пересчёт всех показателей по значениям полей ввода
  function calculate() {
    var price = readNumber(priceInput);
    var deceased = readShare(deceasedShareInput ? deceasedShareInput.value : "");
    var heir = readShare(heirShareInput ? heirShareInput.value : "");
    var rate = readRate(rateInput);

    // Стоимость доли наследника: стоимость объекта × доля наследодателя ×
    // доля наследника. Округление до целого — до расчёта тарифов, потому что
    // региональный тариф задан ступенями от стоимости доли.
    var shareCost = 0;
    if (deceased.valid && heir.valid) {
      shareCost = roundNumber(
        price * deceased.numerator / deceased.denominator
          * heir.numerator / heir.denominator
      );
    }

    // Федеральный тариф — ставка (0,3 или 0,6 %) от стоимости доли
    var federal = shareCost / 100 * rate;

    // Региональный тариф — фиксированная сумма по ступеням стоимости доли
    var regional = regionalTariff(shareCost);

    // Госпошлина в Росреестр прибавляется к нотариальному тарифу: 4 000 ₽ или 700 ₽
    var registryFee = readRegistryFee(registryFeeInput);

    render(outShareCost, shareCost);
    render(outFederal, federal);
    render(outRegional, regional);
    render(outTotal, federal + regional);
    render(outTotalWithFee, federal + regional + registryFee);

    renderShareError(deceasedShareError, deceased.filled && !deceased.valid);
    renderShareError(heirShareError, heir.filled && !heir.valid);
  }

  // Любое изменение поля: значение сразу в хранилище, затем пересчёт
  function handleInput() {
    saveValue(STORAGE_PRICE, priceInput);
    saveValue(STORAGE_DECEASED_SHARE, deceasedShareInput);
    saveValue(STORAGE_HEIR_SHARE, heirShareInput);
    saveValue(STORAGE_RATE, rateInput);
    saveValue(STORAGE_REGISTRY_FEE, registryFeeInput);
    calculate();
  }

  // Значения прошлого визита подставляются в поля, расчёт выполняется сразу
  restoreValue(STORAGE_PRICE, priceInput);
  restoreValue(STORAGE_DECEASED_SHARE, deceasedShareInput);
  restoreValue(STORAGE_HEIR_SHARE, heirShareInput);

  // Ставку восстанавливаем только из известных значений списка
  var savedRate = storageGet(STORAGE_RATE);
  if (savedRate === "0.3" || savedRate === "0.6") {
    rateInput.value = savedRate;
  }

  // Госпошлину также восстанавливаем только из известных значений списка
  var savedRegistryFee = storageGet(STORAGE_REGISTRY_FEE);
  if (savedRegistryFee === "4000" || savedRegistryFee === "700") {
    registryFeeInput.value = savedRegistryFee;
  }

  // Восстановленные суммы показываем так же, как только что введённые, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput) {
    window.MoneyInput.format(priceInput);
  }

  priceInput.addEventListener("input", handleInput);
  deceasedShareInput.addEventListener("input", handleInput);
  heirShareInput.addEventListener("input", handleInput);
  rateInput.addEventListener("change", handleInput);
  registryFeeInput.addEventListener("change", handleInput);

  // Форма без отправки на сервер: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Очистить» чистит все поля блока и возвращает ставку и госпошлину
  // по умолчанию
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      priceInput.value = "";
      deceasedShareInput.value = "";
      heirShareInput.value = "";
      rateInput.value = DEFAULT_RATE;
      registryFeeInput.value = DEFAULT_REGISTRY_FEE;
      storageRemove(STORAGE_PRICE);
      storageRemove(STORAGE_DECEASED_SHARE);
      storageRemove(STORAGE_HEIR_SHARE);
      storageRemove(STORAGE_RATE);
      storageRemove(STORAGE_REGISTRY_FEE);
      calculate();
    });
  }

  calculate();
})();
