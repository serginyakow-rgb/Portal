/* Раздел «Настройки → Резервное копирование»: подтверждение восстановления.
   Своё окно вместо window.confirm(): у браузерного сверху печатается служебная
   строка «Подтвердите действие на сайте 127.0.0.1», а правила проекта требуют
   свой диалог. Без скрипта раздел работает как обычные формы — восстановление
   начинается сразу после нажатия кнопки. */
(function () {
  "use strict";

  var dialog = document.getElementById("backup-confirm");
  if (!dialog) {
    return;
  }

  var textNode = dialog.querySelector("[data-backup-confirm-text]");
  var cancelButton = dialog.querySelector("[data-backup-confirm-cancel]");
  var acceptButton = dialog.querySelector("[data-backup-confirm-accept]");
  // Форма, ожидающая подтверждения
  var pendingForm = null;

  function closeDialog() {
    pendingForm = null;
    if (typeof dialog.close === "function") {
      dialog.close();
    }
  }

  // form.submit() отправляет форму напрямую, минуя обработчик submit — окно
  // не показывается второй раз. Файл, выбранный для восстановления, остаётся
  // в форме: отправляется именно эта форма.
  function submitPending() {
    var form = pendingForm;
    pendingForm = null;
    if (typeof dialog.close === "function") {
      dialog.close();
    }
    if (form) {
      form.submit();
    }
  }

  if (cancelButton) {
    cancelButton.addEventListener("click", closeDialog);
  }
  if (acceptButton) {
    acceptButton.addEventListener("click", submitPending);
  }

  // Escape и кнопка закрытия: просто забываем ожидающую форму
  dialog.addEventListener("close", function () {
    pendingForm = null;
  });

  // Клик по затемнённой подложке: цель совпадает с самим окном
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      closeDialog();
    }
  });

  // Формы и кнопки с data-confirm спрашивают подтверждение перед отправкой.
  // Сообщение берётся у нажатой кнопки, затем у формы — как в tasks.js
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
    // Браузер без <dialog>: подтверждение пропускаем, чтобы не потерять отправку
    if (typeof dialog.showModal !== "function") {
      return;
    }
    event.preventDefault();
    pendingForm = form;
    if (textNode) {
      textNode.textContent = message;
    }
    dialog.showModal();
  });
})();
