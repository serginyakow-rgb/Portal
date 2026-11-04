"""Схемы (Pydantic) модуля «Задачи»: карточки, статусы доски и чек-листы."""
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.sync import SectionState

# Границы длины полей
MAX_TITLE = 200
MAX_CONTACT = 200
# Границы полей справочника контактов (кнопка «Контакты» в шапке «Задач»)
MAX_CONTACT_NAME = 200
MAX_CONTACT_PHONE = 50
MAX_CONTACT_EMAIL = 120

# Тип карточки: id шаблона из «Настроек» → «Шаблоны карточек для раздела
# «Задачи»», записанный строкой. Подписи и пункты чек-листа форма берёт
# из шаблона (routes._card_type_options), поэтому в схеме их нет.
TaskCardType = str

# Встроенные типы прежних версий: подписи нужны карточкам, созданным до
# появления шаблонов в настройках (service.card_type_label)
CARD_TYPE_LABELS: dict[str, str] = {
    "gift": "Договор дарения",
    "sale_minor": "Договор купли-продажи с несовершеннолетним",
    "sale_other": "Договор купли-продажи (иное)",
    "inheritance": "Наследство",
    "power_of_attorney": "Доверенность",
    "spouse_consent": "Согласие супруга",
    "other": "Иное",
}

# Чек-лист встроенных типов прежних версий: наборы нужны валидатору
# keep_type_checklist у карточек, созданных до появления шаблонов.
# Действующие наборы живут в шаблонах («Настройки» → «Шаблоны карточек для
# раздела «Задачи»») и попадают в разметку через data-task-checklists —
# список пунктов в js/tasks.js не дублируется, он только перерисовывает
# чекбоксы при смене типа. Пункты шаблона фильтрует routes._keep_checklist.
CARD_TYPE_CHECKLISTS: dict[str, tuple[str, ...]] = {
    "gift": (
        "Документы дарителя",
        "Документы одаряемого",
        "Правоустанавливающие документы",
        "Родственные отношения",
        "Согласие супруги дарителя",
        "Дееспособность",
    ),
    "sale_minor": (
        "Документы продавца",
        "Документы покупателя",
        "Правоустанавливающие документы",
        "Разрешение опеки",
        "Цена и порядок расчетов",
        "Согласие супруги продавца",
        "Согласие супруги покупателя",
        "Родственные отношения / полномочия",
        "Дееспособность",
        "Справка о составе семьи",
    ),
    "sale_other": (
        "Документы продавца",
        "Документы покупателя",
        "Правоустанавливающие документы",
        "Цена и порядок расчета",
        "Согласие супруги продавца",
        "Согласие супруга покупателя",
        "Дееспособность",
        "Справка о составе семьи",
    ),
    "inheritance": (),
    "other": (),
    "spouse_consent": (
        "Данные лица, дающего согласие",
        "Данные супруга",
        "Данные объекта",
        "Свидетельство о браке",
    ),
    "power_of_attorney": (
        "Документы доверителя",
        "Данные поверенного",
        "Содержание доверенности",
        "Родственные отношения",
    ),
}

# Столбцы доски: порядок словаря = порядок колонок слева направо
STATUS_LABELS: dict[str, str] = {
    "queue": "На очереди",
    "in_progress": "В работе",
    "review": "Проверка",
    "done": "Готово",
}
STATUS_ORDER: tuple[str, ...] = tuple(STATUS_LABELS)

# Цветовые акценты столбцов: модификаторы kb-* из styles.css (секция «КАНБАН-ДОСКА»).
# Отдельный словарь, чтобы шаблон подставлял класс в цикле, без четырёх блоков.
STATUS_CLASSES: dict[str, str] = {
    "queue": "kb-column--queue",
    "in_progress": "kb-column--progress",
    "review": "kb-column--review",
    "done": "kb-column--done",
}
TaskStatus = Literal["queue", "in_progress", "review", "done"]

# Тип по умолчанию: с него открываются окно «Новая карточка» на доске
# и страница /tasks/create — самый частый вид сделки в конторе
DEFAULT_CARD_TYPE: TaskCardType = "sale_minor"
DEFAULT_STATUS: TaskStatus = "queue"


