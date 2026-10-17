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

  // Разделитель разрядов — неразрывный пробел: сумма и знак рубля не разрываются
  var NBSP = "\u00A0";

  // Текст и значок сообщения об ошибке в поле «Какая доля дарится»
  var SHARE_ERROR_TEXT = "Некорректная доля";
  var SHARE_ERROR_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>';

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

  // Стоимость объекта и региональный тариф: разделители разрядов и прочие
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

  // Доля, которая дарится: «числитель/знаменатель», оба числа — целые,
  // знаменатель не равен нулю, числитель не больше знаменателя. Результат:
  // { filled — поле не пустое, valid — долю можно применить, numerator,
  //   denominator }.
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
    // доля больше целого: в обоих случаях тариф не считается
    if (share.denominator === 0 || share.numerator > share.denominator) {
      return share;
    }
    share.valid = true;
    return share;
  }

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
