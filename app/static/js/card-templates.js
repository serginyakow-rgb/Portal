/* Настройки → «Шаблоны карточек для раздела «Задачи»: окна раздела.
   1. «Добавить шаблон» (#card-template-modal) открывает кнопка «Добавить»
      (data-modal-open="card-template-modal").
   2. «Редактирование шаблона» (#card-template-edit-modal) открывает ссылка
      «Изменить» в строке списка (data-template-edit): она несёт JSON шаблона
      (data-template) и адреса сохранения и удаления (data-template-form,
      data-template-delete-url) — скрипт заполняет окно сохранёнными данными
      и открывает его без перезагрузки страницы. Без скрипта та же ссылка —
      обычный переход на ?edit=<id>, и сервер отдаёт окно уже заполненным.
   3. «Удалить шаблон» и формы с data-confirm спрашивают подтверждение
      в своём окне (#template-confirm) вместо window.confirm(): у браузерного
      окна сверху печатается служебная строка «Подтвердите действие на сайте».
   4. Глаз в строке списка (data-template-view) показывает пункты шаблона
      в правом столбце страницы (data-template-view-panel): список собирается
      из data-template, чек-боксы отмечены и заблокированы — только чтение,
      без окна и без перезагрузки страницы.
   После ошибки проверки окно открывается сразу при загрузке
   (data-open-on-load): сервер возвращает его с введёнными значениями,
   текст ошибки виден над таблицей.
   Закрывают «Отмена» (data-modal-close), Escape и клик по подложке.
   Без скрипта список и пункты шаблонов видны, а кнопки окна не открывают. */
