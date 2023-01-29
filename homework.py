import logging
import os
import time
from http import HTTPStatus
from logging import StreamHandler
from sys import stdout

import requests
import telegram
from dotenv import load_dotenv
from requests import HTTPError

from exceptions import (HomeworkMissingException, IncorrectResponseException,
                        TelegramAPIException, UnknownStatusException)

load_dotenv()

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD: int = 600
ERROR_CACHE_LIFETIME: int = 60 * 60 * 24

HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

errors_occured = {}

formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler(stream=stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram чат.
    Чат определяется переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение "{message}" успешно отправлено')
    except Exception as error:
        error_message = f'Ошибка при отправке сообщения: {error}'
        logger.exception(error_message)
        raise TelegramAPIException(error_message)


def get_api_answer(current_timestamp):
    """Функция делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code == HTTPStatus.OK:
            return response.json()
        raise HTTPError()
    except (HTTPError, ConnectionRefusedError) as error:
        error_message = f'Ресурс {ENDPOINT} недоступен: {error}'
        logger.exception(error_message)
        raise HTTPError(error_message)
    except Exception as error:
        error_message = f'Ошибка при запросе к API: {error}'
        logger.exception(error_message)
        raise Exception(error_message)


def check_response(response):
    """Функция проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    logger.debug('Проверка ответа сервиса на корректность.')

    if (isinstance(response, dict)
            and len(response) != 0
            and 'homeworks' in response
            and 'current_date' in response
            and isinstance(response.get('homeworks'), list)):
        return response.get('homeworks')
    else:
        error_message = 'Ответ API не соответствует ожидаемому!'
        logger.exception(error_message)
        raise IncorrectResponseException(error_message)


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра получает только один элемент из списка домашних работ.
    В случае успеха, возвращает подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if homework_name is None:
        raise HomeworkMissingException(
            f'`homework_name` отсутствует: {homework_name}')
    if homework_status not in HOMEWORK_VERDICTS:
        error_message = (
            f'Получен неизвестный статус домашней работы: {homework_status}')
        logger.exception(error_message)
        raise UnknownStatusException(error_message)
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения."""
    params = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    available = all(params)
    if not available:
        logger.critical('Отсутствует обязательная переменная окружения,'
                        'Программа принудительно остановлена.')
    return True


def handle_error(bot, message):
    """Отправляет сообщение в телеграм, если оно еще не передавалось."""
    if type(message) == TelegramAPIException:
        logger.exception('Telegram API не вернул ответ.')

    message = str(message)
    error = errors_occured.get(message)
    if not error:
        errors_occured[message] = int(time.time())
        send_message(bot, '[WARNING] ' + message)


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствие обязательных переменных окружения')
        raise SystemExit('Критическая ошибка, бот остановлен!')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    cache_cleared = current_timestamp

    while True:
        if int(time.time()) - cache_cleared > ERROR_CACHE_LIFETIME:
            errors_occured.clear()
            try:
                response = get_api_answer(current_timestamp)
                homeworks = check_response(response)

                if homeworks:
                    message = parse_status(homeworks[0])
                    send_message(bot, message)
                else:
                    logger.debug('Нет новых статусов')

                current_timestamp = int(time.time())
            except Exception as error:
                handle_error(bot, error)
            finally:
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
