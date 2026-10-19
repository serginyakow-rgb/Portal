/* Модуль «Калькуляторы»: «Удостоверение соглашения о выделении долей по МСК».
   Страница собирает значения полей, а по кнопке «Расчет» подбирает долю на
   каждого члена семьи и показывает три поля вывода: МСК на члена семьи,
   долю простой дробью и стоимость этой доли. В третьем столбце — показатели
   нотариального тарифа (федеральный, региональный, итого и льгота), как на
   странице тарифа за удостоверение ДКП обязательной формы. Суммы в полях
   ввода и вывода форматируются модулем money-input.js (как «Цена договора»
   в тарифе за удостоверение ДКП), целые поля принимают только цифры, а
   «Очистить» чистит все поля, кроме «Знаменатель доли (не более)» и «Базовый
   региональный тариф»: эти два значения сохраняются. Введённые значения
   хранятся в localStorage. Любое изменение поля показывает в строке статуса
   под полями вывода предупреждение о необходимости нового «Расчета»; кнопки
   «Расчет» и «Очистить» его убирают. Если знаменатель меньше числа членов
   семьи, в этой же строке при вводе появляется предупреждение об этом, а
   «Расчет» не выполняется. */
(function () {
  "use strict";

  // Ключи localStorage: у каждого поля свой, поэтому «Очистить» чистит выборочно
  var STORAGE_PRICE = "calculators.vydelenie-doley-msk.price";
  var STORAGE_CAPITAL = "calculators.vydelenie-doley-msk.capital";
  var STORAGE_MEMBERS = "calculators.vydelenie-doley-msk.members";
  var STORAGE_MINORS = "calculators.vydelenie-doley-msk.minors";
  var STORAGE_DENOMINATOR = "calculators.vydelenie-doley-msk.denominator";
  var STORAGE_BASE = "calculators.vydelenie-doley-msk.base";

  // Текст и значок сообщения об ошибке целочисленного поля
  var INTEGER_ERROR_TEXT = "Введите целое число больше нуля";
  // Сообщения кнопки «Расчет»: не хватает данных или долю подобрать нельзя
  var CALC_INCOMPLETE_TEXT = "Заполните стоимость квартиры, размер МСК, количество членов семьи и знаменатель доли";
  var CALC_SHARE_TEXT = "Не удалось подобрать долю: увеличьте знаменатель или проверьте стоимость квартиры";

  // Знаменатель меньше числа членов семьи: на всех долей не хватит —
  // проверка срабатывает при вводе в любое из этих двух полей и при «Расчете»
  var CALC_DENOMINATOR_TEXT = "Не получится подобрать долю: увеличьте знаменатель";

  // Предупреждение в строке статуса: после любого изменения полей ввода
  // показанные результаты (или их отсутствие) уже не соответствуют данным
  var CALC_DIRTY_TEXT = "Произведены изменения. Для получения правильных данных нажмите кнопку \"Расчет\"";

  // Разделитель дроби в поле «Нужно выделить долю...» — «1/9»
  var FRACTION_SEPARATOR = "/";

  // Федеральный тариф на этой странице всегда равен 500 ₽
  var FEDERAL_TARIFF = 500;

  // Потолок перебора знаменателей: защита от подвисания, если в поле
  // «Знаменатель доли (не более)» введут очень большое число. Для реальных
  // значений (десятки) перебор заканчивается намного раньше — как только
  // стоимость доли становится минимально возможной, то есть МСК + 1 ₽
  var MAX_DENOMINATOR_SEARCH = 100000;

  var form = document.getElementById("vydelenie-doley-msk-form");
  if (!form) {
    return;
  }

  var priceInput = document.getElementById("vydelenie-doley-msk-price");
  var capitalInput = document.getElementById("vydelenie-doley-msk-capital");
  var membersInput = document.getElementById("vydelenie-doley-msk-members");
  var minorsInput = document.getElementById("vydelenie-doley-msk-minors");
  var denominatorInput = document.getElementById("vydelenie-doley-msk-denominator");
  var baseInput = document.getElementById("vydelenie-doley-msk-base");
  var resetButton = document.getElementById("vydelenie-doley-msk-reset");
  var calculateButton = document.getElementById("vydelenie-doley-msk-calculate");
  var membersError = document.getElementById("vydelenie-doley-msk-members-error");
  var denominatorError = document.getElementById("vydelenie-doley-msk-denominator-error");

  // Поля вывода: заполняет «Расчет», значения только для чтения
  var outMskInput = document.getElementById("vydelenie-doley-msk-out-msk");
  var outShareInput = document.getElementById("vydelenie-doley-msk-out-share");
  var outCostInput = document.getElementById("vydelenie-doley-msk-out-cost");

  // Показатели нотариального тарифа в третьем столбце
  var outFederal = document.getElementById("vydelenie-doley-msk-out-federal");
  var outRegional = document.getElementById("vydelenie-doley-msk-out-regional");
  var outTotal = document.getElementById("vydelenie-doley-msk-out-total");
  var outBenefit = document.getElementById("vydelenie-doley-msk-out-benefit");

  var calcStatus = document.getElementById("vydelenie-doley-msk-calc-status");

  // Поля ввода по видам: ключ localStorage и (для целых) элемент сообщения
  // об ошибке. У «Из них несовершеннолетних детей» ошибки нет: 0 — допустимое
  // значение, а отрицательные и дробные числа в поле не вводятся.
  var MONEY_FIELDS = [
    { input: priceInput, key: STORAGE_PRICE },
    { input: capitalInput, key: STORAGE_CAPITAL },
    { input: baseInput, key: STORAGE_BASE }
  ];
  var INTEGER_FIELDS = [
    { input: membersInput, key: STORAGE_MEMBERS, error: membersError },
    { input: minorsInput, key: STORAGE_MINORS, error: null },
    { input: denominatorInput, key: STORAGE_DENOMINATOR, error: denominatorError }
  ];

  // Поле ввода по элементу события: null — элемент не из этого калькулятора
  function findField(fields, input) {
    for (var index = 0; index < fields.length; index += 1) {
      if (fields[index].input === input) {
        return fields[index];
      }
    }
    return null;
  }

  // Целое поле: остаются только цифры, ведущие нули отбрасываются.
  // Пустое поле и «0» числом больше нуля не являются — их проверяет
  // renderIntegerError; отрицательный знак и дробная часть не вводятся.
  function prepareInteger(input) {
    var digits = String(input ? input.value : "")
      .replace(/\D/g, "")
      .replace(/^0+(?=\d)/, "");
    if (input && digits !== input.value) {
      input.value = digits;
    }
    return digits;
  }

  // Ошибка показывается только у заполненного поля: пустое поле не мешает
  function renderIntegerError(input, element) {
    var value = String(input ? input.value : "");
    if (element) {
      element.innerHTML = value === "0" ? INTEGER_ERROR_ICON + INTEGER_ERROR_TEXT : "";
    }
  }

  // Целое положительное из поля: цифры уже отфильтрованы prepareInteger
  function readPositiveInteger(input) {
    var number = Number(String(input ? input.value : "").replace(/\D/g, ""));
    return isFinite(number) && number > 0 ? number : 0;
  }

  // Сумма в поле вывода: целые рубли с разделителями разрядов — так же, как
  // в поле «Стоимость квартиры» (формат задаёт money-input.js по data-money)
  function setMoneyOutput(input, value) {
    if (!input) {
      return;
    }
    input.value = String(Math.round(value));
    if (window.MoneyInput) {
      window.MoneyInput.format(input);
    }
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
  // Суммы этого блока читаются мягко: поле уже очищено маской ввода
  var readNumber = core.readPositiveNumber;
  var formatTariffMoney = core.formatMoney;
  var INTEGER_ERROR_ICON = core.ERROR_ICON;

  function setTariffOutput(element, value) {
    if (element) {
      element.textContent = formatTariffMoney(value);
    }
  }

  // Пока «Расчет» не выполнен (или данных не хватает), показатели тарифа
  // показывают нули — как исходные значения на странице тарифа ДКП
  function resetTariffOutputs() {
    [outFederal, outRegional, outTotal, outBenefit].forEach(function (element) {
      setTariffOutput(element, 0);
    });
  }

  // Показатели тарифа по найденной доле: федеральный тариф всегда 500 ₽,
  // льгота — база / знаменатель × числитель доли × число несовершеннолетних
  // детей (округление до целого), региональный — база минус льгота,
  // итого — федеральный плюс региональный
  function calculateTariff(base, share, denominator, minors) {
    var federal = FEDERAL_TARIFF;
    var benefit = Math.round((base / denominator) * share.numerator * minors);
    var regional = base - benefit;

    setTariffOutput(outFederal, federal);
    setTariffOutput(outRegional, regional);
    setTariffOutput(outTotal, federal + regional);
    setTariffOutput(outBenefit, benefit);
  }

  // Поля доли пусты, пока «Расчет» не выполнен или данных не хватает;
  // показатели тарифа в это время показывают нули
  function clearOutputs() {
    [outMskInput, outShareInput, outCostInput].forEach(function (input) {
      if (input) {
        input.value = "";
      }
    });
    resetTariffOutputs();
    if (calcStatus) {
      calcStatus.textContent = "";
    }
  }

  // «Расчет» и «Очистить» снова делают показанные данные актуальными: строка
  // статуса под полями вывода очищается
  function clearDirtyStatus() {
    if (calcStatus) {
      calcStatus.textContent = "";
    }
  }

  // Любое изменение поля ввода: предупреждаем в той же строке статуса, что и
  // сообщения «Расчета» о нехватке данных или невозможности подобрать долю
  function showDirtyStatus() {
    if (calcStatus) {
      calcStatus.textContent = CALC_DIRTY_TEXT;
    }
  }

  // Согласованность полей «Количество членов семьи» и «Знаменатель доли»:
  // знаменатель меньше числа членов семьи — на всех долей не хватит. Пустое
  // или нулевое поле проверку не запускает
  function isDenominatorTooSmall() {
    var members = readPositiveInteger(membersInput);
    var denominator = readPositiveInteger(denominatorInput);
    return members > 0 && denominator > 0 && denominator < members;
  }

  // Ввод в любое поле формы: сначала проверяем согласованность членов семьи и
  // знаменателя, иначе предупреждаем, что нужен новый «Расчет»
  function handleFormInput() {
    if (isDenominatorTooSmall()) {
      if (calcStatus) {
        calcStatus.textContent = CALC_DENOMINATOR_TEXT;
      }
      return;
    }
    showDirtyStatus();
  }

  // Доля a/d на каждого члена семьи: a < d ≤ limit. Нужна минимальная
  // стоимость доли, которая после округления строго больше МСК на члена семьи.
  // Знаменатели перебираются от меньшего к большему, поэтому при равной
  // стоимости остаётся более простая дробь. Перебор прекращается, как только
  // достигнута минимально возможная стоимость — МСК + 1 ₽.
  function findShare(price, mskPerMember, limit) {
    var maxDenominator = Math.min(Math.floor(limit), MAX_DENOMINATOR_SEARCH);
    var best = null;
    for (var denominator = 2; denominator <= maxDenominator; denominator += 1) {
      // Минимальный числитель, при котором P * a / d ≥ T + 0,5, то есть
      // после округления стоимость доли станет больше T. Проверка в цикле
      // страхует от погрешности вычислений с плавающей точкой
      var numerator = Math.ceil(((mskPerMember + 0.5) * denominator) / price);
      if (numerator < 1) {
        numerator = 1;
      }
      while (numerator < denominator
          && Math.round((price * numerator) / denominator) <= mskPerMember) {
        numerator += 1;
      }
      if (numerator >= denominator) {
        continue;   // доля — правильная дробь: числитель меньше знаменателя
      }
      var cost = Math.round((price * numerator) / denominator);
      if (cost <= mskPerMember) {
        continue;
      }
      if (!best || cost < best.cost) {
        best = { numerator: numerator, denominator: denominator, cost: cost };
        if (cost === mskPerMember + 1) {
          break;    // ближе к МСК на члена семьи уже не подобрать
        }
      }
    }
    return best;
  }

  // «Расчет»: сначала МСК на члена семьи, затем доля и её стоимость. Пока
  // данных нет или долю подобрать нельзя, поля доли остаются пустыми,
  // показатели тарифа — нулями, а причина показывается строкой статуса.
  // Если знаменатель меньше числа членов семьи, расчёт не выполняется
  function calculate() {
    clearOutputs();
    clearDirtyStatus();

    // Знаменатель меньше числа членов семьи: долю на каждого не подобрать —
    // оставляем пустые поля вывода и показываем причину
    if (isDenominatorTooSmall()) {
      if (calcStatus) {
        calcStatus.textContent = CALC_DENOMINATOR_TEXT;
      }
      return;
    }

    var price = readNumber(priceInput);
    var capital = readNumber(capitalInput);
    var members = readPositiveInteger(membersInput);
    var minors = readPositiveInteger(minorsInput);
    var denominator = readPositiveInteger(denominatorInput);
    var base = readNumber(baseInput);

    if (!price || !capital || !members || !denominator) {
      if (calcStatus) {
        calcStatus.textContent = CALC_INCOMPLETE_TEXT;
      }
      return;
    }

    var mskPerMember = Math.round(capital / members);
    setMoneyOutput(outMskInput, mskPerMember);

    var share = findShare(price, mskPerMember, denominator);
    if (!share) {
      if (calcStatus) {
        calcStatus.textContent = CALC_SHARE_TEXT;
      }
      return;
    }

    if (outShareInput) {
      outShareInput.value = share.numerator + FRACTION_SEPARATOR + share.denominator;
    }
    setMoneyOutput(outCostInput, share.cost);

    calculateTariff(base, share, denominator, minors);
  }

  // Суммы: значение в хранилище, показ с разделителями разрядов делает
  // money-input.js; пересчёта при вводе нет — «Расчет» запускается кнопкой
  function handleMoneyInput(event) {
    var field = findField(MONEY_FIELDS, event.target);
    if (field) {
      saveValue(field.key, field.input);
    }
  }

  // Целые поля: цифры, сохранение и сообщение об ошибке (если оно есть)
  function handleIntegerInput(event) {
    var field = findField(INTEGER_FIELDS, event.target);
    if (!field) {
      return;
    }
    prepareInteger(field.input);
    saveValue(field.key, field.input);
    renderIntegerError(field.input, field.error);
  }

  // Значения прошлого визита подставляются в поля; для сумм — сразу в формате
  // с разделителями разрядов, как в тарифе за удостоверение ДКП
  restoreValue(STORAGE_PRICE, priceInput);
  restoreValue(STORAGE_CAPITAL, capitalInput);
  restoreValue(STORAGE_MEMBERS, membersInput);
  restoreValue(STORAGE_MINORS, minorsInput);
  restoreValue(STORAGE_DENOMINATOR, denominatorInput);
  restoreValue(STORAGE_BASE, baseInput);

  if (window.MoneyInput) {
    window.MoneyInput.format(priceInput);
    window.MoneyInput.format(capitalInput);
    window.MoneyInput.format(baseInput);
  }

  prepareInteger(membersInput);
  prepareInteger(minorsInput);
  prepareInteger(denominatorInput);
  renderIntegerError(membersInput, membersError);
  renderIntegerError(denominatorInput, denominatorError);

  MONEY_FIELDS.forEach(function (field) {
    field.input.addEventListener("input", handleMoneyInput);
  });
  INTEGER_FIELDS.forEach(function (field) {
    field.input.addEventListener("input", handleIntegerInput);
  });

  // Изменение любого поля формы: проверка согласованности членов семьи и
  // знаменателя либо предупреждение, что показанные данные неактуальны.
  // Восстановление значений из localStorage и заполнение полей вывода идут
  // без события input, поэтому при открытии страницы предупреждения нет
  form.addEventListener("input", handleFormInput);

  // Форма ничего не отправляет: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  // «Расчет» заполняет поля вывода по значениям полей ввода
  if (calculateButton) {
    calculateButton.addEventListener("click", calculate);
  }

  // «Очистить» чистит стоимость квартиры, размер МСК, количество членов семьи
  // и число несовершеннолетних детей. «Знаменатель доли (не более)» и «Базовый
  // региональный тариф» остаются и в полях, и в хранилище; поля вывода и
  // сообщение «Расчета» очищаются
  if (resetButton) {
    resetButton.addEventListener("click", function () {
      priceInput.value = "";
      capitalInput.value = "";
      membersInput.value = "";
      minorsInput.value = "";
      storageRemove(STORAGE_PRICE);
      storageRemove(STORAGE_CAPITAL);
      storageRemove(STORAGE_MEMBERS);
      storageRemove(STORAGE_MINORS);
      renderIntegerError(membersInput, membersError);
      clearOutputs();
      clearDirtyStatus();
    });
  }
})();
