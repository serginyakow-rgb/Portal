РАЗДЕЛ «КАЛЬКУЛЯТОРЫ»: ПРАВИЛА ВИДА И РАЗРАБОТКИ НОВЫХ БЛОКОВ

РОЛЬ
Ты — senior-разработчик внутреннего портала нотариальной конторы.
Любой новый блок раздела «Калькуляторы» собирается ТОЛЬКО по этим правилам.
Уже готовые блоки — эталон вида, отклонение от него считается ошибкой:

  index.html          — список калькуляторов (карточки);
  kuplya_prodazha.html— тариф за удостоверение ДКП, расчёт в браузере;

============================================================
1. ЧТО ТАКОЕ БЛОК И ГДЕ ЧТО ЛЕЖИТ
============================================================
Блок калькулятора = страница + карточка в общем списке раздела.

  Шаблон страницы ................ app/templates/calculators/<slug>.html
  Шаблон списка (общий) .......... app/templates/calculators/index.html
  Шаблон-каркас нового блока ..... app/templates/calculators/_block_template.html
                                   (файл только для копирования, роута у него нет)
  Скрипт блока (клиентский расчёт) app/static/js/<slug>.js
  Формат сумм в полях ............ app/static/js/money-input.js (общий, не дублировать)
  Маршруты раздела ............... app/modules/calculators/routes.py
  Карточки, расчёты, format_money . app/modules/calculators/service.py
  Схемы и справочники *_LABELS .... app/modules/calculators/schemas.py

<slug> — транслит названия через дефис: kuplya-prodazha, gosposhlina.
Название блока дословно совпадает в трёх местах: карточка в CALCULATORS,
<h1 class="panel__title"> на странице, комментарий в начале шаблона.

Два способа расчёта — выбирать осознанно:

  клиентский — показатели пересчитываются при вводе, расчёт в JS, значения полей
               переживают перезагрузку через localStorage (образец: ДКП);
  серверный  — форма отправляет POST на тот же адрес, считает service.py,
               ответ — та же страница с результатом (образец: госпошлина).

Клиентский — по умолчанию, когда расчёт это формулы. Серверный — когда нужны
таблицы тарифов, проверки значений и текстовые пояснения к результату.

============================================================
2. ТОКЕНЫ ДИЗАЙНА (заданы в styles.css, менять нельзя)
============================================================
  Шрифт интерфейса --font ........ "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif
  Брендовый шрифт --font-brand ... Georgia, "Times New Roman", serif
  Базовый текст .................. 15px / line-height 1.5 / цвет --text #333333
  Палитра ........................ --bg #FAFAFA (фон рабочей области),
                                   --surface #FFFFFF (карточки, поля),
                                   --navy #0A2A4D (заголовки, рамки, кнопки),
                                   --gold #D4AF37 (акцент, «Итого», hover),
                                   --text #333333, --muted #6B7280,
                                   --divider #E0E0E0, --warning #F0785A,
                                   --success #10B981
  Радиус ......................... --radius 6px
  Тени ........................... --shadow-sm 0 1px 3px rgba(10,42,77,.08)

Корневой styles.css (в корне проекта) — УТВЕРЖДЁННЫЙ дизайн-код: не менять.
Рабочая копия app/static/css/styles.css используется шаблонами; правки в ней —
только по правилу 11 (scoped-дополнения раздела).

============================================================
3. ПОРЯДОК ЧАСТЕЙ СТРАНИЦЫ БЛОКА
============================================================
Сверху вниз — строго так:

  1) <section class="panel">
  2)   <div class="panel__head">
         <h1 class="panel__title">Название блока</h1>
         <span class="panel__hint">Одна фраза о том, что считаем</span>
       </div>
  3)   (только для серверного расчёта, при ошибке валидации)
       <p class="status status--warn"> иконка + {{ error }}</p>
  4)   <div class="calc">                — базовый вариант, две колонки
  5)     <form class="calc__form" id="<slug>-form" autocomplete="off">
           N × <div class="field"> ... </div>        — по одному вопросу в строке
           <div class="calc__row"> кнопки </div>     — ВСЕГДА последним
         </form>
  6)     <aside class="calc__out"> подписи и показатели </aside>
  7)   </div>
  8) </section>

