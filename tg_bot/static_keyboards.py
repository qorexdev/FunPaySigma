from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
from tg_bot import CBT
from locales.localizer import Localizer

localizer = Localizer()
_ = localizer.translate


def CLEAR_STATE_BTN() -> K:
    return K().add(B(_("gl_cancel"), callback_data=CBT.CLEAR_STATE))


def REFRESH_BTN() -> K:
    return K().add(B(_("gl_refresh"), callback_data=CBT.UPDATE_PROFILE))


def SETTINGS_SECTIONS() -> K:
    return K() \
        .row(B(_("mm_language"), callback_data=f"{CBT.CATEGORY}:lang"),
             B(_("mm_global"), callback_data=f"{CBT.CATEGORY}:main")) \
        .row(B(_("mm_authorized_users"), callback_data=f"{CBT.AUTHORIZED_USERS}:0"),
             B(_("mm_proxy"), callback_data=f"{CBT.PROXY}:0")) \
        .row(B(_("mm_autodelivery"), callback_data=f"{CBT.CATEGORY}:ad"),
             B(_("mm_autoresponse"), callback_data=f"{CBT.CATEGORY}:ar")) \
        .row(B(_("mm_templates"), callback_data=f"{CBT.TMPLT_LIST}:0"),
             B(_("mm_plugins"), callback_data=f"{CBT.PLUGINS_LIST}:0")) \
        .row(B(_("mm_lots_editor"), callback_data=f"{CBT.FP_LOT_EDIT_LIST}:0")) \
        .add(B(_("gl_next"), callback_data=CBT.MAIN2))


def SETTINGS_SECTIONS_2() -> K:
    return K() \
        .row(B(_("mm_notifications"), callback_data=f"{CBT.CATEGORY}:tg"),
             B(_("mm_new_msg_view"), callback_data=f"{CBT.CATEGORY}:mv")) \
        .row(B(_("mm_greetings"), callback_data=f"{CBT.CATEGORY}:gr"),
             B(_("mm_order_confirm"), callback_data=f"{CBT.CATEGORY}:oc")) \
        .row(B(_("mm_order_reminders"), callback_data=f"{CBT.CATEGORY}:or"),
             B(_("mm_review_reply"), callback_data=f"{CBT.CATEGORY}:rr")) \
        .row(B(_("mm_blacklist"), callback_data=f"{CBT.CATEGORY}:bl"),
             B(_("mm_configs"), callback_data=CBT.CONFIG_LOADER)) \
        .row(B(_("gl_back"), callback_data=CBT.MAIN), B(_("gl_next"), callback_data=CBT.MAIN3))


def SETTINGS_SECTIONS_3() -> K:
    """Третья страница меню - встроенные модули."""
    return K() \
        .row(B("📊 Графики статистики", callback_data="graphs_Settings"),
             B("🔄 Синхронизация чатов", callback_data="sync.settings")) \
        .row(B("💬 Ответы на отзывы", callback_data="ReviewChatReply_Settings"),
             B("📈 Лимиты рейтинга", callback_data="sras_info.settings")) \
        .add(B(_("gl_back"), callback_data=CBT.MAIN2))


def AR_SETTINGS() -> K:
    return K() \
        .add(B(_("ar_edit_commands"), callback_data=f"{CBT.CMD_LIST}:0")) \
        .add(B(_("ar_add_command"), callback_data=CBT.ADD_CMD)) \
        .add(B(_("gl_back"), callback_data=CBT.MAIN))


def AD_SETTINGS() -> K:
    return K() \
        .add(B(_("ad_edit_autodelivery"), callback_data=f"{CBT.AD_LOTS_LIST}:0")) \
        .add(B(_("ad_add_autodelivery"), callback_data=f"{CBT.FP_LOTS_LIST}:0")) \
        .add(B(_("ad_edit_goods_file"), callback_data=f"{CBT.PRODUCTS_FILES_LIST}:0")) \
        .row(B(_("ad_create_goods_file"), callback_data=CBT.CREATE_PRODUCTS_FILE),
             B(_("ad_upload_goods_file"), callback_data=CBT.UPLOAD_PRODUCTS_FILE)) \
        .add(B(_("gl_back"), callback_data=CBT.MAIN))


def CONFIGS_UPLOADER() -> K:
    return K() \
        .row(B(_("cfg_download_main"), callback_data=f"{CBT.DOWNLOAD_CFG}:main"),
             B(_("cfg_upload_main"), callback_data="upload_main_config")) \
        .row(B(_("cfg_download_ar"), callback_data=f"{CBT.DOWNLOAD_CFG}:autoResponse"),
             B(_("cfg_upload_ar"), callback_data="upload_auto_response_config")) \
        .row(B(_("cfg_download_ad"), callback_data=f"{CBT.DOWNLOAD_CFG}:autoDelivery"),
             B(_("cfg_upload_ad"), callback_data="upload_auto_delivery_config")) \
        .add(B(_("gl_back"), callback_data=CBT.MAIN2))
