"""Схемы (Pydantic) модуля «Задачи»: карточки, статусы доски и чек-листы."""
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Границы длины полей
MAX_TITLE = 200
MAX_CONTACT = 200

# Тип карточки: значение хранится в БД, подпись показывается на доске и в формах
# Порядок словаря CARD_TYPE_LABELS = порядок пунктов в списке «Тип карточки»
TaskCardType = Literal[
    "gift",
    "sale_minor",
    "sale_other",
    "inheritance",
    "power_of_attorney",
    "spouse_consent",
    "other",
    "personal",
]

CARD_TYPE_LABELS: dict[str, str] = {
    "gift": "Договор дарения",
    "sale_minor": "Договор купли-продажи с несовершеннолетним",
    "sale_other": "Договор купли-продажи (иное)",
    "inheritance": "Наследство",
    "power_of_attorney": "Доверенность",
    "spouse_consent": "Согласие супруга",
    "other": "Иное",
    "personal": "Личное",
}

# Чек-лист по типу карточки: порядок пунктов = порядок чекбоксов в форме.
# Наборы попадают в разметку через data-task-checklists, поэтому в js/tasks.js
# списка пунктов нет — он только перерисовывает чекбоксы при смене типа.
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
    "personal": (),
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
        """Оставляет в чек-листе только пункты выбранного типа карточки."""
        allowed = CARD_TYPE_CHECKLISTS.get(self.card_type, ())
        self.checklist = {name: self.checklist.get(name, False) for name in allowed}
        return self


class TaskCreate(_TaskForm):
    """Создание карточки: тип выбирается первым полем, столбец — «На очереди»."""


class TaskUpdate(_TaskForm):
    """Правка карточки: столбец и позицию меняет только перемещение по доске."""

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
    """Ответ на перемещение карточки: флаг и исполнитель после переноса.

    Доска обновляет имя исполнителя в строке «Исполнитель | Срок» и цветную
    метку по этим полям сразу, без перезагрузки страницы.
    """

    ok: bool = True
    assignee_id: int | None = None
    assignee_name: str | None = None
    assignee_color: str | None = None


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
    # Цвет метки исполнителя (marker_color): им подсвечена левая грань карточки
    assignee_color: str | None = None
    # Чек-лист типа карточки: {пункт: отмечен} — для предзаполнения окна правки
    checklist: dict[str, bool] = {}
    deleted_at: datetime | None = None  # заполняется только у карточек корзины

