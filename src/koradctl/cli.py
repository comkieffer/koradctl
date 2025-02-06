import contextlib
import sys

import click
from click_option_group import MutuallyExclusiveOptionGroup, optgroup
from serial.serialutil import SerialException

from koradctl.port import get_port
from koradctl.psu import PowerSupply
from koradctl.test import TestSuite

from .rate_limit import RateLimit


def truthy(arg: str) -> bool | str:
    match arg.lower():
        case "1" | "on" | "yes" | "true":
            return True
        case "0" | "off" | "no" | "false":
            return False
        case _:
            raise TypeError("Not a truthy or falsy value")


def on_off(value: bool) -> str:  # noqa: FBT001
    return "On" if value else "Off"


pass_psu = click.make_pass_decorator(PowerSupply)


@click.group()
@optgroup.group("Serial Port Options")
@optgroup.option(
    "-p",
    "--port",
    default="/dev/ttyACM0",
    help="The serial port to use",
)
@optgroup.option(
    "-b",
    "--baudrate",
    type=int,
    default=9600,
    help="The serial port baudrate",
)
@click.version_option(package_name="aht-korad")
@click.pass_context
def main(ctx: click.Context, port: str, baudrate: int) -> None:
    try:
        serial_port = get_port(port, baudrate)
    except SerialException:
        print("ERROR: Failed to connect to the power supply...", file=sys.stderr)
        sys.exit(1)

    psu = PowerSupply(serial_port)
    if not psu.is_tested():
        print("WARNING: this power supply is not fully tested", file=sys.stderr)

    ctx.obj = psu


@main.command("set")
@optgroup.option("-c", "--channel", default=1, type=int, help="The channel to control")
@optgroup.group("Output Setup Options")
@optgroup.option("-v", "--voltage", type=float, help="Set the output voltage")
@optgroup.option("-i", "--current", type=float, help="Set the current limit")
@optgroup.option("--ocp", is_flag=True, help="Set over current protection")
@optgroup.option("--ovp", is_flag=True, help="Set over voltage protection")
@optgroup.group("Output Enable Options", cls=MutuallyExclusiveOptionGroup)
@optgroup.option("-e", "--enable", is_flag=True, type=truthy, help="Enable the output")
@optgroup.option(
    "-d", "--disable", is_flag=True, type=truthy, help="Disable the output"
)
@optgroup.option(
    "-t",
    "--toggle",
    is_flag=True,
    type=truthy,
    help="Toggle the state of the power supply",
)
@pass_psu
def set_state(  # noqa: PLR0913
    psu: PowerSupply,
    channel: int,
    voltage: float | None,
    current: float | None,
    *,
    ocp: bool,
    ovp: bool,
    enable: bool,
    disable: bool,
    toggle: bool,
) -> None:
    """Set voltage, current limit, OCP, OVP, ..."""
    try:
        if ocp is not None:
            psu.set_ocp_state(enabled=ocp)
            print(f"OCP:     request: {on_off(ocp):-5s}")

        if ovp is not None:
            psu.set_ovp_state(enabled=ovp)
            print(f"OVP:     request: {on_off(ovp):-5s}")

        if voltage is not None:
            psu.set_voltage_setpoint(voltage, channel=channel)
            print(
                f"Voltage: request: {voltage:2.2f}, "
                f"result: {psu.get_voltage_setpoint().value:2.2f}"
            )

        if current is not None:
            psu.set_current_setpoint(current, channel=channel)
            print(
                f"Current: request: {current:1.3f}, "
                f"result: {psu.get_current_setpoint().value:1.3f}"
            )

        if any((enable, disable, toggle)):
            if enable:
                new_state = True
            elif disable:
                new_state = False
            else:  # toggle
                new_state = not psu.is_output_enabled()

            psu.set_output_state(enabled=new_state)
            print(
                f"Enable:  request: {on_off(new_state):-5s}, "
                f"result: {on_off(psu.is_output_enabled()):-5s}"
            )
    except SerialException:
        print("ERROR: The power supply appears to have gone away...", file=sys.stderr)


@main.command()
@pass_psu
def identify(psu: PowerSupply) -> None:
    """Print the device model and serial number (if available)."""
    try:
        print(f"Device identity: {psu.identity}")

        serial = psu.get_serial_number()
        if serial is not None:
            print(f"Serial Number: {serial}")
    except SerialException:
        print("ERROR: The power supply appears to have gone away...", file=sys.stderr)


@main.command()
@pass_psu
def test(psu: PowerSupply) -> None:
    """
    Test the power supply.

    Ensure that the power supply is fully supported by this library. The test suite
    expects a 2.5 ohm load on the output. It will repeatedly enable and disable the
    output with different configurations of COP, OVP and current limits.
    """
    try:
        t = TestSuite(psu)
        t.run()
    except SerialException:
        print("ERROR: The power supply appears to have gone away...", file=sys.stderr)


@main.command()
@click.option(
    "-f",
    "-frequency",
    type=float,
    default=1,
    help="Frequency of monitor readings (in Hz)",
)
@click.option(
    "-c",
    "--count",
    type=int,
    default=0,
    help="Number of readings to capture (0 = forever)",
)
@click.option(
    "-o", "--off-on-ext", is_flag=True, help="Turn of the power supply on exit."
)
@pass_psu
def monitor(
    psu: PowerSupply, frequency: float, count: int, off_on_exit: bool  # noqa: FBT001
) -> None:
    """Monitor current and voltage."""
    rate = RateLimit(rate_hz=frequency)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            while count != 0:
                count -= 1

                v, i, p = psu.get_output_readings()
                print(f"Output: {v.value:2.2f} v, {i.value:1.3f} A, {p.value:2.2f} W")

                rate.sleep()
    except SerialException:
        print("ERROR: The power supply appears to have gone away...", file=sys.stderr)

    else:
        # If we caught a serial exception, we won't be able to talk to the power supply
        # to power it off.
        if off_on_exit:
            psu.disable_output()
            print(
                f"Enable:  request: {'Off':-5s}, "
                f"result: {on_off(psu.is_output_enabled()):-5s}"
            )
