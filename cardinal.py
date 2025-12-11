"""
Модуль обратной совместимости для плагинов FunPayCardinal.

Этот модуль обеспечивает совместимость плагинов, написанных для оригинального
FunPayCardinal, с форком FunPaySigma. Все импорты из 'cardinal' автоматически
перенаправляются на 'sigma'.

Пример использования в плагинах:
    from cardinal import Cardinal  # Работает как в FunPayCardinal, так и в FunPaySigma
    
Для TYPE_CHECKING:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from cardinal import Cardinal  # Также работает
"""

from sigma import *
from sigma import Cardinal, PluginData, get_cardinal

# Реэкспортируем все публичные имена из sigma
__all__ = ['Cardinal', 'PluginData', 'get_cardinal']
