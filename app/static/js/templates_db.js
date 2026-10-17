/* Модуль «База данных»: копирование текста заготовок, поиск по Tab при выходе
   из полей поиска и подтверждение удаления. */
(function () {
  "use strict";

  // Сколько миллисекунд кнопка показывает галочку «Скопировано»
  var COPY_MARK_TIMEOUT = 1500;

  // Иконки кнопки копирования: буфер обмена и подтверждение
  var ICON_COPY = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>';
  var ICON_DONE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  // Запасной способ копирования: Clipboard API недоступен при работе портала по http://
  function legacyCopy(text) {
    var helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "readonly");
    // Вспомогательное поле держим за пределами окна, чтобы оно не мешало пользователю
    helper.style.position = "fixed";
    helper.style.top = "-1000px";
    document.body.appendChild(helper);
    helper.select();
    var copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    document.body.removeChild(helper);
    if (!copied) {
      throw new Error("copy-failed");
    }
  }

  // Кладёт текст в буфер обмена: сначала штатным API, затем запасным способом
  function writeText(text) {
    if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      try {
        legacyCopy(text);
        resolve();
      } catch (error) {
        reject(error);
      }
    });
  }

  // Показывает на кнопке галочку «Скопировано» и возвращает её значок обратно
  function markCopied(button) {
    if (!button) {
      return;
    }
    var icon = button.querySelector("svg");
    if (!icon) {
      return;
    }
    var original = icon.outerHTML;
    var title = button.getAttribute("title");
    icon.outerHTML = ICON_DONE;
    button.setAttribute("title", "Скопировано");
    window.setTimeout(function () {
      var current = button.querySelector("svg");
      if (current) {
        current.outerHTML = original;
      }
      button.setAttribute("title", title || "Скопировать текст в буфер обмена");
    }, COPY_MARK_TIMEOUT);
  }

  // Копирует текст заготовки по её идентификатору
  function copyToClipboard(blockId, button) {
    var source = document.getElementById("block-body-" + blockId);
    if (!source) {
      return;
    }
    writeText(source.textContent.trim()).then(
      function () {
        markCopied(button);
      },
      function () {
        window.alert("Скопировать текст не удалось: выделите его и нажмите Ctrl+C.");
      }
    );
  }

  // Клик по кнопке с атрибутом data-copy-target копирует текст заготовки
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }
    var sourceId = button.getAttribute("data-copy-target") || "";
    var prefix = "block-body-";
    if (sourceId.indexOf(prefix) !== 0) {
      return;
    }
    event.preventDefault();
    copyToClipboard(sourceId.slice(prefix.length), button);
  });

  // Задержка одиночного клика по пункту раздела — она даёт шанс двойному клику
  var SECTION_CLICK_DELAY = 250;
  var sectionClickTimer = null;

  // Переход по пункту раздела: кнопка отправляет свою форму, ссылка — переходит по href
  function followLink(element) {
    var form = element.form;
    if (form) {
      form.submit();
      return;
    }
    window.location.assign(element.getAttribute("href"));
  }

  // Одиночный клик по пункту раздела открывает список его карточек
  document.addEventListener("click", function (event) {
    var row = event.target.closest("[data-section-edit] .menu__item");
    if (!row || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) {
      return;
    }
    event.preventDefault();
    if (sectionClickTimer !== null) {
      window.clearTimeout(sectionClickTimer);
    }
    sectionClickTimer = window.setTimeout(function () {
      sectionClickTimer = null;
      followLink(row);
    }, SECTION_CLICK_DELAY);
  });

  // Двойной клик по пункту раздела открывает раздел на редактирование
  document.addEventListener("dblclick", function (event) {
    var card = event.target.closest("[data-section-edit]");
    if (!card) {
      return;
    }
    // Кнопки-действия карточки («Редактировать», «Удалить») обрабатывают клик сами;
    // сам пункт раздела — кнопка .menu__item, поэтому двойной клик по нему не отсекается
    if (event.target.closest(".btn, [data-confirm]")) {
      return;
    }
    if (sectionClickTimer !== null) {
      window.clearTimeout(sectionClickTimer);
      sectionClickTimer = null;
    }
    window.location.assign(card.getAttribute("data-section-edit"));
  });

  // Поиск в «Базе данных» запускается и при выходе из полей поиска по клавише Tab,
  // чтобы не тянуться к кнопке «Найти». Кнопка и Enter работают как раньше: их
  // обрабатывает сама форма (method="get"), этот способ мы не переопределяем.
  function isSearchField(element) {
    return !!element && typeof element.hasAttribute === "function" &&
      element.hasAttribute("data-search-field");
  }

  // Метка «клавиша Tab нажата» отличает уход по Tab от ухода по клику мышью
  var tabPressed = false;

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Tab") {
      return;
    }
    // Ctrl+Tab и Alt+Tab переключают окна браузера — поиск запускать не нужно
    tabPressed = !event.ctrlKey && !event.altKey && !event.metaKey;
  });

  // Страховка: если фокус ушёл мимо страницы, метка снимется по отпусканию клавиши
  document.addEventListener("keyup", function (event) {
    if (event.key === "Tab") {
      tabPressed = false;
    }
  });

  // Выход из любого поля поиска по Tab (Tab и Shift+Tab) отправляет форму так же,
  // как кнопка «Найти»: уходят условия, заполненные на странице в этот момент
  document.addEventListener("focusout", function (event) {
    if (!tabPressed) {
      return;
    }
    tabPressed = false;

    var field = event.target;
    if (!isSearchField(field)) {
      return;
    }
    var form = field.form;
    if (!form) {
      return;
    }
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });


  // Окно подтверждения показываем сами: у браузерного window.confirm() сверху
  // печатается служебная строка «Подтвердите действие на сайте 127.0.0.1»
  var confirmDialog = null;
  var confirmDialogText = null;
  var confirmPendingForm = null;

  // Создаёт окно подтверждения при первом обращении; дальше окно переиспользуется
  function ensureConfirmDialog() {
    if (confirmDialog) {
      return confirmDialog;
    }
    confirmDialog = document.createElement("dialog");
    confirmDialog.className = "card";
    confirmDialog.setAttribute("aria-label", "Подтверждение действия");

    confirmDialogText = document.createElement("p");
    confirmDialogText.className = "card__title";

    var row = document.createElement("div");
    row.className = "calc__row";

    // Первой в фокусе оказывается «Отмена»: удаление не сработает по Enter случайно
    var cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "btn btn--ghost";
    cancelButton.textContent = "Отмена";
    cancelButton.addEventListener("click", closeConfirmDialog);

    var confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "btn btn--primary";
    confirmButton.textContent = "Удалить";
    confirmButton.addEventListener("click", submitConfirmedForm);

    row.appendChild(cancelButton);
    row.appendChild(confirmButton);
    confirmDialog.appendChild(confirmDialogText);
    confirmDialog.appendChild(row);
    // Окно закрывается и по Escape — тогда просто забываем ожидающую форму
    confirmDialog.addEventListener("close", function () {
      confirmPendingForm = null;
    });
    document.body.appendChild(confirmDialog);
    return confirmDialog;
  }

  function closeConfirmDialog() {
    confirmPendingForm = null;
    if (confirmDialog) {
      confirmDialog.close();
    }
  }

  // form.submit() отправляет форму напрямую, минуя обработчик submit — окно не повторяется
  function submitConfirmedForm() {
    var form = confirmPendingForm;
    confirmPendingForm = null;
    if (confirmDialog) {
      confirmDialog.close();
    }
    if (form) {
      form.submit();
    }
  }

  function openConfirmDialog(form, message) {
    ensureConfirmDialog();
    if (typeof confirmDialog.showModal !== "function") {
      // Браузер без <dialog>: подтверждение пропускаем, чтобы системное окно не появлялось
      form.submit();
      return;
    }
    confirmPendingForm = form;
    confirmDialogText.textContent = message;
    confirmDialog.showModal();
  }

  // Формы с атрибутом data-confirm спрашивают подтверждение перед отправкой
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || typeof form.getAttribute !== "function") {
      return;
    }
    var message = form.getAttribute("data-confirm");
    if (!message) {
      return;
    }
    event.preventDefault();
    openConfirmDialog(form, message);
  });

  // Функцию можно вызвать и напрямую: copyToClipboard(12)
  window.copyToClipboard = copyToClipboard;
  window.templatesDbIcons = { copy: ICON_COPY, done: ICON_DONE };
})();
