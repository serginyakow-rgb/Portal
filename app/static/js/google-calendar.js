/* Раздел «Связь с Google Календарём»: пока портал ждёт подтверждения входа
   в браузере, страница опрашивает состояние подключения и обновляется сама.
   Без скрипта раздел работает как обычная форма: результат виден после
   обновления страницы. */
(function () {
  "use strict";

  // Как часто спрашиваем состояние входа, миллисекунды
  var POLL_INTERVAL = 2000;

  // Предел опроса: вход ждёт подтверждения до 5 минут, плюс запас на ответ
  var POLL_ATTEMPTS = 160;

  var pending = document.querySelector('[data-google-connect-state="pending"]');
  if (!pending) {
    return;
  }

  var statusUrl = pending.getAttribute("data-google-connect-url");
  if (!statusUrl) {
    return;
  }

  var attempts = 0;
  var timer = window.setInterval(function () {
    attempts += 1;
    if (attempts > POLL_ATTEMPTS) {
      window.clearInterval(timer);
      return;
    }

    fetch(statusUrl, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin"
    })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (state) {
        if (!state || state.state === "pending") {
          return;
        }
        // Итог входа (успех или ошибку) показывает страница после обновления
        window.clearInterval(timer);
        window.location.reload();
      })
      .catch(function () {
        // Сеть недоступна — повторим при следующем опросе
      });
  }, POLL_INTERVAL);
})();
