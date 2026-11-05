"""Error types shared by every module (no imports, so no import cycles)."""


class ReportError(Exception):
    """Ошибка входных данных или параметров; текст предназначен для пользователя."""


class UsageError(ReportError):
    """Неверные параметры командной строки."""
