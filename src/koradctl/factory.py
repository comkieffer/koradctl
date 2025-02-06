import re
from dataclasses import dataclass

from serial import Serial

from .psu import DualChannelPowerSupply, PowerSupply, SingleChannelPowerSupply


@dataclass
class PowerSupplyDescription:
    matcher: str | re.Pattern

    cls: type[PowerSupply]


# Firmwares that have been tested with this library.
#
# Before adding a new firmware here, run `test.py` against it to make sure that it is
# fully supported.
#
# If the power supply reports a serial number in its answer to `get_identity`, capture
# it is a regex group so that `get_serial_number` can return it.
TESTED_POWER_SUPPLIES = [
    PowerSupplyDescription(matcher="TENMA 72-2540 V2.1", cls=SingleChannelPowerSupply),
    PowerSupplyDescription(
        matcher=re.compile(r"^TENMA 72-2540 V5.8 SN:(?P<serial_number>\d+)$"),
        cls=DualChannelPowerSupply,
    ),
]


def _get_power_supply_description(identity: str) -> PowerSupplyDescription | None:
    for description in TESTED_POWER_SUPPLIES:
        match description.matcher:
            case re.Pattern():
                if description.matcher.fullmatch(identity):
                    return description
            case str():
                if description == identity:
                    return description
            case _:
                raise TypeError("Unsupported type in 'TESTED_POWER_SUPPLIES'.")

    return None


def make_power_supply(serial: Serial) -> PowerSupply:
    psu = PowerSupply(serial)

    description = _get_power_supply_description(psu.identity)
    if description:
        return description.cls(serial)

    return psu