class _TaskForm(BaseModel):
    """Общие поля карточки и проверка значений, приходящих из формы."""

    title: str = ""
    contact: str = ""
    due_date: date | None = None
    description: str = ""
    assignee_id: int | None = None
    card_type: TaskCardType = DEFAULT_CARD_TYPE
    checklist: dict[str, bool] = {}

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Заголовок карточки обязателен")
        if len(cleaned) > MAX_TITLE:
            raise ValueError(f"Заголовок слишком длинный (максимум {MAX_TITLE} символов)")
        return cleaned

    @field_validator("contact", mode="before")
    @classmethod
    def clean_contact(cls, value: Any) -> str:
        """Контакт — одна строка: лишние пробелы и переводы строк убираем."""
        return " ".join(str(value).split()) if value else ""

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: Any) -> str:
        """Описание многострочное: снимаем только пробелы по краям."""
        return str(value).strip() if value else ""

    @field_validator("due_date", mode="before")
    @classmethod
    def empty_due_date(cls, value: Any) -> Any:
        """Пустая строка из <input type="date"> означает «срок не задан»."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("assignee_id", mode="before")
    @classmethod
    def empty_assignee(cls, value: Any) -> Any:
        """Пустое значение списка «Выполняет» — исполнитель не выбран."""
        if value is None or value == "" or value == 0 or value == "0":
            return None
        return value

    @field_validator("checklist", mode="before")
    @classmethod
    def prepare_checklist(cls, value: Any) -> dict[str, bool]:
        """Принимает словарь {пункт: отмечен} и приводит флаги к bool."""
        if not value:
            return {}
        return {str(name): bool(flag) for name, flag in dict(value).items()}

    @model_validator(mode="after")
    def keep_type_checklist(self) -> Self:
        """Оставляет в чек-листе только пункты выбранного типа карточки.

        Так разбираются встроенные типы прежних версий. Для типа-шаблона
        набор пунктов лежит в БД, поэтому его проверяет маршрут
        (routes._keep_checklist) — у схемы нет доступа к настройкам.
        """
        allowed = CARD_TYPE_CHECKLISTS.get(self.card_type)
        if allowed is None:
            return self
        self.checklist = {name: self.checklist.get(name, False) for name in allowed}
        return self


class TaskCreate(_TaskForm):
    """Создание карточки: тип выбирается первым полем, столбец — «На очереди»."""


class TaskUpdate(_TaskForm):
    """Правка карточки: столбец и позицию меняет только перемещение по доске.

    Столбец и позицию форма не присылает — их передают служебные вызовы.
    Пустой исполнитель («Не выбран») возвращает карточку в «На очереди»:
    это перемещение, поэтому правило живёт в service.update_task.
    """

    status: TaskStatus | None = None
    position: int | None = None

    @field_validator("status", mode="before")
    @classmethod
    def empty_status(cls, value: Any) -> Any:
        """Пустое значение из формы — «столбец не меняем»."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value


class TaskMove(BaseModel):
    """Перемещение карточки по доске: столбец и позиция в нём."""

    status: TaskStatus
    position: int = 0

    @field_validator("position", mode="before")
    @classmethod
    def empty_position(cls, value: Any) -> Any:
        """Пустое значение позиции из запроса — в начало столбца."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return 0
        return value


class TaskMoveResult(BaseModel):
    """Ответ на перемещение карточки: флаг, исполнитель и числа метки меню.

    Доска обновляет имя исполнителя в строке «Исполнитель | Срок», заливку
    полосы прогресса и числа метки по этим полям сразу, без перезагрузки.

    `menu_unassigned`, `menu_mine` и `menu_due_soon` — те же числа, что метка
    «Задачи» в левом меню (service.count_menu_badge): перенос их меняет, потому
    что карточка сменила столбец, а при выходе из «На очереди» ещё и получила
    исполнителя. js/tasks.js переписывает метку и показывает или прячет значок
    срока по этим полям, не дожидаясь перезагрузки страницы.

    `assignee_counts` — числа окна «Задачи по сотрудникам» после переноса
    (service.count_tasks_by_assignee): перенос в «Готово» убирает карточку
    из загрузки сотрудника, и без этого поля цифра и полоса в окне оставались
    бы прежними до перезагрузки страницы. Окно есть только у роли «Нотариус»
    (admin), остальным поле приходит пустым.
    """

    ok: bool = True
    assignee_id: int | None = None
    assignee_name: str | None = None
    assignee_color: str | None = None
    # Прогресс карточки в процентах после переноса: его считает
    # service.task_progress по новому столбцу, исполнителю и чек-листу;
    # js/tasks.js перерисовывает заливку полосы по этому полю, не дожидаясь
    # перезагрузки страницы
    progress: int = 0
    # Числа метки «Задачи» после переноса: ничьи карточки и карточки сотрудника
    # в «На очереди» и «В работе»
    menu_unassigned: int = 0
    menu_mine: int = 0
    # Срочные карточки сотрудника (истекающий или прошедший срок): по этому
    # числу js/tasks.js показывает или прячет значок предупреждения у метки
    # «Задачи», не дожидаясь перезагрузки страницы
    menu_due_soon: int = 0
    # Числа окна «Задачи по сотрудникам» после переноса: {id сотрудника:
    # карточек в «На очереди», «В работе» и «Проверка»}; «Готово» не входит
    assignee_counts: dict[int, int] = {}


class TaskRead(BaseModel):
    """Карточка целиком: для формы правки и служебных ответов."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    contact: str | None = None
    due_date: date | None = None
    description: str | None = None
    assignee_id: int | None = None
    assignee_name: str | None = None
    card_type: TaskCardType
    status: TaskStatus
    checklist: dict[str, bool] = {}
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    position: int = 0


