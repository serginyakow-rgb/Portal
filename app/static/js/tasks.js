/* Модуль «Задачи»: перетаскивание карточек между столбцами доски, модальные
   окна создания и правки карточки, подтверждение удаления и перерисовка
   чек-листа при смене типа карточки.
   Скрипт подключается на доске (tasks/index.html) и в форме карточки
   (tasks/form.html); без него обе страницы работают как обычные формы. */
(function () {
  "use strict";

  // Адрес переноса карточки: /tasks/move/{id}, тело — {status, position}
  var MOVE_URL = "/tasks/move/";

  // Сколько ждём ответа сервера на перенос, миллисекунды
  var MOVE_TIMEOUT = 8000;

  // Сколько миллисекунд после перетаскивания щелчок по карточке не открывает
  // окно правки: отпускание кнопки мыши не должно считаться щелчком
  var CLICK_AFTER_DRAG = 250;

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

  // Когда закончилось последнее перетаскивание: по этой отметке обработчик
  // щелчка отличает его от отпускания мыши после переноса
  var dragEndedAt = 0;

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
  // Сортирует карточки столбца по сроку по возрастанию — так же, как их
  // отдаёт list_board: карточки без срока уходят в конец, при одинаковых
  // сроках сохраняется прежний порядок (место, куда карточку бросили).
  // Нужна после переноса между столбцами: сервер ставит карточку на место
  // по сроку, и доска не должна показывать другой порядок до перезагрузки
  function sortColumn(column) {
    var container = column.querySelector("[data-board-cards]");
    if (!container) {
      return;
    }
    var cards = columnCards(column);
    // Порядок до сортировки: вторичный ключ при одинаковых сроках
    var order = cards.slice();
    cards.sort(function (left, right) {
      var leftDue = left.getAttribute("data-task-due") || "";
      var rightDue = right.getAttribute("data-task-due") || "";
      if (leftDue !== rightDue) {
        // Срок лежит в data-task-due как ГГГГ-ММ-ДД: строки сравнимы напрямую
        if (!leftDue) {
          return 1;
        }
        if (!rightDue) {
          return -1;
        }
        return leftDue < rightDue ? -1 : 1;
      }
      return order.indexOf(left) - order.indexOf(right);
    });
    // appendChild переносит существующие узлы: клонировать карточки не нужно
    cards.forEach(function (card) {
      container.appendChild(card);
    });
  }

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

  // Обновляет исполнителя карточки по ответу сервера: если карточку без
  // исполнителя вытащили из «На очереди», им становится авторизованный
  // сотрудник, и без этого имя менялось бы только после перезагрузки страницы.
  // Вместе с именем правится снимок полей в data-task: окно «Редактирование
  // карточки» заполняет поле «Выполняет» именно из него, и со старым снимком
  // оно показывало «Не выбран», хотя исполнитель в БД уже есть
  function applyAssignee(card, data) {
    var label = card.querySelector("[data-task-assignee]");
    if (label) {
      label.textContent = data.assignee_name || "Без исполнителя";
    }
    // assignee_id приходит в ответе всегда: null — исполнителя у карточки нет
    if (data.assignee_id === undefined) {
      return;
    }
    var payload;
    try {
      payload = JSON.parse(card.getAttribute("data-task") || "");
    } catch (error) {
      return;
    }
    if (!payload || typeof payload !== "object") {
      return;
    }
    payload.assignee_id = typeof data.assignee_id === "number" ? data.assignee_id : null;
    card.setAttribute("data-task", JSON.stringify(payload));
  }

  // Полоса прогресса в карточке: ширина заливки в процентах и её цвет.
  // Значение и цвет берём из ответа сервера, чтобы после переноса полоса
  // не расходилась с БД до перезагрузки страницы; процент считает
  // service.task_progress. Атрибуты, а не style: оформление в CSS
  function applyProgress(card, data) {
    var fill = card.querySelector(".card__progress-fill");
    if (!fill) {
      return;
    }
    var progress = typeof data.progress === "number" ? data.progress : 0;
    fill.setAttribute("width", progress + "%");
    fill.setAttribute("fill", data.assignee_color || "none");
  }

  // Обновляет метку «Задачи» в левом меню по ответу сервера. Перетаскивание
  // меняет её числа — карточка сменила столбец, а при выходе из «На очереди»
  // получила ещё и исполнителя, — а страница при этом не перезагружается.
  // Текст и подсказка повторяют разметку base.html («X | Y» и расшифровку
  // в title): сервер отдаёт только числа, оформление остаётся в одном месте.
  // Значок «срок истекает» рисует шаблон (base.html); здесь он только
  // показывается или прячется: перенос в «Готово» снимает предупреждение,
  // возврат в работу — снова включает.
  function applyMenuBadge(data) {
    var badge = document.querySelector("[data-menu-badge]");
    var due = document.querySelector("[data-menu-badge-due]");
    if (
      !badge ||
      typeof data.menu_unassigned !== "number" ||
      typeof data.menu_mine !== "number"
    ) {
      return;
    }
    var unassigned = String(data.menu_unassigned);
    var mine = String(data.menu_mine);
    badge.textContent = unassigned + " | " + mine;
    badge.setAttribute(
      "title",
      "Не распределено: " + unassigned + " · Мои на очереди и в работе: " + mine
    );
    if (due && typeof data.menu_due_soon === "number") {
      if (data.menu_due_soon > 0) {
        due.removeAttribute("hidden");
      } else {
        due.setAttribute("hidden", "");
      }
    }
  }

  // Обновляет окно «Задачи по сотрудникам» по ответу сервера. Окно рендерит
  // шаблон при загрузке страницы, поэтому после перетаскивания в «Готово»
  // (этот столбец в загрузку не входит) цифра и полоса оставались бы
  // прежними до перезагрузки. Числа приходят готовыми в assignee_counts,
  // шкалу полосы строим так же, как шаблон: доля от самого загруженного
  // сотрудника, целые проценты. Окна нет у роли «Сотрудник» — тогда panel
  // не найдена и обновлять нечего.
  function applyAssignees(data) {
    var panel = document.querySelector("[data-assignees]");
    var counts = data.assignee_counts;
    if (!panel || !counts || typeof counts !== "object") {
      return;
    }
    var items = toArray(panel.querySelectorAll("[data-assignee-id]"));
    var max = 0;
    items.forEach(function (item) {
      var count = counts[item.getAttribute("data-assignee-id")];
      if (typeof count === "number" && count > max) {
        max = count;
      }
    });
    items.forEach(function (item) {
      var count = counts[item.getAttribute("data-assignee-id")];
      count = typeof count === "number" ? count : 0;
      var label = item.querySelector("[data-assignee-count]");
      if (label) {
        label.textContent = String(count);
      }
      var fill = item.querySelector("[data-assignee-fill]");
      if (fill) {
        fill.setAttribute("width", (max ? Math.floor((count * 100) / max) : 0) + "%");
      }
    });
  }

  // Переносит карточку в выбранный столбец и отправляет позицию на сервер
  function moveCard(card, column, clientY) {
    var container = column.querySelector("[data-board-cards]");
    if (!container) {
      return;
    }
    var status = column.getAttribute("data-status") || "";
    // Столбец, откуда карточку вытащили: при смене столбца целевой столбец
    // пересортировывается по сроку — так же, как его отдаёт сервер
    var previousStatus = card.getAttribute("data-task-status") || "";
    var index = dropIndex(column, clientY);
    var reference = toArray(container.querySelectorAll(".board__card")).filter(function (item) {
      return item !== card;
    })[index] || null;

    container.insertBefore(card, reference);
    card.setAttribute("data-task-status", status);
    if (status !== previousStatus) {
      sortColumn(column);
    }
    refreshBoard();
    // Позиция для сервера — фактическое место карточки после сортировки
    var placed = columnCards(column).indexOf(card);
    persistMove(card, status, placed < 0 ? index : placed);
  }

  // Отправляет перенос на сервер. В ответе приходит исполнитель карточки:
  // если он был пуст и карточку вытащили из «На очереди», им становится
  // авторизованный сотрудник, и имя в строке карточки обновляется без
  // перезагрузки. Там же — числа метки «Задачи» в левом меню (menu_unassigned,
  // menu_mine): перенос их меняет, поэтому метку переписываем сразу.
  // Числа окна «Задачи по сотрудникам» (assignee_counts) обновляются по той же
  // причине: «Готово» в загрузку не входит, и перенос туда меняет цифру.
  // При ошибке доска перезагружается — иначе карточка осталась бы не там,
  // где её видит сервер, и следующий перенос затёр бы чужие позиции
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
        // Ошибка разбора ответа тоже приведёт к перезагрузке доски
        return response.json();
      })
      .then(function (data) {
        if (data) {
          applyAssignee(card, data);
          applyProgress(card, data);
          applyMenuBadge(data);
          applyAssignees(data);
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
      dragEndedAt = Date.now();
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

  /* ── Фильтры доски ─────────────────────────────────────────────────────── */

  // Фильтр применяется без кнопки «Обновить»: смена исполнителя — сразу,
  // поиск — при выходе из поля (Tab, клик мимо) и по Enter. Если строку не
  // меняли, лишней перезагрузки нет. Кнопка остаётся для браузера без
  // скрипта: сервер обрабатывает ту же GET-форму.
  var filterForm = document.querySelector(".tasks-filter");
  var assigneeSelect = filterForm ? filterForm.querySelector('select[name="assignee"]') : null;
  var searchField = filterForm ? filterForm.querySelector('input[name="q"]') : null;

  // Строка, которая сейчас показана на доске: с ней сравниваем поле при выходе
  var shownQuery = searchField ? searchField.value.trim() : "";

  // Отправка одна на страницу: повторный вызов (blur после Enter) игнорируется
  var filtersSent = false;

  function applyFilters() {
    if (!filterForm || filtersSent) {
      return;
    }
    filtersSent = true;
    filterForm.submit();
  }

  if (assigneeSelect) {
    assigneeSelect.addEventListener("change", applyFilters);
  }

  if (searchField) {
    // Enter: перехватываем отправку сами, чтобы blur после неё не отправил
    // форму второй раз. isComposing — Enter завершает ввод через IME, тогда
    // искать ещё рано
    searchField.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.isComposing) {
        event.preventDefault();
        applyFilters();
      }
    });

    searchField.addEventListener("focusout", function (event) {
      if (searchField.value.trim() === shownQuery) {
        return;
      }
      // Ушли на ссылку «Сброс»: она сама показывает все карточки, наша
      // перезагрузка с поиском отменила бы этот переход
      var next = event.relatedTarget;
      if (next && typeof next.closest === "function" && next.closest("a")) {
        return;
      }
      applyFilters();
    });
  }

  /* ── Модальные окна карточки: создание и правка ───────────────────────── */

  // Открывает <dialog> и ставит фокус в первое поле. Возвращает false, если
  // браузер не умеет showModal(): тогда ссылка сработает как обычная и
  // откроет страницу /tasks/create или /tasks/update/{id}
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

  // Поля окна правки ищутся по именам и data-хукам: разметка — те же части,
  // что у окна создания (_form_fields_main.html и _form_fields_extra.html),
  // поэтому список полей в JavaScript не повторяется
  function updateFields(form) {
    return {
      cardType: form.querySelector("[data-task-type]"),
      title: form.querySelector('[name="title"]'),
      contact: form.querySelector('[name="contact"]'),
      dueDate: form.querySelector('[name="due_date"]'),
      description: form.querySelector('[name="description"]'),
      assignee: form.querySelector('[name="assignee_id"]'),
      checklist: form.querySelector("[data-task-checklist]"),
      remove: form.querySelector("[data-task-remove]")
    };
  }

  // Значение списка ставится, только если такой пункт в нём есть: иначе
  // браузер оставил бы список без выбранного значения
  function setSelect(select, value) {
    if (!select || !value) {
      return;
    }
    var found = toArray(select.options).some(function (option) {
      return option.value === value;
    });
    if (found) {
      select.value = value;
    }
  }

  // Заполняет окно правки значениями карточки: JSON лежит в data-task ссылки
  // «Редактировать», адреса сохранения и удаления — рядом (data-task-form,
  // data-task-delete-url). Возвращает false, если данных нет: тогда ссылка
  // открывает страницу правки как обычно
  function fillEditDialog(dialog, opener) {
    var form = dialog.querySelector("form");
    if (!form) {
      return false;
    }
    var payload;
    try {
      payload = JSON.parse(opener.getAttribute("data-task") || "");
    } catch (error) {
      return false;
    }
    if (!payload || typeof payload !== "object") {
      return false;
    }

    form.setAttribute("action", opener.getAttribute("data-task-form") || "");
    var fields = updateFields(form);
    setSelect(fields.cardType, payload.card_type || "");
    if (fields.title) {
      fields.title.value = payload.title || "";
    }
    if (fields.contact) {
      fields.contact.value = payload.contact || "";
    }
    if (fields.dueDate) {
      fields.dueDate.value = payload.due_date || "";
    }
    if (fields.description) {
      fields.description.value = payload.description || "";
    }
    if (fields.assignee) {
      // Пустое значение — пункт «Не выбран», он есть в списке всегда
      fields.assignee.value = payload.assignee_id ? String(payload.assignee_id) : "";
    }
    if (fields.remove) {
      fields.remove.setAttribute(
        "data-task-remove",
        opener.getAttribute("data-task-delete-url") || ""
      );
    }
    // Чек-лист перерисовывается под тип карточки: отметки приходят из JSON
    if (fields.checklist) {
      var sets = checklistSets(fields.checklist);
      renderChecklist(fields.checklist, sets[payload.card_type] || [], payload.checklist || {});
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

    // Щелчок по карточке открывает окно «Редактирование карточки», а не
    // страницу /tasks/update/{id}: окно одно на всю доску, значения берутся
    // у самой карточки (data-task)
    var editOpener = closestElement(event.target, "[data-task-edit]");
    if (editOpener) {
      // Отпускание мыши после переноса — не щелчок: окно не открываем
      if (Date.now() - dragEndedAt < CLICK_AFTER_DRAG) {
        return;
      }
      var editDialog = document.getElementById("task-edit-modal");
      if (editDialog && fillEditDialog(editDialog, editOpener) && openModal(editDialog)) {
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

  // Карточку на доске можно открыть и с клавиатуры: Enter или пробел на
  // карточке (role="button" tabindex="0" в tasks/index.html)
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    var card = closestElement(event.target, "[data-task-edit]");
    if (!card) {
      return;
    }
    var dialog = document.getElementById("task-edit-modal");
    if (dialog && fillEditDialog(dialog, card) && openModal(dialog)) {
      event.preventDefault();
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
  // Действие, которое выполняется после подтверждения: отправку формы или
  // удаление из окна правки описывает тот, кто спрашивает подтверждение
  var confirmAction = null;

  function closeConfirm(accept) {
    var action = confirmAction;
    confirmAction = null;
    if (confirmDialog) {
      confirmDialog.close();
    }
    // Ожидаемое действие отправляет форму напрямую (form.submit()), минуя
    // обработчик submit — окно не открывается второй раз
    if (accept && action) {
      action();
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

    // Кнопка в цвете предупреждения — как «Удалить карточку» в окне правки:
    // все подтверждения в разделе «Задачи» уводят карточку в корзину
    var confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "btn btn--ghost btn--danger";
    confirmButton.textContent = "Удалить";
    confirmButton.addEventListener("click", function () {
      closeConfirm(true);
    });

    row.appendChild(cancelButton);
    row.appendChild(confirmButton);
    confirmDialog.appendChild(confirmText);
    confirmDialog.appendChild(row);
    // Закрытие по Escape тоже забывает ожидающее действие
    confirmDialog.addEventListener("close", function () {
      confirmAction = null;
    });
    document.body.appendChild(confirmDialog);
    return confirmDialog;
  }

  // Спрашивает подтверждение и запоминает действие. Возвращает false, если
  // браузер не умеет <dialog>: тогда вызывающий код выполняет действие сразу
  function askConfirm(message, action) {
    var dialog = ensureConfirmDialog();
    if (typeof dialog.showModal !== "function") {
      return false;
    }
    confirmAction = action;
    confirmText.textContent = message;
    dialog.showModal();
    return true;
  }

  // Формы с атрибутом data-confirm (удаление в корзину и окончательное
  // удаление) спрашивают подтверждение перед отправкой
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || typeof form.getAttribute !== "function") {
      return;
    }
    // Кнопка может нести свои подтверждение и адрес: «Удалить карточку»
    // на странице правки отправляет форму в /tasks/delete/{id} (formaction),
    // поэтому после подтверждения подменяем action — как это делает
    // обработчик [data-task-remove] для окна правки
    var submitter = event.submitter || null;
    var message = (submitter && submitter.getAttribute("data-confirm")) ||
      form.getAttribute("data-confirm");
    if (!message) {
      return;
    }
    // form.submit() отправляет форму напрямую, минуя обработчик submit —
    // окно не открывается второй раз
    var asked = askConfirm(message, function () {
      var address = submitter ? submitter.getAttribute("formaction") : "";
      if (address) {
        form.setAttribute("action", address);
      }
      form.submit();
    });
    if (asked) {
      event.preventDefault();
    }
  });

  // «Удалить карточку» в окне правки: адрес приходит от нажатой карточки
  // (data-task-delete-url → атрибут кнопки data-task-remove, его ставит
  // fillEditDialog). Кнопка не отправляет форму сама — сначала вопрос,
  // как и у кнопок «В корзину» на карточках доски
  document.addEventListener("click", function (event) {
    var removeButton = closestElement(event.target, "[data-task-remove]");
    if (!removeButton) {
      return;
    }
    var form = removeButton.form || closestElement(removeButton, "form");
    var action = removeButton.getAttribute("data-task-remove") || "";
    if (!form || !action) {
      return;
    }
    event.preventDefault();

    var send = function () {
      form.setAttribute("action", action);
      form.submit();
    };
    var titleField = form.querySelector('[name="title"]');
    var title = titleField ? titleField.value.trim() : "";
    var message = title
      ? "Убрать карточку «" + title + "» в корзину?"
      : "Убрать карточку в корзину?";
    if (!askConfirm(message, send)) {
      // Браузер без <dialog>: подтверждение пропускаем, удаляем сразу
      send();
    }
  });
})();
