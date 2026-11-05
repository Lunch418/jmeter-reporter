"""Time zones and time formatting for the report."""
import re
from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from .errors import ReportError

def resolve_timezone(spec):
    """Часовой пояс для отображения меток времени.

    None или 'local' -> локальный пояс машины (значение по умолчанию).
    'UTC' -> работает везде; 'Europe/Moscow', 'Asia/Yekaterinburg' -> именованный пояс
    (системная база zoneinfo; на Windows нужен пакет tzdata).
    '+05:00', '-03:30', '+5' -> фиксированное смещение, работает на любом Python.
    """
    if spec is None or spec.strip().lower() == 'local':
        return None  # None => datetime.astimezone() возьмёт пояс машины

    spec = spec.strip()

    offset = re.fullmatch(r'(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?', spec, re.IGNORECASE)
    if offset:
        sign = 1 if offset.group(1) == '+' else -1
        delta = timedelta(hours=int(offset.group(2)), minutes=int(offset.group(3) or 0))
        return timezone(sign * delta)

    if spec.upper() in ('UTC', 'GMT', 'Z'):
        return timezone.utc  # не требует базы часовых поясов

    try:
        return ZoneInfo(spec)
    except Exception:
        raise ReportError(
            f"Неизвестный часовой пояс: '{spec}'.\n"
            f"Ожидается имя вида Europe/Moscow, UTC, либо смещение вида +05:00.\n"
            f"На Windows именованные пояса требуют пакета tzdata: pip install tzdata"
        )


def to_datetime(ts_ms, tz):
    """Метка времени JMeter (epoch в миллисекундах) -> datetime в поясе tz."""
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).astimezone(tz)


def format_timestamp(ts_ms, tz):
    """Читаемая метка времени: '21.07.2026 17:31:26.285'."""
    try:
        return to_datetime(ts_ms, tz).strftime('%d.%m.%Y %H:%M:%S.%f')[:-3]
    except (TypeError, ValueError, OSError, OverflowError):
        return 'N/A'


def timezone_label(ts_ms, tz):
    """Подпись пояса для шапки отчёта: 'UTC+03:00'.

    Смещение считается на момент самого теста, а не на 'сейчас', поэтому
    отчёт по летнему тесту, открытый зимой, всё равно подпишется правильно.
    """
    try:
        offset = to_datetime(ts_ms, tz).utcoffset()
    except (TypeError, ValueError, OSError, OverflowError):
        return 'UTC'
    if offset is None:
        return 'UTC'
    total_minutes = int(offset.total_seconds() // 60)
    sign = '+' if total_minutes >= 0 else '-'
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def format_duration(ms):
    """Длительность в формате '4 мин 51,430 сек' (с часами, если тест длинный)."""
    total_seconds = ms / 1000.0
    hours = int(total_seconds) // 3600
    minutes = (int(total_seconds) % 3600) // 60
    seconds = total_seconds - hours * 3600 - minutes * 60
    tail = f"{minutes} мин {seconds:.3f}".replace('.', ',') + " сек"
    return f"{hours} ч {tail}" if hours else tail