class TaskListItem(BaseModel):
    """Карточка для доски и корзины: без автора и дат создания.

    Описание и чек-лист на доске не выводятся: они нужны окну правки —
    шаблон кладёт их в data-task на кнопке карточки, а js/tasks.js
    заполняет ими поля окна (одно окно на всю доску).
    """

    id: int
    title: str
    contact: str | None = None
    due_date: date | None = None
    description: str | None = None
    card_type: TaskCardType
    card_type_label: str = ""
    status: TaskStatus
    position: int = 0
    assignee_id: int | None = None
    assignee_name: str | None = None
    # Цвет исполнителя (marker_color): им залита полоса прогресса в карточке
    assignee_color: str | None = None
    # Прогресс карточки в процентах: им задана ширина заливки полосы под
    # строкой «Исполнитель | Срок», цифры не выводятся. Считает
    # service.task_progress по столбцу, исполнителю и чек-листу; в БД
    # значение не хранится — оно производное
    progress: int = 0
    # До срока меньше двух рабочих дней (пн–пт) или срок уже прошёл:
    # шаблон выделяет такой срок жирным красным (.card__due--soon), а в столбце
    # «Готово» подсветку снимают стили — работа закрыта
    due_soon: bool = False
    # Чек-лист типа карточки: {пункт: отмечен} — для предзаполнения окна правки
    checklist: dict[str, bool] = {}
    deleted_at: datetime | None = None  # заполняется только у карточек корзины


class BoardState(SectionState):
    """Ответ «состояние доски» для синхронизации экранов сотрудников.

    ``version`` — отпечаток доски из ``service.board_version``: его сравнивает
    ``js/sync.js`` и при расхождении забирает свежие столбцы у
    ``GET /tasks/board``. Остальные поля обновляются на каждом опросе, даже
    если доска не менялась: они зависят и от карточек вне текущего фильтра.

    Имена ``menu_*`` и ``assignee_counts`` совпадают с полями
    ``TaskMoveResult``: их разбирают те же ``applyMenuBadge`` и
    ``applyAssignees`` в ``js/tasks.js``, поэтому у опроса и перетаскивания
    одна перерисовка метки «Задачи» и окна «Задачи по сотрудникам».
    """

    # Числа метки «Задачи»: ничьи карточки и карточки сотрудника в работе
    menu_unassigned: int = 0
    menu_mine: int = 0
    # Срочные карточки сотрудника: по числу показывается или прячется значок
    menu_due_soon: int = 0
    # Числа окна «Задачи по сотрудникам»: {id сотрудника: карточек в работе}.
    # Окно есть только у роли «Нотариус» (admin), остальным словарь пустой
    assignee_counts: dict[int, int] = {}


class ContactInput(BaseModel):
    """Данные формы контакта: имя, телефон и электронная почта.

    Имя обязательно, телефон и почта — по желанию: у контакта может быть
    только телефон. Пробелы схлопываются, пустое необязательное поле означает
    «нет значения» — сервис превращает его в NULL, а не в пустую строку.
    """

    name: str = ""
    phone: str = ""
    email: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Схлопывает пробелы и требует непустое имя."""
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Имя контакта обязательно")
        if len(cleaned) > MAX_CONTACT_NAME:
            raise ValueError(f"Имя слишком длинное (максимум {MAX_CONTACT_NAME} символов)")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        """Телефон — цифры, пробел и знаки + ( ) -; хотя бы одна цифра."""
        cleaned = " ".join(value.split())
        if not cleaned:
            return ""
        if len(cleaned) > MAX_CONTACT_PHONE:
            raise ValueError(f"Телефон слишком длинный (максимум {MAX_CONTACT_PHONE} символов)")
        if any(symbol not in "+-() 0123456789" for symbol in cleaned):
            raise ValueError("Телефон может содержать только цифры, пробел и знаки + ( ) -")
        if not any(symbol.isdigit() for symbol in cleaned):
            raise ValueError("Телефон должен содержать хотя бы одну цифру")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Почта — простая проверка формы «что-то@что-то.домен», без зависимостей."""
        cleaned = value.strip()
        if not cleaned:
            return ""
        if len(cleaned) > MAX_CONTACT_EMAIL:
            raise ValueError(
                f"Электронная почта слишком длинная (максимум {MAX_CONTACT_EMAIL} символов)"
            )
        local, at_sign, domain = cleaned.partition("@")
        if (
            not at_sign
            or not local
            or not domain
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
            or " " in cleaned
        ):
            raise ValueError("Электронная почта указана неверно")
        return cleaned

