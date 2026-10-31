/* Синхронизация раздела портала между сотрудниками: опрос состояния и подмена
   разметки фрагментом.
   Подключается на странице раздела перед его скриптом, например:
     <script src="…/js/sync.js?v=1"></script>
     <script src="…/js/tasks.js?v=15"></script>
   Раздел отдаёт два адреса (первым их сделали «Задачи»):
     GET <раздел>/state — JSON с полем version и полями раздела;
     GET <раздел>/board — фрагмент разметки и заголовок X-Section-Version.
   Разметку фрагмента собирает сервер, поэтому страница и её обновление
   показывают одно и то же; контракт описан в app/core/sync.py.
   Без скрипта страницы работают как раньше: доска, формы и кнопки серверные. */
(function () {
  "use strict";

  // Как часто спрашиваем состояние раздела, миллисекунды: 15 сотрудников
  // в локальной сети дают три запроса в секунду, ответ — несколько сотен байт
  var DEFAULT_INTERVAL = 5000;

  // Заголовок ответа фрагмента с его версией. То же имя задаёт сервер
  // (app/core/sync.py, VERSION_HEADER); fetch читает заголовки без учёта регистра
  var VERSION_HEADER = "X-Section-Version";

  // Ключ атрибута у элементов с прокруткой внутри подменяемой разметки:
  // без возврата scrollTop столбцы доски прыгали бы в начало после обновления
  var SCROLL_ATTRIBUTE = "data-sync-scroll";

  // Запрос раздела: cookie сессии нужны (credentials), кеш — только с сервера,
  // иначе браузер мог бы отдать старую версию фрагмента
  function request(url) {
    return window.fetch(url, {
      credentials: "same-origin",
      cache: "no-store"
    }).then(function (response) {
      // Сессия истекла: сервер увёл на страницу входа. Перезагружаем страницу,
      // иначе в доску попала бы разметка формы входа
      if (response.redirected) {
        window.location.reload();
        return null;
      }
      if (!response.ok) {
        throw new Error("sync-" + response.status);
      }
      return response;
    });
  }

  // Прокрутка всех элементов с data-sync-scroll: снимок до подмены —
  // значения по порядку, после подмены тот же порядок возвращает их на место
  function snapshotScroll(target) {
    var nodes = target.querySelectorAll("[" + SCROLL_ATTRIBUTE + "]");
    var values = [];
    for (var index = 0; index < nodes.length; index += 1) {
      values.push(nodes[index].scrollTop);
    }
    return values;
  }

  function restoreScroll(target, values) {
    var nodes = target.querySelectorAll("[" + SCROLL_ATTRIBUTE + "]");
    for (var index = 0; index < nodes.length && index < values.length; index += 1) {
      nodes[index].scrollTop = values[index];
    }
  }

  /* Подключает раздел к опросу.
     options:
       target           — элемент, чью разметку подменяет фрагмент (innerHTML);
       stateUrl         — адрес состояния раздела (JSON);
       fragmentUrl      — адрес фрагмента разметки (те же фильтры раздела);
       version          — версия разметки, которую сейчас показывает страница;
       versionAttribute — атрибут target, куда записывается новая версия
                          (шаблон выводит его же при загрузке страницы);
       interval         — период опроса, миллисекунды (по умолчанию 5000);
       isBusy           — функция «раздел занят»: перетаскивание, ввод. Пока она
                          возвращает true, опрос ждёт следующего тика;
       onState          — вызывается с JSON состояния на каждом опросе, даже
                          если версия не изменилась (числа меню и счётчиков);
       onFragment       — вызывается с новой версией после подмены разметки.
     Возвращает {poll}: раздел может проверить изменения сразу, не ждя тика. */
  function watch(options) {
    var target = options.target;
    if (
      !target ||
      typeof window.fetch !== "function" ||
      typeof options.stateUrl !== "string" ||
      typeof options.fragmentUrl !== "string"
    ) {
      return null;
    }

    var interval = options.interval || DEFAULT_INTERVAL;
    var version = options.version || "";
    var isBusy = options.isBusy || function () {
      return false;
    };
    var onState = options.onState || function () {};
    var onFragment = options.onFragment || function () {};

    // Флаги не дают наложиться двум опросам и подмене: ответы идут по сети
    var pollPending = false;
    var refreshPending = false;

    // Открытое окно <dialog> — сотрудник редактирует данные: подменять
    // разметку под ним нельзя, дождёмся закрытия (обработчик close ниже)
    function modalOpen() {
      return Boolean(document.querySelector("dialog[open]"));
    }

    function applyVersion(next) {
      if (!next) {
        return;
      }
      version = next;
      if (options.versionAttribute) {
        target.setAttribute(options.versionAttribute, next);
      }
    }

    // Забирает фрагмент и подменяет им разметку target. Обработчики раздела
    // висят на самом target и на document, поэтому подмена их не снимает
    function refresh() {
      if (refreshPending) {
        return;
      }
      refreshPending = true;
      request(options.fragmentUrl)
        .then(function (response) {
          if (!response) {
            return null;
          }
          var next = response.headers.get(VERSION_HEADER) || "";
          return response.text().then(function (html) {
            return { html: html, version: next };
          });
        })
        .then(function (result) {
          if (!result) {
            return;
          }
          var scroll = snapshotScroll(target);
          target.innerHTML = result.html;
          restoreScroll(target, scroll);
          applyVersion(result.version);
          onFragment(version);
        })
        .catch(function () {
          // Сеть моргнула или сервер ответил ошибкой — повторим на следующем
          // опросе: версия на странице осталась прежней, и опрос снова увидит
          // расхождение
        })
        .then(function () {
          refreshPending = false;
        });
    }

    function poll() {
      if (pollPending || refreshPending || document.hidden || modalOpen() || isBusy()) {
        return;
      }
      pollPending = true;
      request(options.stateUrl)
        .then(function (response) {
          return response ? response.json() : null;
        })
        .then(function (state) {
          if (!state) {
            return;
          }
          onState(state);
          if (typeof state.version === "string" && state.version !== version) {
            refresh();
          }
        })
        .catch(function () {
          // Молча: следующий тик повторит, страница остаётся рабочей
        })
        .then(function () {
          pollPending = false;
        });
    }

    window.setInterval(poll, interval);

    // Вернулись на вкладку — проверяем сразу, не ждём тика
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        poll();
      }
    });

    // Окно правки закрыли — сразу проверяем, не изменилась ли доска, пока оно
    // было открыто. Событие close не всплывает, поэтому слушаем на перехвате
    document.addEventListener("close", function (event) {
      var node = event.target;
      if (node && node.nodeType === 1 && node.tagName === "DIALOG") {
        poll();
      }
    }, true);

    return { poll: poll };
  }

  window.portalSync = { watch: watch };
})();