(function () {
  "use strict";

  var createDialog = document.getElementById("card-template-modal");
  var editDialog = document.getElementById("card-template-edit-modal");
  var confirmDialog = document.getElementById("template-confirm");

  // Браузер без <dialog>: окна не открываются, страница работает как без скрипта
  function canOpen(dialog) {
    return !!dialog && typeof dialog.showModal === "function";
  }

  // Первое поле окна: после открытия курсор сразу в названии шаблона
  function focusTitle(dialog) {
    var input = dialog.querySelector("input[name='title']");
    if (input) {
      input.focus();
    }
  }

  function openDialog(dialog) {
    if (!canOpen(dialog)) {
      return false;
    }
    if (!dialog.open) {
      dialog.showModal();
    }
    focusTitle(dialog);
    return true;
  }

  function closeDialog(dialog) {
    if (dialog) {
      dialog.close();
    }
  }

  // Клик по подложке: событие приходит на сам <dialog>, а не на форму внутри.
  // Escape окно закрывает само — это поведение <dialog>, дублировать не нужно.
  function closeOnBackdrop(dialog) {
    if (!dialog) {
      return;
    }
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        closeDialog(dialog);
      }
    });
  }

  closeOnBackdrop(createDialog);
  closeOnBackdrop(editDialog);

  /* ── Окно подтверждения удаления ──────────────────────────────────────── */

  // Форма, ждущая подтверждения, и адрес отправки из formaction нажатой кнопки
  var pendingForm = null;
  var pendingAction = null;

  var confirmText = confirmDialog
    ? confirmDialog.querySelector("[data-template-confirm-text]")
    : null;
  var confirmAccept = confirmDialog
    ? confirmDialog.querySelector("[data-template-confirm-accept]")
    : null;
  var confirmCancel = confirmDialog
    ? confirmDialog.querySelector("[data-template-confirm-cancel]")
    : null;

  function forgetPending() {
    pendingForm = null;
    pendingAction = null;
  }

  // form.submit() отправляет форму напрямую, минуя обработчик submit —
  // подтверждение не спрашивается второй раз
  function submitPending() {
    var form = pendingForm;
    var action = pendingAction;
    forgetPending();
    closeDialog(confirmDialog);
    if (!form) {
      return;
    }
    if (action) {
      form.setAttribute("action", action);
    }
    form.submit();
  }

  function askConfirm(form, message, action) {
    if (!canOpen(confirmDialog)) {
      // Подтверждение показать нечем: отправляем без вопроса, чтобы действие работало
      if (action) {
        form.setAttribute("action", action);
      }
      form.submit();
      return;
    }
    pendingForm = form;
    pendingAction = action || null;
    if (confirmText) {
      confirmText.textContent = message;
    }
    confirmDialog.showModal();
  }

  if (confirmAccept) {
    confirmAccept.addEventListener("click", submitPending);
  }
  if (confirmCancel) {
    confirmCancel.addEventListener("click", function () {
      forgetPending();
      closeDialog(confirmDialog);
    });
  }
  if (confirmDialog) {
    confirmDialog.addEventListener("close", forgetPending);
  }

  // Формы с атрибутом data-confirm (удаление шаблона) спрашивают подтверждение
  // перед отправкой; сообщение и адрес отправки берутся у нажатой кнопки
  // (event.submitter), потому что «Удалить шаблон» несёт formaction
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || typeof form.getAttribute !== "function") {
      return;
    }
    var submitter = event.submitter || null;
    var message = (submitter && submitter.getAttribute("data-confirm"))
      || form.getAttribute("data-confirm");
    if (!message) {
      return;
    }
    event.preventDefault();
    askConfirm(form, message, submitter ? submitter.getAttribute("formaction") : null);
  });

  /* ── Окно «Редактирование шаблона» ────────────────────────────────────── */

  // Строки «чек-бокс + описание» окна правки: пункты шаблона занимают первые
  // строки по порядку (пункт 1 — строка 1), остальные строки пустые
  function editRows(dialog) {
    return dialog.querySelectorAll(".checklist__item--input");
  }

  // Заполняет окно правки данными шаблона из data-template ссылки «Изменить»
  // и ставит адреса сохранения и удаления. Возвращает false, если данных нет
  function fillEditDialog(dialog, opener) {
    var form = dialog.querySelector("form");
    if (!form) {
      return false;
    }
    var payload;
    try {
      payload = JSON.parse(opener.getAttribute("data-template") || "");
    } catch (error) {
      return false;
    }
    if (!payload || typeof payload !== "object") {
      return false;
    }

    var action = opener.getAttribute("data-template-form") || "";
    form.setAttribute("action", action);

    var title = dialog.querySelector("input[name='title']");
    if (title) {
      title.value = payload.title || "";
    }

    var checks = payload.checks || [];
    var rows = editRows(dialog);
    for (var index = 0; index < rows.length; index += 1) {
      var box = rows[index].querySelector("input[type='checkbox']");
      var text = rows[index].querySelector("input[type='text']");
      if (text) {
        text.value = index < checks.length ? checks[index] : "";
      }
      if (box) {
        box.checked = index < checks.length;
      }
    }

    // «Удалить шаблон» отправляет эту же форму на адрес удаления, поэтому
    // и адрес (formaction), и текст подтверждения зависят от открытого шаблона
    var remove = dialog.querySelector("[data-template-remove]");
    if (remove) {
      remove.setAttribute("formaction", opener.getAttribute("data-template-delete-url") || "");
      remove.setAttribute("data-confirm", "Удалить шаблон «" + (payload.title || "") + "»?");
    }
    return true;
  }

  /* ── Правый столбец: пункты выбранного шаблона (только чтение) ────────── */

  // Блок, который подменяется по щелчку глаза. Разметка та же, что отдаёт
  // сервер при переходе на ?edit=<id>, поэтому список выглядит одинаково
  var viewPanel = document.querySelector("[data-template-view-panel]");

  function renderViewPanel(payload) {
    var checks = payload.checks || [];

    viewPanel.textContent = "";

    var field = document.createElement("div");
    field.className = "field";

    var title = document.createElement("label");
    title.textContent = payload.title || "";
    field.appendChild(title);

    var list = document.createElement("div");
    list.className = "checklist";

    if (checks.length === 0) {
      // Шаблон без пунктов: та же подсказка, что в серверной разметке
      var hint = document.createElement("span");
      hint.className = "panel__hint";
      hint.textContent = "Отмеченных пунктов у шаблона нет";
      list.appendChild(hint);
    }

    // Пункт отмечен и заблокирован: шаблон только показывается, менять здесь
    // нечего — правка и удаление остаются в окне «Редактирование шаблона»
    for (var index = 0; index < checks.length; index += 1) {
      var item = document.createElement("label");
      item.className = "checklist__item";

      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = true;
      box.disabled = true;

      var text = document.createElement("span");
      text.textContent = checks[index];

      item.appendChild(box);
      item.appendChild(text);
      list.appendChild(item);
    }

    field.appendChild(list);
    viewPanel.appendChild(field);
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || typeof target.closest !== "function") {
      return;
    }

    // «Изменить» в строке списка: окно заполняется сохранёнными данными
    // и открывается без перезагрузки страницы
    var editor = target.closest("[data-template-edit]");
    if (editor && editDialog) {
      if (fillEditDialog(editDialog, editor) && openDialog(editDialog)) {
        event.preventDefault();
      }
      return;
    }

    // Глаз в строке списка: в правом столбце — пункты выбранного шаблона
    var viewer = target.closest("[data-template-view]");
    if (viewer && viewPanel) {
      var shown;
      try {
        shown = JSON.parse(viewer.getAttribute("data-template") || "");
      } catch (error) {
        shown = null;
      }
      if (shown && typeof shown === "object") {
        renderViewPanel(shown);
        event.preventDefault();
      }
      return;
    }

    // «Добавить»: кнопка открывает окно «Добавить шаблон»
    var opener = target.closest("[data-modal-open]");
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute("data-modal-open") || "");
      if (dialog && openDialog(dialog)) {
        // Ссылка-открывашка не должна менять адрес страницы
        if (opener.tagName === "A") {
          event.preventDefault();
        }
      }
      return;
    }

    // «Отмена» внутри окна
    var closer = target.closest("[data-modal-close]");
    if (closer) {
      closeDialog(closer.closest("dialog"));
    }
  });

  // Окно, которое сервер вернул открытым (ошибка проверки или переход
  // по ссылке ?edit=<id> без скрипта), показываем сразу после загрузки
  var autoload = document.querySelectorAll("dialog[data-open-on-load]");
  for (var i = 0; i < autoload.length; i += 1) {
    openDialog(autoload[i]);
  }
})();
