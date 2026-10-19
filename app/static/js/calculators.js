/* Модуль «Калькуляторы»: расчёт нотариального тарифа за удостоверение договора
   купли-продажи недвижимости. Считает браузер: расчёт обновляется при каждом
   изменении полей ввода, введённые значения хранятся в localStorage. Суммы в
   полях ввода показываются с разделителями разрядов (модуль money-input.js). */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_PRICE = "calculators.dkp.price";
  var STORAGE_SHARE = "calculators.dkp.share";
  var STORAGE_BASE = "calculators.dkp.base";

  // Федеральный тариф для обязательной нотариальной формы: 0,5 % цены
  // договора, но не менее 300 ₽ и не более 20 000 ₽ (нижняя граница действует
  // при цене до 60 000 ₽, верхняя — от 4 000 000 ₽)
  var FEDERAL_RATE = 0.005;
  var FEDERAL_MIN = 300;
  var FEDERAL_MAX = 20000;

  var form = document.getElementById("tariff-form");
  if (!form) {
    return;
  }

  var priceInput = document.getElementById("tariff-price");
  var shareInput = document.getElementById("tariff-share");
  var baseInput = document.getElementById("tariff-base");
  var resetButton = document.getElementById("tariff-reset");
  var shareError = document.getElementById("tariff-share-error");

  var outFederal = document.getElementById("tariff-out-federal");
  var outRegional = document.getElementById("tariff-out-regional");
  var outBenefit = document.getElementById("tariff-out-benefit");
  var outTotal = document.getElementById("tariff-out-total");

  // Федеральный тариф — до округления: 0,5 % цены договора, но не менее 300 ₽
  // и не более 20 000 ₽. Цена 0 (пустое или мусорное значение поля) тарифа не
  // даёт: без цены договора удостоверять нечего
  function federalTariff(price) {
    if (price <= 0) {
      return 0;
    }
    return Math.min(Math.max(price * FEDERAL_RATE, FEDERAL_MIN), FEDERAL_MAX);
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
    var price = readNumber(priceInput);
    var base = readNumber(baseInput);
    var share = readShare(shareInput ? shareInput.value : "");

    // Федеральный тариф
    var federal = federalTariff(price);

    // Льгота — половина базового регионального тарифа, умноженная на долю
    // несовершеннолетних продавцов; при некорректной доле равна 0
    var benefit = share.valid
      ? base / 2 / share.denominator * share.numerator
      : 0;

    // Региональный тариф — базовый региональный тариф минус льгота
    var regional = base - benefit;

    // Итого — сумма федерального и регионального тарифов.
    // Округление до целого применяется к каждому показателю отдельно при выводе
    // (см. formatMoney), поэтому «Итого» считается по неокруглённым значениям
    render(outFederal, federal);
    render(outBenefit, benefit);
    render(outRegional, regional);
    render(outTotal, federal + regional);

    renderShareError(share.filled && !share.valid);
  }

  // Любое изменение поля: значение сразу в хранилище, затем пересчёт
  function handleInput() {
    saveValue(STORAGE_PRICE, priceInput);
    saveValue(STORAGE_SHARE, shareInput);
    saveValue(STORAGE_BASE, baseInput);
    calculate();
  }

  // Значения прошлого визита подставляются в поля, расчёт выполняется сразу
  restoreValue(STORAGE_PRICE, priceInput);
  restoreValue(STORAGE_SHARE, shareInput);
  restoreValue(STORAGE_BASE, baseInput);

  // Восстановленные суммы показываем так же, как только что введённые, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput) {
    window.MoneyInput.format(priceInput);
    window.MoneyInput.format(baseInput);
  }

  priceInput.addEventListener("input", handleInput);
  shareInput.addEventListener("input", handleInput);
  baseInput.addEventListener("input", handleInput);

  // Форма без отправки на сервер: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Очистить» чистит цену договора и долю несовершеннолетних продавцов;
  // базовый региональный тариф остаётся и в поле, и в хранилище
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      priceInput.value = "";
      shareInput.value = "";
      storageRemove(STORAGE_PRICE);
      storageRemove(STORAGE_SHARE);
      calculate();
    });
  }

  calculate();
})();
