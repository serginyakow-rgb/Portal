/* Модуль «Калькуляторы»: нотариальный тариф за удостоверение договора
   купли-продажи недвижимости (необязательная нотариальная форма). Считает
   браузер: показатели обновляются при каждом изменении полей ввода, введённые
   значения хранятся в localStorage. Суммы в полях ввода показываются
   с разделителями разрядов (модуль money-input.js). */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_PRICE = "calculators.udostoverenie-dkp.price";
  var STORAGE_BASE = "calculators.udostoverenie-dkp.base";
  var STORAGE_KIND = "calculators.udostoverenie-dkp.kind";

  // Категории получателя: ключи совпадают со словарём DKP_RECIPIENT_LABELS
  // (app/modules/calculators/schemas.py) и со строками выпадающего списка
  var KIND_CLOSE = "close";
  var KIND_OTHER = "other";

  // Границы сумм сделки, ₽
  var ONE_MILLION = 1000000;
  var TEN_MILLION = 10000000;

  // Федеральный тариф для близких (супруг, родители, дети, внуки):
  // до 10 000 000 ₽ включительно — 3 000 ₽ + 0,2 % цены договора; свыше —
  // 23 000 ₽ + 0,1 % суммы сверх 10 000 000 ₽, но не более 50 000 ₽
  var CLOSE_BASE = 3000;
  var CLOSE_RATE = 0.002;
  var CLOSE_OVER_BASE = 23000;
  var CLOSE_OVER_RATE = 0.001;
  var CLOSE_CAP = 50000;

  // Федеральный тариф для других лиц: до 1 000 000 ₽ включительно — 3 000 ₽ +
  // 0,4 % цены договора; свыше 1 000 000 ₽ до 10 000 000 ₽ включительно —
  // 7 000 ₽ + 0,2 % суммы сверх 1 000 000 ₽; свыше 10 000 000 ₽ — 25 000 ₽ +
  // 0,1 % суммы сверх 10 000 000 ₽, для жилых помещений и земельных участков,
  // занятых жилыми домами, — не более 100 000 ₽
  var OTHER_BASE = 3000;
  var OTHER_RATE = 0.004;
  var OTHER_MID_BASE = 7000;
  var OTHER_MID_RATE = 0.002;
  var OTHER_OVER_BASE = 25000;
  var OTHER_OVER_RATE = 0.001;
  var OTHER_CAP = 100000;

  var form = document.getElementById("udostoverenie-dkp-form");
  if (!form) {
    return;
  }

  var priceInput = document.getElementById("udostoverenie-dkp-price");
  var baseInput = document.getElementById("udostoverenie-dkp-base");
  var kindInput = document.getElementById("udostoverenie-dkp-kind");
  var resetButton = document.getElementById("udostoverenie-dkp-reset");

  var outFederal = document.getElementById("udostoverenie-dkp-out-federal");
  var outRegional = document.getElementById("udostoverenie-dkp-out-regional");
  var outTotal = document.getElementById("udostoverenie-dkp-out-total");

  // Категория получателя: неизвестное значение списка читаем как первую строку
  // «Супругу, родителям, детям, внукам»
  function readKind() {
    var value = kindInput ? String(kindInput.value || "") : "";
    return value === KIND_OTHER ? KIND_OTHER : KIND_CLOSE;
  }

  // Федеральный тариф — до округления. Цена 0 (пустое или мусорное значение
  // поля) тарифа не даёт: без цены договора удостоверять нечего
  function federalTariff(price, kind) {
    if (price <= 0) {
      return 0;
    }
    if (kind === KIND_OTHER) {
      if (price <= ONE_MILLION) {
        return OTHER_BASE + price * OTHER_RATE;
      }
      if (price <= TEN_MILLION) {
        return OTHER_MID_BASE + (price - ONE_MILLION) * OTHER_MID_RATE;
      }
      var over = OTHER_OVER_BASE + (price - TEN_MILLION) * OTHER_OVER_RATE;
      return Math.min(over, OTHER_CAP);
    }
    if (price <= TEN_MILLION) {
      return CLOSE_BASE + price * CLOSE_RATE;
    }
    var overClose = CLOSE_OVER_BASE + (price - TEN_MILLION) * CLOSE_OVER_RATE;
    return Math.min(overClose, CLOSE_CAP);
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
  var render = core.render;

  // Пересчёт показателей по значениям полей ввода. Каждое значение округляется
  // до целого отдельно, «Итого» — сумма уже округлённых тарифов, поэтому
  // результат всегда сходится со слагаемыми на экране.
  function calculate() {
    var federal = Math.round(federalTariff(readNumber(priceInput), readKind()));
    var regional = Math.round(readNumber(baseInput));

    render(outFederal, federal);
    render(outRegional, regional);
    render(outTotal, federal + regional);
  }

  // Любое изменение числового поля: значение сразу в хранилище, затем пересчёт
  function handleInput() {
    saveValue(STORAGE_PRICE, priceInput);
    saveValue(STORAGE_BASE, baseInput);
    calculate();
  }

  // Выбор категории получателя: значение в хранилище и пересчёт
  function handleKindChange() {
    saveValue(STORAGE_KIND, kindInput);
    calculate();
  }

  // Значения прошлого визита подставляются в поля, расчёт выполняется сразу
  restoreValue(STORAGE_PRICE, priceInput);
  restoreValue(STORAGE_BASE, baseInput);
  restoreValue(STORAGE_KIND, kindInput);

  // Категория могла устареть: неизвестную строку списка возвращаем к первой
  if (kindInput && readKind() !== String(kindInput.value || "")) {
    kindInput.value = KIND_CLOSE;
    storageRemove(STORAGE_KIND);
  }

  // Восстановленные суммы показываем так же, как только что введённые, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput) {
    window.MoneyInput.format(priceInput);
    window.MoneyInput.format(baseInput);
  }

  priceInput.addEventListener("input", handleInput);
  baseInput.addEventListener("input", handleInput);
  if (kindInput) {
    kindInput.addEventListener("change", handleKindChange);
  }

  // Форма ничего не отправляет: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Очистить» чистит только цену договора: базовый региональный тариф и
  // категория получателя остаются и в полях, и в хранилище
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      priceInput.value = "";
      storageRemove(STORAGE_PRICE);
      calculate();
    });
  }

  calculate();
})();
