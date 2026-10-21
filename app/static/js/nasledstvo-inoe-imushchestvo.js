/* Модуль «Калькуляторы»: нотариальный тариф за выдачу свидетельства о праве на
   наследство на иное имущество. Считает браузер: расчёт обновляется при
   каждом изменении полей ввода, введённые значения хранятся в localStorage.
   Суммы в полях ввода показываются с разделителями разрядов
   (модуль money-input.js). Региональный тариф берётся из справочника
   «Региональный тариф для наследства» (раздел «Настройки»): строки приходят
   в шаблон из базы, выбранная строка подставляет свой тариф в поле
   «Региональный тариф». */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_PRICE = "calculators.nasledstvo-inoe-imushchestvo.price";
  var STORAGE_DECEASED_SHARE = "calculators.nasledstvo-inoe-imushchestvo.deceased-share";
  var STORAGE_HEIR_SHARE = "calculators.nasledstvo-inoe-imushchestvo.heir-share";
  var STORAGE_RATE = "calculators.nasledstvo-inoe-imushchestvo.rate";
  var STORAGE_ASSET = "calculators.nasledstvo-inoe-imushchestvo.asset";

  // Ставка федерального тарифа по умолчанию — первая строка выпадающего списка
  var DEFAULT_RATE = "0.3";

  var form = document.getElementById("nasledstvo-inoe-imushchestvo-form");
  if (!form) {
    return;
  }

  var priceInput = document.getElementById("nasledstvo-inoe-imushchestvo-price");
  var deceasedShareInput = document.getElementById("nasledstvo-inoe-imushchestvo-deceased-share");
  var heirShareInput = document.getElementById("nasledstvo-inoe-imushchestvo-heir-share");
  var rateInput = document.getElementById("nasledstvo-inoe-imushchestvo-rate");
  var assetInput = document.getElementById("nasledstvo-inoe-imushchestvo-asset");
  var regionalInput = document.getElementById("nasledstvo-inoe-imushchestvo-regional");
  var resetButton = document.getElementById("nasledstvo-inoe-imushchestvo-reset");
  var deceasedShareError = document.getElementById("nasledstvo-inoe-imushchestvo-deceased-share-error");
  var heirShareError = document.getElementById("nasledstvo-inoe-imushchestvo-heir-share-error");

  var outShareCost = document.getElementById("nasledstvo-inoe-imushchestvo-out-share-cost");
  var outFederal = document.getElementById("nasledstvo-inoe-imushchestvo-out-federal");
  var outRegional = document.getElementById("nasledstvo-inoe-imushchestvo-out-regional");
  var outTotal = document.getElementById("nasledstvo-inoe-imushchestvo-out-total");

  // Ставка федерального тарифа из выпадающего списка; любое постороннее
  // значение считается ставкой по умолчанию — 0,3 %
  function readRate(input) {
    var value = input ? String(input.value || "").replace(",", ".") : "";
    return value === "0.6" ? 0.6 : 0.3;
  }

  // Региональный тариф выбранной строки справочника «Региональный тариф для
  // наследства»: значение второго столбца таблицы хранится в атрибуте
  // data-rate варианта списка. Пустой или испорченный вариант даёт 0.
  function selectedRegionalTariff() {
    if (!assetInput || !assetInput.options) {
      return 0;
    }
    var option = assetInput.options[assetInput.selectedIndex];
    var value = option ? parseInt(option.getAttribute("data-rate") || "", 10) : NaN;
    return isFinite(value) && value > 0 ? value : 0;
  }

  // Поле «Региональный тариф» показывает тариф выбранной строки справочника.
  // Вид и формат — как у «Базовый региональный тариф» в ДКП: то же денежное
  // поле с разделителями разрядов (data-money, модуль money-input.js).
  function showRegionalTariff() {
    if (!regionalInput) {
      return;
    }
    var tariff = selectedRegionalTariff();
    regionalInput.value = tariff > 0 ? String(tariff) : "";
    if (window.MoneyInput) {
      window.MoneyInput.format(regionalInput);
    }
  }

  // Округление до целого по правилу математического округления:
  // дробная часть меньше 0,5 — отбрасывается, 0,5 и больше — вверх.
  function roundNumber(value) {
    return Math.round(value);
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
    // региональный тариф начисляется только при наличии стоимости доли.
    var shareCost = 0;
    if (deceased.valid && heir.valid) {
      shareCost = roundNumber(
        price * deceased.numerator / deceased.denominator
          * heir.numerator / heir.denominator
      );
    }

    // Федеральный тариф — ставка (0,3 или 0,6 %) от стоимости доли
    var federal = shareCost / 100 * rate;

    // Региональный тариф — сумма из выбранной строки справочника: от стоимости
    // доли не зависит, но без стоимости доли не начисляется
    var regional = shareCost > 0 ? readNumber(regionalInput) : 0;

    render(outShareCost, shareCost);
    render(outFederal, federal);
    render(outRegional, regional);
    render(outTotal, federal + regional);

    renderShareError(deceasedShareError, deceased.filled && !deceased.valid);
    renderShareError(heirShareError, heir.filled && !heir.valid);
  }

  // Любое изменение поля: значение сразу в хранилище, затем пересчёт
  function handleInput() {
    saveValue(STORAGE_PRICE, priceInput);
    saveValue(STORAGE_DECEASED_SHARE, deceasedShareInput);
    saveValue(STORAGE_HEIR_SHARE, heirShareInput);
    saveValue(STORAGE_RATE, rateInput);
    calculate();
  }

  // Смена имущества: в поле «Региональный тариф» подставляется тариф
  // выбранной строки справочника, выбор запоминается
  function handleAssetChange() {
    showRegionalTariff();
    saveValue(STORAGE_ASSET, assetInput);
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

  // Имущество восстанавливаем, только если такая строка ещё есть в
  // справочнике: удалённую строку выбрать нельзя
  var savedAsset = storageGet(STORAGE_ASSET);
  if (savedAsset && assetInput) {
    Array.prototype.forEach.call(assetInput.options, function (option) {
      if (option.value === savedAsset) {
        assetInput.value = savedAsset;
      }
    });
  }

  // Поле «Региональный тариф» всегда показывает тариф из справочника
  showRegionalTariff();

  // Восстановленные суммы показываем так же, как только что введённые, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput) {
    window.MoneyInput.format(priceInput);
  }

  priceInput.addEventListener("input", handleInput);
  deceasedShareInput.addEventListener("input", handleInput);
  heirShareInput.addEventListener("input", handleInput);
  rateInput.addEventListener("change", handleInput);
  if (assetInput) {
    assetInput.addEventListener("change", handleAssetChange);
  }

  // Форма без отправки на сервер: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Очистить» чистит стоимость и доли, ставка возвращается к 0,3 %;
  // имущество и его региональный тариф остаются — как «Базовый региональный
  // тариф» в ДКП
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      priceInput.value = "";
      deceasedShareInput.value = "";
      heirShareInput.value = "";
      rateInput.value = DEFAULT_RATE;
      storageRemove(STORAGE_PRICE);
      storageRemove(STORAGE_DECEASED_SHARE);
      storageRemove(STORAGE_HEIR_SHARE);
      storageRemove(STORAGE_RATE);
      calculate();
    });
  }

  calculate();
})();
