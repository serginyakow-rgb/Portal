/* Модуль «Калькуляторы»: расчёт и сдача. Двенадцать полей ввода сумм
   складываются в поле «Итого», а «Сдача» — это «Оплачено» минус «Итого».
   Считает браузер: суммы обновляются при каждом изменении полей и показываются
   с разделителями разрядов (модуль money-input.js), введённые значения
   хранятся в localStorage.
   Enter в поле переводит к следующему полю — так же, как Tab. */
(function () {
  "use strict";

  // Количество полей таблицы: столько же строк выводит шаблон
  var SLOTS = 12;

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит всё,
  // а восстановление не зависит от порядка заполнения
  var STORAGE_PREFIX = "calculators.raschet-i-sdacha.amount";

  // «Оплачено» вводится вручную, поэтому у него отдельный ключ хранилища
  var PAID_KEY = "calculators.raschet-i-sdacha.paid";

  var form = document.getElementById("raschet-i-sdacha-form");
  if (!form) {
    return;
  }

  var totalInput = document.getElementById("raschet-i-sdacha-out-total");
  var paidInput = document.getElementById("raschet-i-sdacha-paid");
  var changeInput = document.getElementById("raschet-i-sdacha-out-change");
  var resetButton = document.getElementById("raschet-i-sdacha-reset");

  // Поля таблицы в порядке строк: Enter идёт к следующему полю этого списка
  var amountInputs = [];
  for (var number = 1; number <= SLOTS; number += 1) {
    var input = document.getElementById("raschet-i-sdacha-amount-" + number);
    if (input) {
      amountInputs.push(input);
    }
  }

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

  // Сумма из поля: разделители разрядов и прочие пробелы убираем, запятую
  // принимаем как разделитель дробной части. Пустое, нечисловое и
  // отрицательное значение дают 0 (защита от мусора в поле).
  function readNumber(field) {
    var raw = field ? String(field.value || "") : "";
    var cleaned = raw.replace(/\s/g, "").replace(",", ".");
    if (!/^\d+(?:\.\d+)?$/.test(cleaned)) {
      return 0;
    }
    var value = parseFloat(cleaned);
    return isNaN(value) ? 0 : value;
  }

  // Итог показывается в том же формате, что «Цена договора»: разделители
  // разрядов и запятая, копейки — только если они есть (0, 1 500, 1 500,50).
  // Группировку разрядов делает money-input.js — своя логика не нужна.
  function formatSum(value) {
    var text = (Math.round(value * 100) / 100).toFixed(2).replace(".", ",");
    if (text.slice(-3) === ",00") {
      text = text.slice(0, -3);
    }
    return window.MoneyInput ? window.MoneyInput.formatValue(text, 2) : text;
  }

  // Итого — сумма всех полей таблицы, округлённая до копеек; сдача — оплачено
  // минус итого. Отрицательной сдачи не бывает: пока оплата не покрыла итог,
  // в поле остаётся 0.
  function calculate() {
    var total = 0;
    amountInputs.forEach(function (field) {
      total += readNumber(field);
    });
    total = Math.round(total * 100) / 100;
    if (totalInput) {
      totalInput.value = formatSum(total);
    }
    if (changeInput) {
      var change = Math.round((readNumber(paidInput) - total) * 100) / 100;
      changeInput.value = formatSum(change > 0 ? change : 0);
    }
  }

  // Запоминает значения всех полей; пустое значение из хранилища убираем
  function saveValues() {
    amountInputs.forEach(function (field, index) {
      var key = STORAGE_PREFIX + (index + 1);
      var value = String(field.value || "").trim();
      if (value) {
        storageSet(key, value);
      } else {
        storageRemove(key);
      }
    });
    if (paidInput) {
      var paid = String(paidInput.value || "").trim();
      if (paid) {
        storageSet(PAID_KEY, paid);
      } else {
        storageRemove(PAID_KEY);
      }
    }
  }

  // Подставляет значения прошлого визита в поля таблицы
  function restoreValues() {
    amountInputs.forEach(function (field, index) {
      var saved = storageGet(STORAGE_PREFIX + (index + 1));
      if (saved !== null) {
        field.value = saved;
      }
    });
    if (paidInput) {
      var savedPaid = storageGet(PAID_KEY);
      if (savedPaid !== null) {
        paidInput.value = savedPaid;
      }
    }
  }

  // Любое изменение поля: значения сразу в хранилище, затем пересчёт итога
  function handleInput() {
    saveValues();
    calculate();
  }

  // Enter в поле — переход к следующему полю, как Tab. На последнем поле
  // переходить некуда: Enter остаётся без действия, но форму не отправляет.
  function handleKeydown(event) {
    if (event.key !== "Enter") {
      return;
    }
    var index = amountInputs.indexOf(event.target);
    if (index === -1) {
      return;
    }
    event.preventDefault();
    var next = amountInputs[index + 1];
    if (next) {
      next.focus();
      next.select();
    }
  }

  restoreValues();

  // Восстановленные суммы показываем так же, как только что введённые, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput) {
    amountInputs.forEach(function (field) {
      window.MoneyInput.format(field);
    });
    if (paidInput) {
      window.MoneyInput.format(paidInput);
    }
  }

  amountInputs.forEach(function (field) {
    field.addEventListener("input", handleInput);
  });
  if (paidInput) {
    paidInput.addEventListener("input", handleInput);
  }

  form.addEventListener("keydown", handleKeydown);

  // Форма без отправки на сервер: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Очистить» чистит все поля таблицы и обнуляет «Итого»
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      amountInputs.forEach(function (field, index) {
        field.value = "";
        storageRemove(STORAGE_PREFIX + (index + 1));
      });
      if (paidInput) {
        paidInput.value = "";
        storageRemove(PAID_KEY);
      }
      calculate();
      if (amountInputs.length) {
        amountInputs[0].focus();
      }
    });
  }

  calculate();
})();
