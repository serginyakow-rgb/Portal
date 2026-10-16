/* Модуль «Калькуляторы»: показ сумм в полях ввода с разделителями разрядов
   («1500000» -> «1 500 000») — тем же неразрывным пробелом, что и в показателях
   (.calc__out .value). Поля помечены в шаблонах атрибутом data-money, поэтому
   скрипт работает только в калькуляторах и не затрагивает остальной портал.

   Форматирование не влияет на расчёты: и браузер (calculators.js), и сервер
   (app/modules/calculators/schemas.py) пробелы в значении игнорируют.
   Число цифр после запятой ограничивается атрибутом data-money-decimals. */
(function () {
  "use strict";

  // Разделитель разрядов — неразрывный пробел: сумма не разрывается при переносе
  var NBSP = "\u00A0";

  // Поля с форматированием: помечаются атрибутом в шаблонах калькуляторов
  var SELECTOR = "[data-money]";

  // Максимум цифр после запятой: задаётся атрибутом поля data-money-decimals
  // (например, «2» — суммы до копеек). Без атрибута дробная часть не ограничена.
  var ATTR_DECIMALS = "data-money-decimals";

  // Ограничение дробной части для конкретного поля: null — без ограничения
  function fractionLimit(input) {
    if (!input || !input.hasAttribute(ATTR_DECIMALS)) {
      return null;
    }
    var limit = parseInt(input.getAttribute(ATTR_DECIMALS), 10);
    return limit >= 0 ? limit : null;
  }

  // Отбрасывает лишние цифры дробной части: «567» при лимите 2 -> «56»
  function limitFraction(tail, limit) {
    var digits = tail.replace(/\D/g, "");
    return typeof limit === "number" ? digits.slice(0, limit) : digits;
  }

  var DIGIT = /\d/;

  // Разделители разрядов в целом числе: «1500000» -> «1 500 000»
  function groupDigits(digits) {
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  }

  // Значение поля в виде «1 500 000» или «1 500 000,50»: целая часть получает
  // разделители разрядов, дробная часть (после «,» или «.») остаётся как
  // введена. Посторонние символы отбрасываются, пустое поле остаётся пустым.
  // limit — максимум цифр после запятой (например, 2 для сумм в копейках).
  function formatValue(raw, limit) {
    var value = String(raw || "");
    var point = value.search(/[.,]/);
    var integer = point === -1 ? value : value.slice(0, point);
    var digits = integer.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
    var fraction = point === -1
      ? ""
      : value.charAt(point) + limitFraction(value.slice(point + 1), limit);
    if (!digits && !fraction) {
      return "";
    }
    return groupDigits(digits || "0") + fraction;
  }

  // Каретка встаёт так, чтобы перед ней осталось столько же цифр, сколько было
  // до форматирования: добавленные разделители её не сдвигают
  function moveCaret(input, digitsBefore) {
    var text = String(input.value || "");
    var position = 0;
    var seen = 0;
    while (position < text.length && seen < digitsBefore) {
      if (DIGIT.test(text.charAt(position))) {
        seen += 1;
      }
      position += 1;
    }
    input.setSelectionRange(position, position);
  }

  // Приводит поле к формату сумм, не сдвигая каретку относительно цифр
  function formatInput(input) {
    if (!input) {
      return;
    }
    var caret = input.selectionStart;
    var digitsBefore = typeof caret === "number"
      ? String(input.value.slice(0, caret)).replace(/\D/g, "").length
      : 0;
    var formatted = formatValue(input.value, fractionLimit(input));
    if (formatted === input.value) {
      return;
    }
    input.value = formatted;
    if (typeof caret === "number" && document.activeElement === input) {
      moveCaret(input, digitsBefore);
    }
  }

  function handleInput(event) {
    formatInput(event.target);
  }

  // Backspace и Delete на разделителе разрядов: пробел нельзя убрать отдельно —
  // форматирование вернёт его на место, поэтому разделитель удаляется вместе с
  // соседней цифрой, как если бы её стёрли одним нажатием
  function handleDeleteKey(event) {
    if (event.key !== "Backspace" && event.key !== "Delete") {
      return;
    }
    var input = event.target;
    var caret = input.selectionStart;
    if (typeof caret !== "number" || caret !== input.selectionEnd) {
      return;
    }
    var value = String(input.value || "");
    var from = caret;
    var to = caret;

    if (event.key === "Backspace") {
      while (from > 0 && value.charAt(from - 1) === NBSP) {
        from -= 1;
      }
      if (from === caret || from === 0) {
        return;          // пробела слева нет — обычное удаление символа
      }
      from -= 1;
    } else {
      while (to < value.length && value.charAt(to) === NBSP) {
        to += 1;
      }
      if (to === caret || to === value.length) {
        return;          // пробела справа нет — обычное удаление символа
      }
      to += 1;
    }

    event.preventDefault();
    input.value = value.slice(0, from) + value.slice(to);
    input.setSelectionRange(from, from);
    // Пересчёт калькулятора слушает «input»: после правки значения сообщаем об этом
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  Array.prototype.forEach.call(document.querySelectorAll(SELECTOR), function (input) {
    input.addEventListener("input", handleInput);
    input.addEventListener("change", handleInput);
    input.addEventListener("keydown", handleDeleteKey);
    formatInput(input);
  });

  // Значения могут появиться позже (значение из шаблона, localStorage): перед
  // полной загрузкой страницы нормализуем поля ещё раз
  window.addEventListener("load", function () {
    Array.prototype.forEach.call(document.querySelectorAll(SELECTOR), formatInput);
  });

  // Доступ для соседних модулей калькуляторов: например, calculators.js
  // нормализует значения, восстановленные из localStorage
  window.MoneyInput = { format: formatInput, formatValue: formatValue };
})();
