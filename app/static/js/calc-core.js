/* Общие помощники клиентских калькуляторов раздела «Калькуляторы».
   Подключается в шаблоне перед скриптом блока, после money-input.js:
     money-input.js → calc-core.js → <slug>.js
   Здесь только то, что одинаково нужно нескольким блокам: безопасная работа
   с localStorage, разбор чисел и долей, форматирование сумм, вывод показателей
   и сообщения об ошибке поля. Тарифы, ставки и правила конкретных калькуляторов
   остаются в их скриптах: этот модуль ничего не считает. */
(function () {
  "use strict";

  // Разделитель разрядов и отбивка знака рубля — неразрывный пробел
  var NBSP = "\u00A0";

  // Текст и значок сообщения об ошибке в поле доли
  var SHARE_ERROR_TEXT = "Некорректная доля";
  var ERROR_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" '
    + 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    + 'stroke-linejoin="round"><circle cx="12" cy="12" r="10"/>'
    + '<line x1="12" x2="12" y1="8" y2="12"/>'
    + '<line x1="12" x2="12.01" y1="16" y2="16"/></svg>';

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

  // Число из поля: разделители разрядов и прочие пробелы убираем, запятую
  // принимаем как разделитель дробной части. Пустое, нечисловое и
  // отрицательное значение дают 0 (защита от мусора в поле).
  function readNumber(input) {
    var raw = input ? String(input.value || "") : "";
    var cleaned = raw.replace(/\s/g, "").replace(",", ".");
    if (!/^\d+(?:\.\d+)?$/.test(cleaned)) {
      return 0;
    }
    var value = parseFloat(cleaned);
    return isNaN(value) ? 0 : value;
  }

  // Мягкий разбор суммы: Number понимает больше форматов записи. Нужен там,
  // где поле уже очищается маской ввода; пустое, нечисловое и отрицательное
  // значение по-прежнему дают 0.
  function readPositiveNumber(input) {
    var value = String(input ? input.value : "")
      .replace(/\s/g, "")
      .replace(",", ".");
    var number = Number(value);
    return isFinite(number) && number > 0 ? number : 0;
  }

  // Доля «числитель/знаменатель», где оба числа — целые неотрицательные.
  // Результат: { filled — поле не пустое, valid — долю можно применить,
  // numerator, denominator }.
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

  // Сумма в показателе: целые рубли с разделителями разрядов —
  // 25000 => «25 000 ₽». Округление только при выводе.
  function formatMoney(value) {
    var digits = String(Math.round(value));
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + NBSP + "₽";
  }

  // Та же сумма со знаком минус: «−1 500 ₽». Отрицательные значения бывают
  // только у «Сдачи» и разницы сумм, поэтому знак выводится отдельно.
  function formatMoneySigned(value) {
    var rounded = Math.round(value);
    var digits = String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    return (rounded < 0 ? "−" : "") + digits + NBSP + "₽";
  }

  // Сумма для поля вывода с копейками: «0», «1 500», «1 500,50». Группировку
  // разрядов делает money-input.js; без него выводится число как есть.
  function formatSum(value) {
    var rounded = Math.round(Math.abs(value) * 100) / 100;
    var text = rounded.toFixed(2).replace(".", ",");
    if (text.slice(-3) === ",00") {
      text = text.slice(0, -3);
    }
    text = window.MoneyInput ? window.MoneyInput.formatValue(text, 2) : text;
    return (value < 0 ? "−" : "") + text;
  }

  // Показатель в поле вывода — сумма в рублях
  function render(element, value) {
    if (element) {
      element.textContent = formatMoney(value);
    }
  }

  // Сообщение об ошибке в поле доли: показываем только у заполненного поля.
  // Текст можно переопределить, иконка одна на весь раздел.
  function renderShareError(element, visible, text) {
    if (element) {
      element.innerHTML = visible ? ERROR_ICON + (text || SHARE_ERROR_TEXT) : "";
    }
  }

  window.CalcCore = {
    NBSP: NBSP,
    ERROR_ICON: ERROR_ICON,
    storageGet: storageGet,
    storageSet: storageSet,
    storageRemove: storageRemove,
    saveValue: saveValue,
    restoreValue: restoreValue,
    readNumber: readNumber,
    readPositiveNumber: readPositiveNumber,
    readShare: readShare,
    formatMoney: formatMoney,
    formatMoneySigned: formatMoneySigned,
    formatSum: formatSum,
    render: render,
    renderShareError: renderShareError
  };
})();
