/* Модуль «Калькуляторы»: нотариальный тариф за удостоверение договора дарения
   недвижимости. Считает браузер: показатели обновляются при каждом изменении
   полей ввода, введённые значения хранятся в localStorage. Суммы в полях ввода
   показываются с разделителями разрядов (модуль money-input.js). */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_AMOUNT = "calculators.udostoverenie-dareniya.amount";
  var STORAGE_SHARE = "calculators.udostoverenie-dareniya.share";
  var STORAGE_REGIONAL = "calculators.udostoverenie-dareniya.regional";
  var STORAGE_KIND = "calculators.udostoverenie-dareniya.kind";

  // Кому дарится недвижимость: ключи совпадают со словарём
  // DARENIE_RECIPIENT_LABELS (app/modules/calculators/schemas.py) и со строками
  // выпадающего списка
  var KIND_CLOSE = "close";
  var KIND_OTHER = "other";

  // Промежуточный федеральный тариф — 0,5 % стоимости подаренной доли, но не
  // менее 300 ₽ и не более 20 000 ₽ (нижняя граница действует при стоимости
  // доли до 60 000 ₽, верхняя — от 4 000 000 ₽)
  var PERCENT = 100;
  var FEDERAL_RATE = 0.5;
  var FEDERAL_MIN = 300;
  var FEDERAL_MAX = 20000;

  // Родственникам промежуточный тариф уменьшается вдвое: разница и есть льгота
  var CLOSE_DIVISOR = 2;

  var form = document.getElementById("udostoverenie-dareniya-form");
  if (!form) {
    return;
  }

  var amountInput = document.getElementById("udostoverenie-dareniya-amount");
  var shareInput = document.getElementById("udostoverenie-dareniya-share");
  var regionalInput = document.getElementById("udostoverenie-dareniya-regional");
  var kindInput = document.getElementById("udostoverenie-dareniya-kind");
  var resetButton = document.getElementById("udostoverenie-dareniya-reset");
  var shareError = document.getElementById("udostoverenie-dareniya-share-error");

  var outFederal = document.getElementById("udostoverenie-dareniya-out-federal");
  var outRegional = document.getElementById("udostoverenie-dareniya-out-regional");
  var outBenefit = document.getElementById("udostoverenie-dareniya-out-benefit");
  var outTotal = document.getElementById("udostoverenie-dareniya-out-total");

  // Кому дарится недвижимость: неизвестное значение списка читаем как первую
  // строку «Родственникам»
  function readKind() {
    var value = kindInput ? String(kindInput.value || "") : "";
    return value === KIND_OTHER ? KIND_OTHER : KIND_CLOSE;
  }

  // Стоимость подаренной доли — до округления. Поле доли пустое — дарится весь
  // объект; доля заполнена с ошибкой — считаем по доступным данным (0)
  function giftValue(amount, share) {
    if (!share.filled) {
      return amount;
    }
    if (!share.valid) {
      return 0;
    }
    return amount / share.denominator * share.numerator;
  }

  // Промежуточный федеральный тариф — до округления: 0,5 % стоимости
  // подаренной доли в границах 300…20 000 ₽. Стоимость доли 0 (поле стоимости
  // пустое или заполнено мусором, доля некорректна) промежуточного тарифа не
  // даёт: без стоимости подарка удостоверять нечего
  function federalBase(amount, share) {
    var gift = giftValue(amount, share);
    if (gift <= 0) {
      return 0;
    }
    return Math.min(Math.max(gift / PERCENT * FEDERAL_RATE, FEDERAL_MIN), FEDERAL_MAX);
  }

  // Федеральный тариф — до округления: другим лицам он равен промежуточному,
  // родственникам делится вдвое
  function federalTariff(amount, share, kind) {
    var base = federalBase(amount, share);
    return kind === KIND_OTHER ? base : base / CLOSE_DIVISOR;
  }

  // Округление до целого по правилу математического округления: дробная часть
  // меньше 0,5 — отбрасывается, 0,5 и больше — к целой части прибавляется
  // единица. Значения всегда неотрицательны, поэтому Math.round подходит.
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

  // Сообщение об ошибке в поле доли: показываем только у заполненного поля
  function renderShareError(visible) {
    core.renderShareError(shareError, visible);
  }

  // Пересчёт всех показателей по значениям полей ввода
  function calculate() {
    var amount = readNumber(amountInput);
    var regional = readNumber(regionalInput);
    var share = readShare(shareInput ? shareInput.value : "");
    var kind = readKind();

    // Сначала стоимость даримой доли, затем промежуточный федеральный тариф
    // (0,5 % в границах 300…20 000 ₽) и, для родственников, деление вдвое
    var federal = federalTariff(amount, share, kind);

    // Льгота родственникам — весь федеральный тариф (он уже уменьшен вдвое);
    // другим лицам льготы нет
    var benefit = kind === KIND_OTHER ? 0 : federal;

    // Итого — сумма показанных тарифов: каждое слагаемое округлено отдельно,
    // поэтому результат сходится со значениями на экране
    render(outFederal, federal);
    render(outRegional, regional);
    render(outBenefit, benefit);
    render(outTotal, roundNumber(federal) + roundNumber(regional));

    renderShareError(share.filled && !share.valid);
  }

  // Любое изменение числового поля: значение сразу в хранилище, затем пересчёт
  function handleInput() {
    saveValue(STORAGE_AMOUNT, amountInput);
    saveValue(STORAGE_SHARE, shareInput);
    saveValue(STORAGE_REGIONAL, regionalInput);
    calculate();
  }

  // Выбор категории получателя: значение в хранилище и пересчёт
  function handleKindChange() {
    saveValue(STORAGE_KIND, kindInput);
    calculate();
  }

  // Значения прошлого визита подставляются в поля, расчёт выполняется сразу
  restoreValue(STORAGE_AMOUNT, amountInput);
  restoreValue(STORAGE_SHARE, shareInput);
  restoreValue(STORAGE_REGIONAL, regionalInput);
  restoreValue(STORAGE_KIND, kindInput);

  // Категория могла устареть: неизвестную строку списка возвращаем к первой
  if (kindInput && readKind() !== String(kindInput.value || "")) {
    kindInput.value = KIND_CLOSE;
    storageRemove(STORAGE_KIND);
  }

  // Восстановленные суммы показываем так же, как только что введённые, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput) {
    window.MoneyInput.format(amountInput);
    window.MoneyInput.format(regionalInput);
  }

  amountInput.addEventListener("input", handleInput);
  shareInput.addEventListener("input", handleInput);
  regionalInput.addEventListener("input", handleInput);
  if (kindInput) {
    kindInput.addEventListener("change", handleKindChange);
  }

  // Форма ничего не отправляет: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Очистить» чистит только стоимость объекта: региональный тариф, доля
  // и категория получателя остаются и в полях, и в хранилище
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      amountInput.value = "";
      storageRemove(STORAGE_AMOUNT);
      calculate();
    });
  }

  calculate();
})();