После </section>: {% block scripts %} — сначала money-input.js, затем скрипт
блока (только если расчёт клиентский). app.js подключает base.html последним,
его подключать не нужно.

Внутри формы сначала идут числовые поля (суммы, доли, проценты), затем поля
справочников (<select>) — от общего вопроса к уточняющему. Каждое поле —
отдельная строка: <div class="field"> = подпись + поле (+ пустой блок ошибки).

Внутри <aside class="calc__out">: пары «подпись → значение» в порядке чтения
сверху вниз, последним — «Итого» с классом value--total, затем примечания .note.
Никаких разделителей и линий между показателями — только gap 6px.

Заголовок вкладки: {% block title %}<Короткое название> · Нотариальная контора{% endblock %}

============================================================
4. РАЗМЕРЫ И ОТСТУПЫ КОНТЕЙНЕРОВ (точно по styles.css)
============================================================
  .panel           отступ 22px 28px; фон --bg; нижняя линия 1px --divider;
                   на ширине ≤900px боковые отступы 16px
  .panel__head     flex; выравнивание по базовой линии; space-between; gap 16px;
                   padding-bottom 12px; margin-bottom 16px; линия 1px --divider
  .calc            колонки: поля 1fr + показатели 280px; gap 0; фон --surface;
                   рамка 1px --navy; радиус 6px; тень --shadow-sm; overflow hidden
  .calc__form      grid; gap 14px; padding 18px       — левая колонка, форма
  .field           grid; gap 6px                      — подпись над полем
  .calc__row       flex; gap 12px; align-items center — строка кнопок
  .calc__out       правая колонка 280px; flex-колонка; justify-content center;
                   gap 6px; padding 18px; фон --navy; текст #FFFFFF
  .cards           grid auto-fill minmax(280px, 1fr); gap 14px   — список
  .card            padding 15px 16px; gap 10px; фон --surface; рамка 1px --navy;
                   радиус 6px; тень --shadow-sm
  .card__foot      padding-top 10px; верхняя линия 1px --divider

============================================================
5. ШРИФТЫ, РАЗМЕРЫ И ЦВЕТА НАДПИСЕЙ И ПОЛЕЙ
============================================================
Размеры берутся ровно из таблицы — не «на глаз» и не свои:

  Что                  Класс                Шрифт    Размер  Начертание              Цвет
  Название блока       .panel__title (h1)   --font   17px    600, ls .2px            --navy
  Подсказка справа     .panel__hint         --font   12.5px  400                     --muted
  Подпись поля         .field label         --font   12px    600, ls .4px            --navy
  Текст в поле/списке  .field input, select --font   14px    400                     --text
  Ошибка у поля        .status--warn        --font   12.5px  600 + иконка 16×16      --warning
  Название в карточке  .card__title         --font   14.5px  600                     --text
  Описание в карточке  .card__meta          --font   12.5px  400                     --muted
  Подпись показателя   .calc__out .label    --font   11.5px  400, ls 1px, ЗАГЛАВНЫМИ rgba(255,255,255,.6)
  Значение показателя  .calc__out .value    Georgia  30px    400                     #FFFFFF
  Итог                 .value--total        как значение     400                     --gold
  Примечание           .calc__out .note     --font   11.5px  400                     rgba(255,255,255,.55)
  Кнопка               .btn                 --font   14px    600                     см. правило 8

Подписи полей набраны в обычном регистре: ЗАГЛАВНЫЕ буквы — только у подписей
показателей (.calc__out .label). Засечный Georgia применяется только к значению
показателя в базовом .calc; ДКП — задокументированное исключение (правило 11).

Поля ввода и списки (.field input, .field select):
  width 100%; padding 10px 12px; рамка 1px --divider; радиус 6px; фон --surface;
  шрифт наследуется (--font), 14px. Высоту НЕ задавать — её дают padding и
  размер шрифта. Фокус: рамка --navy + box-shadow 0 0 0 3px rgba(10,42,77,.10),
  outline: none — уже нарисовано в styles.css, добавлять ничего не нужно.

