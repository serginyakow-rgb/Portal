/* Модуль «Задачи»: перетаскивание карточек между столбцами доски, модальное
   окно создания карточки, подтверждение удаления и перерисовка чек-листа
   при смене типа карточки.
   Скрипт подключается на доске (tasks/index.html) и в форме карточки
   (tasks/form.html); без него обе страницы работают как обычные формы. */
(function () {
  "use strict";

  // Адрес переноса карточки: /tasks/move/{id}, тело — {status, position}
  var MOVE_URL = "/tasks/move/";

  // Сколько ждём ответа сервера на перенос, миллисекунды
  var MOVE_TIMEOUT = 8000;

  function toArray(collection) {
    return Array.prototype.slice.call(collection);
  }

  // closest() есть только у элементов: клик по текстовому узлу не должен падать
  function closestElement(node, selector) {
    return node && node.nodeType === 1 && node.closest ? node.closest(selector) : null;
  }

  /* ── Доска: перетаскивание карточек ────────────────────────────────────── */

  var board = document.querySelector("[data-board]");
  var draggedCard = null;

  // Карточки столбца в порядке отображения
  function columnCards(column) {
    return toArray(column.querySelectorAll(".board__card"));
  }

  // Пересчитывает счётчик столбца и позиции карточек по их месту в DOM:
  // сервис нумерует позиции подряд (0..n-1), поэтому после переноса
  // достаточно перечитать порядок элементов
  function refreshBoard() {
    toArray(document.querySelectorAll("[data-board-column]")).forEach(function (column) {
      var cards = columnCards(column);
      var counter = column.querySelector(".board__count");
      if (counter) {
        counter.textContent = String(cards.length);
      }
      // Подсказка «Карточек нет» показывается только у пустого столбца
      var empty = column.querySelector("[data-board-empty]");
      if (empty) {
        empty.hidden = cards.length > 0;
      }
      cards.forEach(function (card, index) {
        card.setAttribute("data-task-position", String(index));
      });
    });
  }

  // Индекс вставки по вертикали курсора: перед первой карточкой, чья середина
  // ниже курсора; если такой нет — в конец столбца. Перетаскиваемая карточка
  // в расчёт не входит, иначе позиция съезжала бы на единицу
  function dropIndex(column, clientY) {
    var cards = columnCards(column).filter(function (card) {
      return card !== draggedCard;
    });
    for (var index = 0; index < cards.length; index += 1) {
      var rect = cards[index].getBoundingClientRect();
      if (clientY < rect.top + rect.height / 2) {
        return index;
      }
    }
    return cards.length;
  }

  // Переносит карточку в выбранный столбец и отправляет позицию на сервер
  function moveCard(card, column, clientY) {
    var container = column.querySelector("[data-board-cards]");
    if (!container) {
      return;
    }
    var status = column.getAttribute("data-status") || "";
    var index = dropIndex(column, clientY);
    var reference = toArray(container.querySelectorAll(".board__card")).filter(function (item) {
      return item !== card;
    })[index] || null;

    container.insertBefore(card, reference);
    card.setAttribute("data-task-status", status);
    refreshBoard();
    persistMove(card, status, index);
  }

  // Отправляет перенос на сервер. Ответ короткий ({"ok": true}); при ошибке
  // доска перезагружается — иначе карточка осталась бы не там, где её видит
  // сервер, и следующий перенос затёр бы чужие позиции
  function persistMove(card, status, position) {
    var taskId = card.getAttribute("data-task-id") || "";
    if (!taskId || typeof window.fetch !== "function") {
      window.location.reload();
      return;
    }
    var controller = typeof window.AbortController === "function" ? new window.AbortController() : null;
    var timer = controller
      ? window.setTimeout(function () {
          controller.abort();
        }, MOVE_TIMEOUT)
      : null;

    window
      .fetch(MOVE_URL + encodeURIComponent(taskId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: status, position: position }),
        signal: controller ? controller.signal : undefined,
        credentials: "same-origin"
      })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("move-failed-" + response.status);
        }
      })
      .catch(function () {
        window.location.reload();
      })
      .then(function () {
        if (timer) {
          window.clearTimeout(timer);
        }
      });
  }

  if (board) {
    // Начало перетаскивания: запоминаем карточку и кладём id в dataTransfer —
    // без данных Firefox не начинает drag
    board.addEventListener("dragstart", function (event) {
      var card = closestElement(event.target, ".board__card");
      if (!card) {
        return;
      }
      draggedCard = card;
      card.classList.add("is-dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.getAttribute("data-task-id") || "");
      }
    });

    // Конец перетаскивания (в том числе отменённого по Escape): снимаем подсветку
    board.addEventListener("dragend", function (event) {
      var card = closestElement(event.target, ".board__card");
      if (card) {
        card.classList.remove("is-dragging");
      }
      draggedCard = null;
      toArray(board.querySelectorAll("[data-board-cards]")).forEach(function (container) {
        container.classList.remove("is-over");
      });
    });

    // Разрешаем бросок только над приёмником столбца: без preventDefault
    // браузер считает элемент недопустимой целью и событие drop не приходит
    board.addEventListener("dragover", function (event) {
      if (!draggedCard) {
        return;
      }
      var container = closestElement(event.target, "[data-board-cards]");
      if (!container) {
        return;
      }
      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "move";
      }
      container.classList.add("is-over");
    });

    // Подсветку снимаем только при выходе за пределы приёмника, а не при
    // переходе курсора на карточку внутри него
    board.addEventListener("dragleave", function (event) {
      var container = closestElement(event.target, "[data-board-cards]");
      if (!container) {
        return;
      }
      if (event.relatedTarget && container.contains(event.relatedTarget)) {
        return;
      }
      container.classList.remove("is-over");
    });

    board.addEventListener("drop", function (event) {
      var card = draggedCard;
      var column = closestElement(event.target, "[data-board-column]");
      draggedCard = null;
      toArray(board.querySelectorAll("[data-board-cards]")).forEach(function (container) {
        container.classList.remove("is-over");
      });
      if (!card) {
        return;
      }
      card.classList.remove("is-dragging");
      if (!column) {
        return;
      }
      event.preventDefault();
      moveCard(card, column, event.clientY);
    });
  }

  /* ── Модальное окно создания карточки ──────────────────────────────────── */

  // Открывает <dialog> и ставит фокус в первое поле. Возвращает false, если
  // браузер не умеет showModal(): тогда ссылка сработает как обычная и
  // откроет страницу /tasks/create
  function openModal(dialog) {
    if (typeof dialog.showModal !== "function") {
      return false;
    }
    dialog.showModal();
    var firstField = dialog.querySelector("input:not([type=hidden]), select, textarea");
    if (firstField) {
      firstField.focus();
    }
    return true;
  }

  document.addEventListener("click", function (event) {
    // Кнопка «Новая карточка» — ссылка на /tasks/create, скрипт её перехватывает
    var opener = closestElement(event.target, "[data-modal-open]");
    if (opener) {
      var modalId = opener.getAttribute("data-modal-open") || "";
      var dialog = modalId ? document.getElementById(modalId) : null;
      if (dialog && openModal(dialog)) {
        event.preventDefault();
      }
      return;
    }

    // Кнопки «Закрыть» и «Отмена» внутри окна
    var closer = closestElement(event.target, "[data-modal-close]");
    if (closer) {
      var ownDialog = closer.closest("dialog");
      if (ownDialog) {
        ownDialog.close();
      }
      return;
    }

    // Клик по затемнённой подложке: цель совпадает с самим окном
    if (closestElement(event.target, "dialog.modal") === event.target) {
      event.target.close();
    }
  });


  /* ── Чек-лист карточки ────────────────────────────────────────────────── */

  // Наборы пунктов приходят из схемы (CARD_TYPE_CHECKLISTS) через атрибут
  // data-task-checklists: список пунктов в JavaScript не дублируется
  function checklistSets(container) {
    var raw = container.getAttribute("data-task-checklists") || "{}";
    try {
      var sets = JSON.parse(raw);
      return sets && typeof sets === "object" ? sets : {};
    } catch (error) {
      return {};
    }
  }

  // Отмеченные сейчас пункты — их сохраняем при смене типа карточки
  function checkedItems(container) {
    var checked = {};
    toArray(container.querySelectorAll('input[type="checkbox"]')).forEach(function (box) {
      if (box.checked) {
        checked[box.value] = true;
      }
    });
    return checked;
  }

  // Перерисовывает пункты под выбранный тип. Отметки, которых нет в новом
  // наборе, отбрасываются — так же поступает схема TaskCreate на сервере
  function renderChecklist(container, items, checked) {
    container.textContent = "";
    if (!items || items.length === 0) {
      var hint = document.createElement("span");
      hint.className = "panel__hint";
      hint.textContent = "У этого типа карточки чек-листа нет";
      container.appendChild(hint);
      return;
    }
    items.forEach(function (item) {
      var label = document.createElement("label");
      label.className = "checklist__item";

      var box = document.createElement("input");
      box.type = "checkbox";
      box.name = "checklist";
      box.value = item;
      box.checked = Boolean(checked[item]);

      var text = document.createElement("span");
      text.textContent = item;

      label.appendChild(box);
      label.appendChild(text);
      container.appendChild(label);
    });
  }

  // Смена типа карточки перерисовывает чек-лист её формы
  function bindChecklist(select) {
    var form = select.form || select.closest("form");
    var container = form ? form.querySelector("[data-task-checklist]") : null;
    if (!container) {
      return;
    }
    var sets = checklistSets(container);
    select.addEventListener("change", function () {
      renderChecklist(container, sets[select.value] || [], checkedItems(container));
    });
  }

  toArray(document.querySelectorAll("[data-task-type]")).forEach(bindChecklist);

  /* ── Подтверждение удаления ───────────────────────────────────────────── */

  // Своё окно вместо window.confirm(): у системного окна сверху печатается
  // служебная строка «Подтвердите действие на сайте 127.0.0.1». Приём тот же,
  // что в js/templates_db.js, но модуль «Задачи» от него не зависит.
  var confirmDialog = null;
  var confirmText = null;
  var confirmPendingForm = null;

  function closeConfirm(accept) {
    var form = confirmPendingForm;
    confirmPendingForm = null;
    if (confirmDialog) {
      confirmDialog.close();
    }
    // form.submit() отправляет форму напрямую, минуя обработчик submit —
    // окно не открывается второй раз
    if (accept && form) {
      form.submit();
    }
  }

  // Окно создаётся при первом обращении и дальше переиспользуется
  function ensureConfirmDialog() {
    if (confirmDialog) {
      return confirmDialog;
    }
    confirmDialog = document.createElement("dialog");
    confirmDialog.className = "modal modal--confirm";
    confirmDialog.setAttribute("aria-label", "Подтверждение действия");

    confirmText = document.createElement("p");
    confirmText.className = "card__title";

    var row = document.createElement("div");
    row.className = "calc__row";

    // Первой в фокусе оказывается «Отмена»: случайный Enter ничего не удалит
    var cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "btn btn--ghost";
    cancelButton.textContent = "Отмена";
    cancelButton.addEventListener("click", function () {
      closeConfirm(false);
    });

    var confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "btn btn--primary";
    confirmButton.textContent = "Удалить";
    confirmButton.addEventListener("click", function () {
      closeConfirm(true);
    });

    row.appendChild(cancelButton);
    row.appendChild(confirmButton);
    confirmDialog.appendChild(confirmText);
    confirmDialog.appendChild(row);
    // Закрытие по Escape тоже забывает ожидающую форму
    confirmDialog.addEventListener("close", function () {
      confirmPendingForm = null;
    });
    document.body.appendChild(confirmDialog);
    return confirmDialog;
  }

  // Формы с атрибутом data-confirm (удаление в корзину и окончательное
  // удаление) спрашивают подтверждение перед отправкой
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || typeof form.getAttribute !== "function") {
      return;
    }
    var message = form.getAttribute("data-confirm");
    if (!message) {
      return;
    }
    var dialog = ensureConfirmDialog();
    if (typeof dialog.showModal !== "function") {
      // Браузер без <dialog>: подтверждение пропускаем, форма уходит сразу
      return;
    }
    event.preventDefault();
    confirmPendingForm = form;
    confirmText.textContent = message;
    dialog.showModal();
  });
})();
