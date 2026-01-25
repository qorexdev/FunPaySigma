from locales.localizer import Localizer
localizer = Localizer()
_ = localizer.translate

class ParamNotFoundError(Exception):

    def __init__(self, param_name: str):

        self.param_name = param_name

    def __str__(self):
        return _("exc_param_not_found", self.param_name)

class EmptyValueError(Exception):

    def __init__(self, param_name: str):

        self.param_name = param_name

    def __str__(self):
        return _("exc_param_cant_be_empty", self.param_name)

class ValueNotValidError(Exception):

    def __init__(self, param_name: str, current_value: str, valid_values: list[str | None]):

        self.param_name = param_name
        self.current_value = current_value
        self.valid_values = valid_values

    def __str__(self):
        return _("exc_param_value_invalid", self.param_name, self.valid_values, self.current_value)

class ProductsFileNotFoundError(Exception):

    def __init__(self, goods_file_path: str):
        self.goods_file_path = goods_file_path

    def __str__(self):
        return _("exc_goods_file_not_found", self.goods_file_path)

class NoProductsError(Exception):

    def __init__(self, goods_file_path: str):
        self.goods_file_path = goods_file_path

    def __str__(self):
        return _("exc_goods_file_is_empty", self.goods_file_path)

class NotEnoughProductsError(Exception):

    def __init__(self, goods_file_path: str, available: int, requested: int):

        self.goods_file_path = goods_file_path
        self.available = available
        self.requested = requested

    def __str__(self):
        return _("exc_not_enough_items", self.goods_file_path, self.requested, self.available)

class NoProductVarError(Exception):

    def __init__(self):
        pass

    def __str__(self):
        return _("exc_no_product_var")

class SectionNotFoundError(Exception):

    def __init__(self):
        pass

    def __str__(self):
        return _("exc_no_section")

class SubCommandAlreadyExists(Exception):

    def __init__(self, command: str):
        self.command = command

    def __str__(self):
        return _("exc_cmd_duplicate", self.command)

class DuplicateSectionErrorWrapper(Exception):

    def __init__(self):
        pass

    def __str__(self):
        return _("exc_section_duplicate")

class ConfigParseError(Exception):

    def __init__(self, config_path: str, section_name: str, exception: Exception):
        self.config_path = config_path
        self.section_name = section_name
        self.exception = exception

    def __str__(self):
        return _("exc_cfg_parse_err", self.config_path, self.section_name, self.exception)

class FieldNotExistsError(Exception):

    def __init__(self, field_name: str, plugin_file_name: str):
        self.field_name = field_name
        self.plugin_file_name = plugin_file_name

    def __str__(self):
        return _("exc_plugin_field_not_found", self.plugin_file_name, self.field_name)