============================================================
6. ФОРМАТЫ ПОЛЕЙ (обязательные атрибуты)
============================================================
  1) Сумма в рублях
     <input id="<slug>-amount" name="amount" type="text" inputmode="decimal"
            data-money data-money-decimals="2" placeholder="Например: 1 500 000">
     type="number" ЗАПРЕЩЁН: он ломает разделители разрядов и запятую.
     data-money-decimals="2" — для сумм в рублях с копейками; без атрибута
     дробная часть не ограничена (нужно для ставок и процентов: 0,005).
     Разделители разрядов, запятую и лимит знаков делает money-input.js, свою
     логику форматирования писать нельзя.

  2) Доля, дробь, ставка без денег
     <input id="<slug>-share" name="share" type="text" inputmode="numeric"
            placeholder="Например: 1/2">
     Атрибут data-money НЕ ставится. Разбор значения — в скрипте блока.

  3) Значение из справочника
     <select id="<slug>-kind" name="kind"> ... </select>
     Пункты строятся из словаря *_LABELS в schemas.py: порядок словаря = порядок
     в списке; проверка значения на сервере — через Literal.

  4) Ошибка поля (пустой блок под полем)
     <p class="status status--warn" id="<slug>-share-error" aria-live="polite"></p>
     Заполняется скриптом: иконка 16×16 (inline SVG в стиле Lucide,
     stroke="currentColor", stroke-width 2) + короткий текст, например
     «Некорректная доля». Виден только у заполненного, но неверного поля.

  5) Общая ошибка страницы (только серверный расчёт)
     <p class="status status--warn"> иконка + {{ error }}</p> — сразу под
     .panel__head, над .calc; приходит из роута вместе с кодом 400.

Атрибуты формы: autocomplete="off". required ставится только в серверных формах,
где пустое значение недопустимо; в клиентских калькуляторах пустое или мусорное
значение поля даёт 0, поэтому required не нужен.

============================================================
7. ПОКАЗАТЕЛИ И ФОРМАТ ЧИСЕЛ
============================================================
  <aside class="calc__out">
    <span class="label">Федеральный тариф</span>
    <span class="value" id="<slug>-out-federal">0&nbsp;₽</span>
    ...
    <span class="label">Итого</span>
    <span class="value value--total" id="<slug>-out-total">0&nbsp;₽</span>
    <span class="note">Оговорка одной-двумя строками</span>
  </aside>

Порядок: основные показатели → «Итого» (класс value--total) → примечания .note.
Если расчёта ещё нет — в значение ставится «—», в .note короткая подсказка,
как в калькуляторе госпошлины. Между показателями только gap 6px: разделители,
линии и лишние <br> не добавлять.

Числа:
  клиентский расчёт (formatMoney в скрипте блока) — целые рубли, разделители
    разрядов и знак рубля — НЕРАЗРЫВНЫЙ пробел: «250 000 ₽»; округление до
    целого только при выводе, «Итого» считается по неокруглённым значениям;
  серверный расчёт (format_money из service.py) — «1 500 000,00», знак ₽
    дописывается в шаблоне: {{ result_text }} ₽;
  начальные значения в шаблоне — 0&nbsp;₽ (неразрывный пробел, не обычный):
    сумма и знак рубля не должны разрываться при переносе строки.

============================================================
8. КНОПКИ
============================================================
Всегда в .calc__row в самом конце формы: сначала действие, затем навигация.
  действие — клиентский расчёт: <button class="btn btn--primary" type="button"
    id="<slug>-reset">Очистить</button>; серверный: type="submit" с текстом
    «Рассчитать»;
  навигация — <a class="btn btn--ghost" href="/calculators/"
    title="Вернуться к списку калькуляторов">К списку</a> — всегда последней.

Геометрия .btn: inline-flex; gap 8px; padding 10px 18px; радиус 6px; 14px; 600;
white-space nowrap. Иконка в кнопке (если нужна) — inline SVG 16×16.
  .btn--primary — фон --navy, текст #FFFFFF; hover — фон и рамка --gold, текст #14243A;
  .btn--ghost   — прозрачный, рамка и текст --navy; hover — фон --navy, текст #FFFFFF.
Словарь текстов: «Открыть» (в списке), «Рассчитать» (серверный расчёт),
«Очистить» (сброс), «К списку» (возврат). Никаких «OK», «Отправить», «Готово».

============================================================
9. СПИСОК КАЛЬКУЛЯТОРОВ
============================================================
Разметка списка уже готова в index.html — новый блок добавляется в него только
записью в CALCULATORS (service.py), шаблон списка не правится:

  CalculatorCard(
      title="Название блока дословно как <h1>",
      description="Короткая фраза без точки",
      url="/calculators/<slug>",
  )

