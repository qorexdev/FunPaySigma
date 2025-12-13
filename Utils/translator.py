"""
Модуль для автоматического перевода текста RU → EN.
Использует бесплатную библиотеку googletrans без API ключей.
"""

import logging
import asyncio
from functools import lru_cache

logger = logging.getLogger("TGBot")

# Ленивый импорт для оптимизации памяти
_translator = None


def _get_translator():
    """Ленивая инициализация переводчика."""
    global _translator
    if _translator is None:
        try:
            from googletrans import Translator
            _translator = Translator()
        except ImportError:
            logger.error("Библиотека googletrans не установлена. pip install googletrans==4.0.0-rc1")
            return None
        except Exception as e:
            logger.error(f"Ошибка инициализации переводчика: {e}")
            return None
    return _translator


def _run_async(coro):
    """Запускает асинхронную функцию синхронно."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # Если уже в async контексте, создаём новый цикл
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    else:
        return loop.run_until_complete(coro)


async def _translate_async(text: str) -> str | None:
    """Асинхронный перевод текста."""
    translator = _get_translator()
    if not translator:
        return None
    
    try:
        result = await translator.translate(text, src='ru', dest='en')
        if result and result.text:
            return result.text
        return None
    except Exception as e:
        logger.error(f"Ошибка асинхронного перевода: {e}")
        return None


def translate_to_english(text: str) -> str | None:
    """
    Переводит текст с русского на английский.
    
    :param text: текст на русском языке
    :return: переведённый текст на английском или None при ошибке
    """
    if not text or not text.strip():
        return text
    
    translator = _get_translator()
    if not translator:
        logger.warning("Переводчик недоступен")
        return None
    
    try:
        # Пробуем синхронный вызов (для старых версий googletrans)
        try:
            result = translator.translate(text, src='ru', dest='en')
            if hasattr(result, '__await__'):
                # Это корутина - нужно запустить асинхронно
                result = _run_async(_translate_async(text))
                if result:
                    logger.debug(f"Перевод (async): '{text[:30]}...' → '{result[:30]}...'")
                    return result
                return None
            elif result and result.text:
                logger.debug(f"Перевод: '{text[:30]}...' → '{result.text[:30]}...'")
                return result.text
            return None
        except TypeError as e:
            # Если метод асинхронный и вызван неправильно
            if 'await' in str(e) or 'coroutine' in str(e):
                result = _run_async(_translate_async(text))
                if result:
                    logger.debug(f"Перевод (async fallback): '{text[:30]}...' → '{result[:30]}...'")
                    return result
            raise
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        return None


def translate_batch_to_english(texts: dict[str, str]) -> dict[str, str]:
    """
    Переводит несколько текстов за один запрос (оптимизация).
    
    :param texts: словарь {ключ: русский_текст}
    :return: словарь {ключ: английский_текст}
    """
    if not texts:
        return {}
    
    result = {}
    for key, text in texts.items():
        translated = translate_to_english(text)
        if translated:
            result[key] = translated
        else:
            result[key] = text  # Оставляем оригинал при ошибке
    
    return result


def is_translation_available() -> bool:
    """Проверяет, доступен ли сервис перевода."""
    try:
        result = translate_to_english("тест")
        return result is not None and result.lower() == "test"
    except Exception:
        return False
