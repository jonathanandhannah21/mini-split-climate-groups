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

MODE_COOL: Final = "cool"
MODE_HEAT: Final = "heat"
MODES: Final = (MODE_COOL, MODE_HEAT)

WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Member status values exposed to the card
STATUS_UNAVAILABLE: Final = "unavailable"
STATUS_PAUSED: Final = "paused"
STATUS_DRIVING: Final = "driving"
STATUS_RUNNING: Final = "running"
STATUS_WANTS_HEAT: Final = "wants_heat"
STATUS_WANTS_COOL: Final = "wants_cool"
STATUS_AT_TARGET: Final = "at_target"
STATUS_IDLE: Final = "idle"
STATUS_MANUAL_ON: Final = "on"
STATUS_MANUAL_OFF: Final = "off"

SERVICE_SET_TARGET_TEMPERATURE: Final = "set_target_temperature"
SERVICE_SET_TOLERANCE: Final = "set_tolerance"
SERVICE_SET_HYSTERESIS: Final = "set_hysteresis"
SERVICE_SET_PRIORITY_ORDER: Final = "set_priority_order"
SERVICE_RESET_TO_DEFAULT: Final = "reset_to_default"
SERVICE_SET_AUTOMATION: Final = "set_automation"
SERVICE_SET_MODE: Final = "set_mode"
SERVICE_SET_MEMBER_POWER: Final = "set_member_power"
SERVICE_SET_SCHEDULES: Final = "set_schedules"

ATTR_MEMBER_ID: Final = "member_id"
ATTR_TEMPERATURE: Final = "temperature"
ATTR_TOLERANCE: Final = "tolerance"
ATTR_HYSTERESIS: Final = "hysteresis"
ATTR_PRIORITY_ORDER: Final = "priority_order"
ATTR_MEMBERS: Final = "members"
ATTR_CURRENT_PRIORITY: Final = "current_priority"
ATTR_DEFAULT_PRIORITY: Final = "default_priority"
ATTR_AUTOMATION: Final = "automation"
ATTR_ENABLED: Final = "enabled"
ATTR_MODE: Final = "mode"
ATTR_GROUP_MODE: Final = "group_mode"
ATTR_ON: Final = "on"
ATTR_SCHEDULES: Final = "schedules"
ATTR_ACTIVE_SCHEDULE: Final = "active_schedule"
ATTR_DRIVING_MEMBER: Final = "driving_member"

STORAGE_VERSION = 1
STORAGE_KEY = "mini_split_climate_groups_store"