Карточка: .card__title + p.card__meta + .card__foot с одной кнопкой «Открыть»
(.btn.btn--primary), прижатой вправо правилом
.panel--calculators .card__foot. В карточке калькулятора ровно одна кнопка:
её оформление уменьшено правилом .card__foot .btn (padding 5px 9px, иконка 13×13).
Порядок карточек = порядок записей в CALCULATORS.

============================================================
10. ТЕКСТЫ
============================================================
  заголовок блока — полное официальное название, без сокращений и точки;
    название в карточке совпадает с ним дословно;
  подсказка .panel__hint — одна фраза без точки («Расчёт обновляется при вводе»,
    «Тариф за удостоверение сделки»);
  подписи полей — с большой буквы, без двоеточия и точки в конце, 2–5 слов;
  единица измерения — через запятую после названия: «Цена договора, ₽»,
    «Сумма договора, ₽»; у нечисловых полей единицы нет: «Доля
    несовершеннолетних продавцов», «Тип сделки», «Категория плательщика»;
  подсказка в поле (placeholder) — «Например: 1 500 000», «Например: 1/2»;
  подписи показателей — краткие существительные: «Федеральный тариф»,
    «Региональный тариф», «Итого», «Льгота», «Госпошлина»;
  сообщения об ошибке — короткие и в терминах поля: «Некорректная доля»,
    «Сумма договора должна быть больше нуля»;
  оговорки в .note — «…не учтены — уточнить у нотариуса»;
  интерфейс только на русском; латиница допустима в единицах и аббревиатурах (₽, %).

============================================================
11. ПРАВКИ CSS И ИСКЛЮЧЕНИЯ
============================================================
Корневой styles.css (утверждённый дизайн-код) не менять НИКОГДА. Дополнения
раздела живут только в рабочей копии app/static/css/styles.css.

Доступные классы (придумывать новые нельзя):
  панель и список: .panel, .panel--calculators, .panel__head, .panel__title,
                   .panel__hint, .cards, .card, .card__title, .card__meta,
                   .card__foot и .card__foot .btn (компактная кнопка карточки);
  калькулятор:     .calc, .calc__form, .calc__row, .calc__out, .field,
                   .label, .value, .value--total, .note;
  элементы:        .btn, .btn--primary, .btn--ghost, .status,
                   .status--warn / --ok / --info (по смыслу сообщения);
  иконки — inline SVG в стиле Lucide: stroke="currentColor", stroke-width 2,
  размер 16×16 (в карточке 13×13, в статусах до 21×21).

Если блоку действительно нужен свой вид:
  1) сначала попробовать собрать блок только из классов выше;
  2) если не получилось — дописать в рабочую копию CSS scoped-блок по классу
     блока (.calc--<slug> или .panel--<slug>) с комментарием на русском: что
     меняется и почему общим правилом не обойтись;
  3) правка не должна менять вид других блоков: селектор начинается с класса
     этого блока, а не с общего элемента или тега.

Задокументированные исключения (образцы таких комментариев):
  .calc--tariff — калькулятор ДКП: два столбца по 350px + распорка minmax(0,1fr),
    рамку и радиус рисуют сами столбцы, тень — псевдоэлемент ::after, значения
    показателей без Georgia (28px, по правому краю), «Итого» золотом, поля 15px;
    на ≤900px ширины столбцы остаются 350/350, прокручивается .workspace;
  .calc__form .cards и .panel--db-search — служебные для раздела «База данных»,
    в калькуляторах не используются.

Хардкод цветов и размеров мимо токенов, свои CSS-файлы, Tailwind и inline-стили
в шаблонах запрещены.

============================================================
12. КОНТРАКТ СКРИПТА БЛОКА (клиентский расчёт)
============================================================
Подключение — в {% block scripts %} шаблона, ровно в таком порядке:
  <script src="{{ url_for('static', path='js/money-input.js') }}"></script>
  <script src="{{ url_for('static', path='js/<slug>.js') }}"></script>
app.js подключает base.html — повторно его не подключать.

Структура файла: один IIFE + "use strict" + guard «страница не наша — выходим»:
  (function () {
    "use strict";
    var form = document.getElementById("<slug>-form");
    if (!form) { return; }
    ...
  })();
