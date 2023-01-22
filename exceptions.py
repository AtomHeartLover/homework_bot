class IncorrectResponseException(TypeError):
    """В ответе не обнаружены ожидаемые ключи."""
    pass


class UnknownStatusException(KeyError):
    """В ответе не обнаружены ожидаемые ключи."""
    pass


class TelegramAPIException(Exception):
    """Telegram API не вернул ответ."""
    pass


class HomeworkMissingException(Exception):
    """В ответе API домашки нет ключа `homework_name`."""
    pass
