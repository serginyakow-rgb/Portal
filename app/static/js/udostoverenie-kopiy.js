/* Модуль «Калькуляторы»: удостоверение копий и равнозначность документов.
   Скрипт обслуживает элементы страницы:
     - кнопка «Очистить» — очищает поля «Страниц» и «Оплачено»;
     - переключатель вида услуги под калькулятором — активной может быть только
       одна кнопка, выбранная помечена aria-pressed="true";
     - поля ввода — в таблице тарифов только целое число больше нуля; значения
       всех полей ввода сохраняются в localStorage, как в калькуляторе ДКП;
     - расчёт: ставки выбранного режима × «Страниц», «Итого» — сумма
       федерального и регионального тарифов, «Сдача» — «Итого» минус «Оплачено».
   Пересчёт выполняется после любого изменения полей и переключения режима. */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_PAGES = "calculators.udostoverenie-kopiy.pages";
  var STORAGE_PAID = "calculators.udostoverenie-kopiy.paid";
  // У тарифов ключ — префикс + внутреннее имя поля (FTRos, RTInoe, …)
  var STORAGE_TARIFF_PREFIX = "calculators.udostoverenie-kopiy.tariff.";

  var form = document.getElementById("udostoverenie-kopiy-form");
  var pagesInput = document.getElementById("udostoverenie-kopiy-pages");
  var pagesError = document.getElementById("udostoverenie-kopiy-pages-error");
  var paidInput = document.getElementById("udostoverenie-kopiy-paid");
  var resetButton = document.getElementById("udostoverenie-kopiy-reset");
  var modeGroup = document.getElementById("udostoverenie-kopiy-mode");
  var tariffInputs = document.querySelectorAll("#udostoverenie-kopiy-tariffs input");

  // Поля вывода: два readonly-поля тарифов и показатели «Итого» и «Сдача»
  var federalOutput = document.getElementById("udostoverenie-kopiy-out-federal");
  var regionalOutput = document.getElementById("udostoverenie-kopiy-out-regional");
  var totalOutput = document.getElementById("udostoverenie-kopiy-out-total");
  var changeOutput = document.getElementById("udostoverenie-kopiy-out-change");

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

  // --- Расчёт ---------------------------------------------------------------
  // Ставка за страницу по режимам: внутренние имена полей таблицы. Кнопка
  // режима хранит своё имя в data-mode.
  var MODE_RATES = {
    rosreestr: { federal: "FTRos", regional: "RTRos" },
    other: { federal: "FTInoe", regional: "RTInoe" },
    copies: { federal: "FTICopy", regional: "RTCopy" }
  };

  // Поля таблицы по внутреннему имени: по ним расчёт читает ставки режима
  var rateInputs = {};
  Array.prototype.forEach.call(tariffInputs, function (input) {
    rateInputs[input.name] = input;
  });

  // Неразрывный пробел — тот же, что в money-input.js и в показателях
  var NBSP = "\u00A0";

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

  // Сумма для показа: разделители разрядов и запятая, копейки — только если
  // они есть (0, 1 500, 1 500,50). Группировку разрядов делает money-input.js.
  function formatSum(value) {
    var rounded = Math.round(Math.abs(value) * 100) / 100;
    var text = rounded.toFixed(2).replace(".", ",");
    if (text.slice(-3) === ",00") {
      text = text.slice(0, -3);
    }
    text = window.MoneyInput ? window.MoneyInput.formatValue(text, 2) : text;
    return (value < 0 ? "−" : "") + text;
  }

  // Показатели «Итого» и «Сдача» — целые рубли с разделителями разрядов и
  // знаком рубля, как в остальных калькуляторах (округление только при выводе)
  function formatMoney(value) {
    var rounded = Math.round(value);
    var text = String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    return (rounded < 0 ? "−" : "") + text + NBSP + "₽";
  }

  // Активный режим — кнопка с aria-pressed="true"; без выбора считаем Росреестр
  function currentMode() {
    var active = modeGroup
      ? modeGroup.querySelector('.btn[aria-pressed="true"]')
      : null;
    var mode = active ? active.getAttribute("data-mode") : "";
    return MODE_RATES[mode] ? mode : "rosreestr";
  }

  // Пересчёт: «Федеральный/Региональный тариф, итого» — ставка выбранного
  // режима × число страниц, «Итого» — их сумма, «Сдача» — оплачено минус итого
  function calculate() {
    var pages = readNumber(pagesInput);
    var paid = readNumber(paidInput);
    var rates = MODE_RATES[currentMode()];

    var federal = pages * readNumber(rateInputs[rates.federal]);
    var regional = pages * readNumber(rateInputs[rates.regional]);
    var total = federal + regional;
    // «Сдача» — оплачено минус итого; пока оплата не покрыла итог, остаётся 0
    var change = Math.max(paid - total, 0);

    // Без «Страниц» считать нечего: поля тарифов остаются пустыми (placeholder «—»),
    // при введённых страницах показывается и нулевая сумма
    if (federalOutput) {
      federalOutput.value = pages ? formatSum(federal) : "";
    }
    if (regionalOutput) {
      regionalOutput.value = pages ? formatSum(regional) : "";
    }
    if (totalOutput) {
      totalOutput.textContent = formatMoney(total);
    }
    if (changeOutput) {
      changeOutput.textContent = formatMoney(change);
    }
  }

  // Выбранной остаётся только нажатая кнопка: у остальных aria-pressed="false"
  function selectMode(activeButton) {
    Array.prototype.forEach.call(modeGroup.querySelectorAll("button"), function (button) {
      button.setAttribute("aria-pressed", button === activeButton ? "true" : "false");
    });
  }

  if (modeGroup) {
    modeGroup.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button || !modeGroup.contains(button)) {
        return;          // клик по промежутку между кнопками ничего не меняет
      }
      selectMode(button);
      calculate();       // у нового режима свои ставки — суммы меняются сразу
    });
  }

  // Тарифы — целые числа больше нуля. Пропускаются только цифры (пробелы-
  // разделители разрядов при вставке отбрасываются), а минус, точка, запятая и
  // ведущий ноль отклоняются целиком: значение не «склеивается» из посторонних
  // цифр. Пустое поле ошибкой не считается — оно даёт нулевые суммы.
  // Корректное значение сразу уходит в localStorage под ключом своего поля.
  Array.prototype.forEach.call(tariffInputs, function (input) {
    var key = STORAGE_TARIFF_PREFIX + input.name;

    // Восстановленное значение тоже проверяем: в хранилище мог остаться мусор
    var saved = storageGet(key);
    if (saved !== null && /^[1-9]\d*$/.test(saved)) {
      input.value = saved;
    }
    var lastValue = input.value;

    function acceptValue() {
      var value = input.value.replace(/\s+/g, "");
      if (value !== "" && !/^[1-9]\d*$/.test(value)) {
        input.value = lastValue;      // минус, точка и ведущий ноль — отклоняем целиком
      } else {
        lastValue = value;
        if (value !== input.value) {
          input.value = value;        // «1 000» из буфера обмена → «1000»
        }
        saveValue(key, input);
      }
      calculate();                    // новая ставка сразу меняет суммы
    }

    input.addEventListener("input", acceptValue);
    // Автозаполнение может не вызвать input — проверяем ещё и по change
    input.addEventListener("change", acceptValue);
  });

  // «Страниц» и «Оплачено»: значения прошлого визита подставляются в поля, как в
  // калькуляторе ДКП, а каждое изменение сразу уходит в хранилище
  restoreValue(STORAGE_PAGES, pagesInput);
  restoreValue(STORAGE_PAID, paidInput);

  // Введённую ранее сумму показываем так же, как только что набранную, —
  // с разделителями разрядов (модуль money-input.js)
  if (window.MoneyInput && paidInput) {
    window.MoneyInput.format(paidInput);
  }

  // Расчёт при открытии страницы: восстановленные значения сразу дают суммы
  calculate();

  if (pagesInput) {
    pagesInput.addEventListener("input", function () {
      saveValue(STORAGE_PAGES, pagesInput);
      calculate();
    });
  }
  if (paidInput) {
    paidInput.addEventListener("input", function () {
      saveValue(STORAGE_PAID, paidInput);
      calculate();
    });
  }

  // «Очистить» чистит оба поля ввода и снимает сообщение об ошибке «Страниц»;
  // их ключи из хранилища тоже удаляются. Тарифы таблицы остаются — как
  // «Базовый региональный тариф» в калькуляторе ДКП.
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      pagesInput.value = "";
      paidInput.value = "";
      storageRemove(STORAGE_PAGES);
      storageRemove(STORAGE_PAID);
      if (pagesError) {
        pagesError.textContent = "";
      }
      calculate();       // без «Страниц» и «Оплачено» показатели обнуляются
    });
  }

  // Форма ничего не отправляет: Enter в поле не должен перезагружать страницу
  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
    });
  }
})();