С guard файл безопасно грузится на любой странице.

Идентификаторы (id и name совпадают):
  <slug>-form            форма
  <slug>-<field>         поле ввода: amount, share, kind …
  <slug>-out-<key>       показатель в .calc__out
  <slug>-<field>-error   пустой .status--warn под полем
  <slug>-reset           кнопка сброса

Правила:
  форматирование сумм — только атрибутами data-money / data-money-decimals;
    после подстановки значений из localStorage вызвать
    window.MoneyInput.format(input);
  localStorage — ключи вида calculators.<slug>.<field>; все обращения (getItem,
    setItem, removeItem) в try/catch: в приватном режиме хранилище недоступно,
    а калькулятор обязан продолжать считать; «Очистить» удаляет только свои
    ключи и обнуляет показатели;
  события — только addEventListener, никаких inline onclick: input на числовых
    полях (пересчёт и сохранение), change на select, submit формы —
    event.preventDefault() (Enter в поле не перезагружает страницу), сброс —
    click по кнопке type="button";
  разбор значений: обычные и неразрывные пробелы убрать, запятую принять как
    десятичный разделитель, пустое/нечисловое/отрицательное → 0; в показателях
    не должно появляться NaN;
  расчёт — чистые функции; округление только при выводе
    (formatMoney → Math.round), «Итого» считается по неокруглённым значениям;
  ошибка поля — сообщение .status--warn с иконкой 16×16 и коротким текстом;
  внешние библиотеки, CDN и сборщики не подключать: только нативный JS в стиле
    existing-кода (IIFE, var, никаких модулей и транспиляции).

============================================================
13. КОНТРАКТ МАРШРУТОВ, РАСЧЁТА И СХЕМ
============================================================
Все маршруты раздела — в app/modules/calculators/routes.py; пути внутри модуля
пишутся без префикса, /calculators добавляет main.py при include_router.

Имена:
  <slug>_page(...)      — GET страница калькулятора;
  <slug>_calculate(...) — POST расчёт (только серверный вариант);
  _render_<slug>(...)   — общий хелпер рендера страницы (форма + результат + error).

Страница:
  обязательный параметр user: CurrentUser — раздел доступен только сотрудникам;
  рендер через app.core.templating.render с user=user и active_menu=MENU_CALCULATORS
    (иначе пункт «Калькуляторы» в меню не подсветится);
  заголовок вкладки задаётся в шаблоне через {% block title %}.

Серверный расчёт:
  POST на тот же адрес страницы (у формы нет action), ответ — та же страница;
  при ошибке валидации — status.HTTP_400_BAD_REQUEST и тот же шаблон с error
    (не JSON и не редирект), текст берётся из _validation_message;
  в шаблон передаются введённые значения и подписи списка: amount, kind,
    kinds=KIND_LABELS;
  в шаблоне рисуется результат: result_text получен из format_money.

service.py:
  карточка блока — запись в кортеже CALCULATORS (CalculatorCard); список отдаёт
    list_calculators();
  расчёт — чистая функция, возвращает Pydantic-модель «значение + пояснение»;
  денежные суммы на вывод — format_money («1 500 000,00»), знак ₽ дописывает шаблон.

schemas.py:
  суммы: float + @field_validator(..., mode="before") — убрать пробелы и
    неразрывные пробелы, запятую заменить точкой; ограничение MAX_AMOUNT;
    округление round(..., 2);
  справочники: словари *_LABELS + Literal на ключ; ключи словаря совпадают с
    ключами тарифов в service.py, подписи берутся из словаря, а не из шаблона;
  сообщения об ошибке — на русском, для пользователя, без технических деталей
    (служебный префикс «Value error, » снимает _validation_message).

============================================================
14. ЧЕГО НЕ ДЕЛАТЬ
============================================================
  не менять корневой styles.css и общий calculators.js «под свой блок»;
  не дублировать money-input.js своей логикой форматирования сумм;
  не создавать классы CSS и не писать style="..." в шаблоне;
  не использовать type="number", alert() и свои подсказки браузера для ошибок;
  не подключать внешние библиотеки, шрифты, иконочные шрифты и CDN: портал
    работает в закрытой сети;
  не заводить модели и таблицы БД под калькулятор — раздел ничего не хранит;
  не править index.html и карточки вручную — только реестр CALCULATORS;
  не выносить общую логику в абстракции «на будущее» — только то, что нужно блоку;
  не переписывать соседние калькуляторы «заодно»: правка одного блока не меняет
    вид и поведение других.

