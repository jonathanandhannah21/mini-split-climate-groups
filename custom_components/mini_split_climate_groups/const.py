"""Constants for the Mini Split Climate Groups integration."""
from typing import Final

DOMAIN: Final = "mini_split_climate_groups"

CONF_MEMBERS: Final = "members"
CONF_CLIMATE_ENTITY: Final = "climate_entity"
CONF_TEMP_SENSOR: Final = "temp_sensor"
CONF_TARGET_TEMP: Final = "target_temp"
CONF_TOLERANCE: Final = "tolerance"
CONF_HYSTERESIS: Final = "hysteresis"
CONF_PRIORITY_SCHEDULE: Final = "priority_schedule"
CONF_CURRENT_PRIORITY: Final = "current_priority"
CONF_ADD_ANOTHER: Final = "add_another"
CONF_MEMBER_NAME: Final = "name"

DEFAULT_TOLERANCE: Final = 1.5
DEFAULT_HYSTERESIS: Final = 0.1
DEFAULT_TARGET_TEMP: Final = 72
MIN_TARGET_TEMP: Final = 60
MAX_TARGET_TEMP: Final = 85

UPDATE_INTERVAL: Final = 30

SERVICE_SET_TARGET_TEMPERATURE: Final = "set_target_temperature"
SERVICE_SET_TOLERANCE: Final = "set_tolerance"
SERVICE_SET_PRIORITY_ORDER: Final = "set_priority_order"
SERVICE_RESET_TO_DEFAULT: Final = "reset_to_default"

ATTR_MEMBER_ID: Final = "member_id"
ATTR_TEMPERATURE: Final = "temperature"
ATTR_TOLERANCE: Final = "tolerance"
ATTR_PRIORITY_ORDER: Final = "priority_order"
ATTR_MEMBERS: Final = "members"
ATTR_CURRENT_PRIORITY: Final = "current_priority"

STORAGE_VERSION = 1
STORAGE_KEY = "mini_split_climate_groups_store"