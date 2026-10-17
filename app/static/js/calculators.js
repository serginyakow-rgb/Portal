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

  // Текст и значок сообщения об ошибке в поле «Доля несовершеннолетних продавцов»
  var SHARE_ERROR_TEXT = "Некорректная доля";
  var SHARE_ERROR_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>';

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

  // --- localStorage: в приватном режиме браузера он может быть недоступен,
  // поэтому все обращения обёрнуты в try — калькулятор продолжает работать ---

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // Без хранилища значения просто не сохранятся до следующего визита
    }
  }

  function storageRemove(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (error) {
      // см. storageSet
    }
  }

  // Цена договора и базовый региональный тариф: разделители разрядов и прочие
  // пробелы убираем, запятую принимаем как разделитель дробной части. Пустое,
  // нечисловое и отрицательное значение дают 0 (защита от мусора в поле).
  function readNumber(input) {
    var raw = input ? String(input.value || "") : "";
    var cleaned = raw.replace(/\s/g, "").replace(",", ".");
    if (!/^\d+(?:\.\d+)?$/.test(cleaned)) {
      return 0;
    }
    var value = parseFloat(cleaned);
    return isNaN(value) ? 0 : value;
  }

  // Доля несовершеннолетних продавцов: «числитель/знаменатель», где оба числа —
  // целые неотрицательные. Результат: { filled — поле не пустое,
  // valid — долю можно применить, numerator, denominator }.
  function readShare(raw) {
    var value = String(raw || "").trim();
    var share = { filled: false, valid: false, numerator: 0, denominator: 0 };
    if (!value) {
      return share;
    }
    share.filled = true;

    var parts = value.split("/");
    if (parts.length !== 2) {
      return share;
    }
    var numerator = parts[0].trim();
    var denominator = parts[1].trim();
    if (!/^\d+$/.test(numerator) || !/^\d+$/.test(denominator)) {
      return share;
    }
    share.numerator = parseInt(numerator, 10);
    share.denominator = parseInt(denominator, 10);

    // Знаменатель 0 — деление невозможно, числитель больше знаменателя —
    // доля больше целого: в обоих случаях льгота не считается
    if (share.denominator === 0 || share.numerator > share.denominator) {
      return share;
    }
    share.valid = true;
    return share;
  }

  // Разделитель разрядов — неразрывный пробел: сумма и символ рубля не
  // разрываются при переносе строки
  var NBSP = "\u00A0";

  // Округление до целого по правилу математического округления:
  // дробная часть меньше 0,5 — отбрасывается, 0,5 и больше — вверх.
  // Значения всегда неотрицательны, поэтому Math.round даёт нужный результат.
  function roundNumber(value) {
    return Math.round(value);
  }

  // Федеральный тариф — до округления: 0,5 % цены договора, но не менее 300 ₽
  // и не более 20 000 ₽. Цена 0 (пустое или мусорное значение поля) тарифа не
  // даёт: без цены договора удостоверять нечего
  function federalTariff(price) {
    if (price <= 0) {
      return 0;
    }
    return Math.min(Math.max(price * FEDERAL_RATE, FEDERAL_MIN), FEDERAL_MAX);
  }

  // Сумма в поле вывода: целое число с разделением разрядов и символом рубля
  // в конце — 250000 => «250 000 ₽»
  function formatMoney(value) {
    var digits = String(roundNumber(value));
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + NBSP + "₽";
  }

  // Показатель в поле вывода — сумма в рублях
  function render(element, value) {
    if (element) {
      element.textContent = formatMoney(value);
    }
  }

  // Сообщение об ошибке в поле доли: показываем только у заполненного поля
  function renderShareError(visible) {
    if (shareError) {
      shareError.innerHTML = visible ? SHARE_ERROR_ICON + SHARE_ERROR_TEXT : "";
    }
  }

  // Запоминает значение поля; пустое значение из хранилища убираем
  function saveValue(key, input) {
    var value = input ? String(input.value || "").trim() : "";
    if (value) {
      storageSet(key, value);
    } else {
      storageRemove(key);
    }
  }

  // Подставляет сохранённое значение в поле ввода
  function restoreValue(key, input) {
    var saved = storageGet(key);
    if (saved !== null && input) {
      input.value = saved;
    }
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