============================================================
15. ШАБЛОН НОВОГО БЛОКА
============================================================
Готовый каркас разметки — app/templates/calculators/_block_template.html
(файл лежит в шаблонах, но роута у него нет: он только для копирования).
Эталон разметки — этот файл; при правке каркаса обновляй и текст ниже.
Скрипт, бэкенд и карточка — только в этой главе.

15.1 Разметка — копия app/templates/calculators/<slug>.html
--------------------------------------------------------------
{% extends "base.html" %}

{% block title %}Короткое название · Нотариальная контора{% endblock %}

{% block content %}
{# Калькулятор «НАЗВАНИЕ БЛОКА»: слева поля ввода, справа показатели.
   Расчёт идёт в браузере (static/js/<slug>.js), введённые значения хранятся
   в localStorage. #}
<section class="panel">
  <div class="panel__head">
    <h1 class="panel__title">НАЗВАНИЕ БЛОКА ДОСЛОВНО КАК В КАРТОЧКЕ</h1>
    <span class="panel__hint">Одна фраза о том, что считаем</span>
  </div>

  {% if error %}
  <p class="status status--warn">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16"
         fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" x2="12" y1="8" y2="12"/>
      <line x1="12" x2="12.01" y1="16" y2="16"/>
    </svg>
    {{ error }}
  </p>
  {% endif %}

  <div class="calc">
    <form class="calc__form" id="<slug>-form" autocomplete="off">
      <div class="field">
        <label for="<slug>-amount">Сумма, ₽</label>
        <input id="<slug>-amount" name="amount" type="text" inputmode="decimal"
               data-money data-money-decimals="2" placeholder="Например: 1 500 000">
      </div>

      <div class="field">
        <label for="<slug>-share">Доля</label>
        <input id="<slug>-share" name="share" type="text" inputmode="numeric"
               placeholder="Например: 1/2">
        <p class="status status--warn" id="<slug>-share-error" aria-live="polite"></p>
      </div>

      <div class="field">
        <label for="<slug>-kind">Параметр из справочника</label>
        <select id="<slug>-kind" name="kind">
          <option value="a">Вариант А</option>
          <option value="b">Вариант Б</option>
        </select>
      </div>

      <div class="calc__row">
        <button class="btn btn--primary" id="<slug>-reset" type="button">Очистить</button>
        <a class="btn btn--ghost" href="/calculators/"
           title="Вернуться к списку калькуляторов">К списку</a>
      </div>
    </form>

    <aside class="calc__out">
      <span class="label">Показатель</span>
      <span class="value" id="<slug>-out-main">0&nbsp;₽</span>

      <span class="label">Итого</span>
      <span class="value value--total" id="<slug>-out-total">0&nbsp;₽</span>

      <span class="note">Услуги правового и технического характера и льготы
        не учтены — уточнить у нотариуса</span>
    </aside>
  </div>
</section>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', path='js/money-input.js') }}"></script>
<script src="{{ url_for('static', path='js/<slug>.js') }}"></script>
{% endblock %}
--------------------------------------------------------------
Для серверного расчёта: строки с data-money оставить, но value подставлять из
роута (value="{{ amount }}"), кнопка становится type="submit" с текстом
«Рассчитать», а {% block scripts %} ограничивается money-input.js.

15.2 Скрипт блока — app/static/js/<slug>.js (только клиентский расчёт)
--------------------------------------------------------------
/* Модуль «Калькуляторы»: расчёт «НАЗВАНИЕ БЛОКА». Считает браузер: показатели
   обновляются при вводе, введённые значения хранятся в localStorage. Суммы в
   полях ввода показываются с разделителями разрядов (модуль money-input.js). */
(function () {
  "use strict";

  var STORAGE_AMOUNT = "calculators.<slug>.amount";
  var STORAGE_SHARE = "calculators.<slug>.share";
  var STORAGE_KIND = "calculators.<slug>.kind";

  // Разделитель разрядов — неразрывный пробел: сумма и знак рубля не разрываются
  var NBSP = "\u00A0";

  var form = document.getElementById("<slug>-form");
  if (!form) {
    return;
  }

  var amountInput = document.getElementById("<slug>-amount");
  var shareInput = document.getElementById("<slug>-share");
  var kindInput = document.getElementById("<slug>-kind");
  var resetButton = document.getElementById("<slug>-reset");
  var shareError = document.getElementById("<slug>-share-error");

  var outMain = document.getElementById("<slug>-out-main");
  var outTotal = document.getElementById("<slug>-out-total");

  // --- localStorage: в приватном режиме хранилище недоступно, поэтому все
  // обращения обёрнуты в try — калькулятор продолжает работать ---
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

  // Сумма: разделители разрядов и прочие пробелы убираем, запятую принимаем как
  // разделитель дробной части. Пустое, нечисловое и отрицательное дают 0.
  function readNumber(input) {
    var cleaned = String((input && input.value) || "").replace(/\s/g, "").replace(",", ".");
    if (!/^\d+(?:\.\d+)?$/.test(cleaned)) {
      return 0;
    }
    var value = parseFloat(cleaned);
    return isNaN(value) ? 0 : value;
  }

  // Сумма в показателе: целые рубли с разделителями разрядов —
  // 250000 => «250 000 ₽»
  function formatMoney(value) {
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + NBSP + "₽";
  }

  function render(element, value) {
    if (element) {
      element.textContent = formatMoney(value);
    }
  }
--------------------------------------------------------------
(продолжение — 15.3)

15.3 Скрипт блока (продолжение)
--------------------------------------------------------------
  // Доля «числитель/знаменатель»: { filled, valid, numerator, denominator }
  function readShare(raw) {
    var share = { filled: false, valid: false, numerator: 0, denominator: 0 };
    var value = String(raw || "").trim();
    if (!value) {
      return share;
    }
    share.filled = true;
    var parts = value.split("/");
    if (parts.length !== 2) {
      return share;
    }
    var numerator = parts[0].trim();
    var denominator = parts[1].trim();
    if (!/^\d+$/.test(numerator) || !/^\d+$/.test(denominator)) {
      return share;
    }
    share.numerator = parseInt(numerator, 10);
    share.denominator = parseInt(denominator, 10);
    if (share.denominator === 0 || share.numerator > share.denominator) {
      return share;
    }
    share.valid = true;
    return share;
  }

  // Сообщение об ошибке показываем только у заполненного поля
  function renderShareError(visible) {
    if (shareError) {
      shareError.textContent = visible ? "Некорректная доля" : "";
    }
  }

  function saveValue(key, input) {
    var value = input ? String(input.value || "").trim() : "";
    if (value) {
      storageSet(key, value);
    } else {
      storageRemove(key);
    }
  }

  function restoreValue(key, input) {
    var saved = storageGet(key);
    if (saved !== null && input) {
      input.value = saved;
    }
  }

  // Пересчёт показателей: пустое или мусорное значение поля даёт 0
  function calculate() {
    var amount = readNumber(amountInput);
    var share = readShare(shareInput ? shareInput.value : "");

    var main = amount / 2;
    render(outMain, main);
    render(outTotal, main);

    renderShareError(share.filled && !share.valid);
  }

  function handleInput() {
    saveValue(STORAGE_AMOUNT, amountInput);
    saveValue(STORAGE_SHARE, shareInput);
    saveValue(STORAGE_KIND, kindInput);
    calculate();
  }

  restoreValue(STORAGE_AMOUNT, amountInput);
  restoreValue(STORAGE_SHARE, shareInput);
  restoreValue(STORAGE_KIND, kindInput);

  // Восстановленные суммы показываем так же, как только что введённые
  if (window.MoneyInput) {
    window.MoneyInput.format(amountInput);
  }

  amountInput.addEventListener("input", handleInput);
  shareInput.addEventListener("input", handleInput);
  kindInput.addEventListener("change", handleInput);

  // Форма ничего не отправляет: Enter в поле не должен перезагружать страницу
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  if (resetButton) {
    resetButton.addEventListener("click", function () {
      amountInput.value = "";
      shareInput.value = "";
      storageRemove(STORAGE_AMOUNT);
      storageRemove(STORAGE_SHARE);
      calculate();
    });
  }

  calculate();
})();
--------------------------------------------------------------
