import importlib.metadata
import importlib.util
import pathlib
import sys
from time import sleep

from serial.serialutil import SerialException

from koradctl.args import get_args
from koradctl.port import get_port
from koradctl.psu import PowerSupply
from koradctl.test import TestSuite


def get_package_name() -> str | None:
    file_dir = pathlib.Path(__file__).parent
    spec = importlib.util.spec_from_file_location(
        "module.name", file_dir / "__init__.py"
    )

    if spec is None:
        return None

    module = importlib.util.module_from_spec(spec)

    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.__package__


def get_package_version(package_name: str) -> str:
    return importlib.metadata.version(package_name)


class Cli:
    def __init__(self) -> None:
        self.args = get_args()

        if self.args.show_version:
            me = get_package_name()
            ver = get_package_version(me) if me else "Unknown"
            print(f"{me} version {get_package_version(ver)}")
            sys.exit(0)

        try:
            self.port = get_port(self.args.port, self.args.baudrate)
        except SerialException:
            print("ERROR: Failed to connect to the power supply...", file=sys.stderr)
            sys.exit(0)

        self.psu = PowerSupply(self.port)

    def run(self) -> None:
        if self.args.test:
            self.run_tests()
        elif self.args.identify:
            print(f"Device identity: {self.psu.get_identity()}")

            serial = self.psu.get_serial_number()
            if serial is not None:
                print(f"Serial Number: {serial}")

        self.run_noninteractive()

    def run_tests(self) -> None:
        t = TestSuite(self.psu)
        t.run()

    def run_noninteractive(self) -> None:  # noqa: C901, PLR0912
        if not self.psu.is_tested():
            print("WARNING: this power supply is not fully tested", file=sys.stderr)

        if self.args.over_current_protection is not None:
            self.psu.set_ocp_state(enabled=self.args.over_current_protection)
            print(
                "OCP:     request: %-5s"
                % ("On" if self.args.over_current_protection else "Off",)
            )

        if self.args.over_voltage_protection is not None:
            self.psu.set_ovp_state(enabled=self.args.over_voltage_protection)
            print(
                "OVP:     request: %-5s"
                % ("On" if self.args.over_voltage_protection else "Off",)
            )

        if self.args.voltage is not None:
            self.psu.set_voltage_setpoint(self.args.voltage)
            print(
                f"Voltage: request: {self.args.voltage:2.2f}, "
                f"result: {self.psu.get_voltage_setpoint().value:2.2f}"
            )

        if self.args.current is not None:
            self.psu.set_current_setpoint(self.args.current)
            print(
                f"Current: request: {self.args.current:1.3f}, "
                f"result: {self.psu.get_current_setpoint().value:1.3f}"
            )

        if self.args.output_enable is not None:
            if self.args.output_enable == "toggle":
                new_state = not self.psu.is_output_enabled()
            else:
                new_state = self.args.output_enable

            self.psu.set_output_state(enabled=new_state)
            print(
                "Enable:  request: %-5s, result: %-5s"
                % (
                    "On" if new_state else "Off",
                    "On" if self.psu.is_output_enabled() else "Off",
                )
            )

        if self.args.monitor or self.args.monitor_loop:
            self.print_output_readings()

        if self.args.monitor_loop:
            try:
                while True:
                    sleep(self.args.monitor_freq)
                    self.print_output_readings()
            except KeyboardInterrupt:
                print()  # this puts the terminal's ^C on a line by itself

        if self.args.off_on_exit:
            self.psu.set_output_state(enabled=False)
            print(
                "Enable:  request: %-5s, result: %-5s"
                % (
                    "Off",
                    "On" if self.psu.is_output_enabled() else "Off",
                )
            )

    def print_output_readings(self) -> None:
        v, i, p = self.psu.get_output_readings()
        print(f"Output: {v.value:2.2f} v, {i.value:1.3f} A, {p.value:2.2f} W")
