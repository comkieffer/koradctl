import re
from datetime import datetime
from time import sleep

from serial import Serial

from koradctl.pretty import Reading, Status, pretty_reading, pretty_status

# i used the sigrok page for reference:
#     https://sigrok.org/wiki/Korad_KAxxxxP_series
#
# i have a Tenma 72-2540, and the only discrepancy i've found is
# in the status byte, where bit 7 (0x80) indicates the "OVP and/or
# OCP status", instead of bit 5 (0x20)...

# it is important that commands aren't issued too quickly... instead
# we impose a gap of at least ~50ms between commands
INTER_COMMAND_DELAY = 0.05

# Firmwares that have been tested with this library.
#
# Before adding a new firmware here, run `test.py` against it to make sure that it is
# fully supported.
#
# If the power supply reports a serial number in its answer to `get_identity`, capture
# it is a regex group so that `get_serial_number` can return it.
tested_firmware = [
    "TENMA 72-2540 V2.1",
    re.compile(r"^TENMA 72-2540 V5.8 SN:(?P<serial_number>\d+)$"),
]


class PowerSupply:
    def __init__(self, port: Serial) -> None:
        self.last_command: datetime | None = None
        self.port = port

    def insert_command_delay(self) -> None:
        last_command = self.last_command
        self.last_command = datetime.now()

        if last_command is None:
            return

        time_since_last_command = (datetime.now() - last_command).total_seconds()
        time_until_next_command = INTER_COMMAND_DELAY - time_since_last_command

        if time_until_next_command < 0:
            return

        sleep(time_until_next_command)

    def issue_command(
        self,
        command: bytes | str,
        max_response_size: int = 1000,
        *,
        wait_for_response: bool = True,
        allow_retry: bool = False,
    ) -> bytes | None:
        """
        Write the bytes of a command to the serial port.

        This function is really for internal use... you shouldn't need to call it
        will encode the command (if necessary), and then wait for a response
        of up to max_response_size. this is useful for commands that expect a
        binary response.
        """
        if isinstance(command, str):
            command = command.encode("ascii")

        self.insert_command_delay()

        self.port.write(command)

        if not wait_for_response:
            return None

        for _i in range(10 if allow_retry else 1):
            response = self.port.read(max_response_size)
            if len(response) != 0:
                break

            # retry issuing the command
            self.port.write(command)

        return response

    def issue_command_trim(
        self,
        command: bytes | str,
        max_response_size: int = 1000,
        *,
        wait_for_response: bool = True,
        allow_retry: bool = False,
        trim_chars: bytes = b"\x00",
    ) -> bytes | None:
        """
        Send a command and trim trailing characters.

        This function is really for internal use... you shouldn't need to call it,
        it will call issue_command(), and then trim the response by removing any
        trim_chars from the right-hand side. this is useful for commands that
        expect an ASCII response, as sometimes trailing NULs are received.
        """
        response = self.issue_command(
            command,
            max_response_size,
            wait_for_response=wait_for_response,
            allow_retry=allow_retry,
        )

        if response is None:
            return None

        return response.rstrip(trim_chars)

    def get_identity(self) -> str:
        """Get the power supply's identity string, e.g: "TENMA 72-2540 V2.1"."""
        response = self.issue_command_trim("*IDN?", allow_retry=True)
        if response is None:
            raise RuntimeError("Powersupply failed to answer command.")

        return response.decode("ascii")

    def get_serial_number(self) -> str | None:
        """Get the power supply's serial number if possible, otherwise return None."""
        identity = self.get_identity()
        for version in tested_firmware:
            # We can only extract the serial number if the version is a regex.
            if isinstance(version, re.Pattern) and (
                match := version.fullmatch(identity)
            ):
                return match.group("serial_number")

        return None

    def is_tested(self) -> bool:
        """
        Check whether the power supply is known to work.

        Check whether the connected power supply has been tested against
        this codebase... when adding new power supplies, please check
        all commands and responses before adding to the tested_firmware
        list.
        """
        identity = self.get_identity()
        for version in tested_firmware:
            if isinstance(version, re.Pattern):
                if version.fullmatch(identity):
                    return True
            elif isinstance(version, str):
                if version == identity:
                    return True
            else:
                raise TypeError("Unsupported type in 'tested_firmware'.")

        return False

    def get_status(self) -> Status:
        response = self.issue_command("STATUS?", allow_retry=True)
        if response is None:
            raise RuntimeError("Powersupply failed to answer command.")

        return pretty_status(response)

    def get_output_state(self) -> bool:
        return self.get_status().output_enabled

    def set_output_state(self, enabled: bool) -> None:  # noqa: FBT001
        self.issue_command("OUT1" if enabled else "OUT0", wait_for_response=False)

    def get_ovp_ocp_state(self) -> bool:
        return self.get_status().ovp_ocp_enabled

    def set_ocp_state(self, enabled: bool) -> None:  # noqa: FBT001
        self.issue_command("OCP1" if enabled else "OCP0", wait_for_response=False)

    def set_ovp_state(self, enabled: bool) -> None:  # noqa: FBT001
        self.issue_command("OVP1" if enabled else "OVP0", wait_for_response=False)

    def get_voltage_setpoint(self) -> Reading:
        response = self.issue_command_trim("VSET1?", allow_retry=True)
        if response is None:
            raise RuntimeError("Powersupply failed to answer command.")

        return pretty_reading(response, "V")

    def set_voltage_setpoint(self, voltage: float) -> None:
        self.issue_command(f"VSET1:{voltage:2.2f}", wait_for_response=False)

    def get_current_setpoint(self) -> Reading:
        response = self.issue_command_trim("ISET1?", allow_retry=True)
        if response is None:
            raise RuntimeError("Powersupply failed to answer command.")

        return pretty_reading(response, "I")

    def set_current_setpoint(self, current: float) -> None:
        self.issue_command(f"ISET1:{current:1.3f}", wait_for_response=False)

    def get_output_voltage(self) -> Reading:
        response = self.issue_command_trim("VOUT1?", allow_retry=True)
        if response is None:
            raise RuntimeError("Powersupply failed to answer command.")

        return pretty_reading(response, "V")

    def get_output_current(self) -> Reading:
        response = self.issue_command_trim("IOUT1?", allow_retry=True)
        if response is None:
            raise RuntimeError("Powersupply failed to answer command.")

        return pretty_reading(response, "I")

    def get_output_power(self) -> Reading:
        return self.get_output_readings()[2]

    def get_output_readings(self) -> tuple[Reading, Reading, Reading]:
        v = self.get_output_voltage()
        i = self.get_output_current()
        p = pretty_reading(i.value * v.value, "W")
        return v, i, p
