import asyncio
import time
import traceback
from typing import Callable, Optional

from runze_syringe_pump import RunzeSyringePump, RunzeSyringePumpMode, RunzeSyringePumpInfo, RunzeSyringePumpConnectionError
from pr1 import ureg
from pr1.devices.nodes.collection import DeviceNode
from pr1.devices.nodes.common import NodeId, NodeUnavailableError
from pr1.devices.nodes.numeric import NumericNode
from pr1.devices.nodes.primitive import EnumNode, EnumNodeCase
from pr1.devices.nodes.readable import PollableReadableNode, StableReadableNode
from pr1.util.asyncio import aexit_handler, run_double, shield
from pr1.util.pool import Pool
from quantops import Quantity

from . import logger, namespace


valve_info = {
    "I": "Input",
    "O": "Output",
    "B": "ByPass",
    "E": "Extra",
    "?": "Unknown"
}

speed_grade = {
    "0" : "  1.25 s/travel",
    "1" : "  1.30 s/travel",
    "2" : "  1.39 s/travel",
    "3" : "  1.52 s/travel",
    "4" : "  1.71 s/travel",
    "5" : "  1.97 s/travel",
    "6" : "  2.37 s/travel",
    "7" : "  2.77 s/travel",
    "8" : "  3.03 s/travel",
    "9" : "  3.36 s/travel",
    "10": "  3.37 s/travel",
    "11": "  4.30 s/travel",
    "12": "  5.00 s/travel",
    "13": "  6.00 s/travel",
    "14": "  7.50 s/travel",
    "15": " 10.00 s/travel",
    "16": " 15.00 s/travel",
    "17": " 30.00 s/travel",
    "18": " 31.58 s/travel",
    "19": " 33.33 s/travel",
    "20": " 35.29 s/travel",
    "21": " 37.50 s/travel",
    "22": " 40.00 s/travel",
    "23": " 42.86 s/travel",
    "24": " 46.15 s/travel",
    "25": " 50.00 s/travel",
    "26": " 54.55 s/travel",
    "27": " 60.00 s/travel",
    "28": " 66.67 s/travel",
    "29": " 75.00 s/travel",
    "30": " 85.71 s/travel",
    "31": "100.00 s/travel",
    "32": "120.00 s/travel",
    "33": "150.00 s/travel",
    "34": "200.00 s/travel",
    "35": "300.00 s/travel",
    "36": "333.33 s/travel",
    "37": "375.00 s/travel",
    "38": "428.00 s/travel",
    "39": "500.00 s/travel",
    "40": "600.00 s/travel",
}


class RunzeValvePositionNode(EnumNode[str], StableReadableNode):
    def __init__(
        self,
        *,
        master: 'RunzeSyringePumpDevice'
    ):
        super().__init__(
            cases=[EnumNodeCase(id, label=label) for id, label in valve_info.items()],
            readable=True,
            writable=True
        )

        self.id = NodeId("valve_position")
        self.icon = "360"
        self.label = "Valve Position"

        self._master = master

    async def __aenter__(self):
        assert (device := self._master._device)

        self.connected = True

    @aexit_handler
    async def __aexit__(self):
        self.connected = False

    async def _read(self):
        assert (device := self._master._device)

        try:
            valve_position = await device.query_valve_position()
            self.value = (time.time(), valve_position)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e

    async def _write(self, value: str, /):
        assert (device := self._master._device)

        try:
            await device.set_valve_position(value)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e


class RunzeStepModeNode(EnumNode[int], StableReadableNode):
    def __init__(
        self,
        *,
        master: 'RunzeSyringePumpDevice'
    ):
        super().__init__(
            cases=[EnumNodeCase(id, label=label.name) for id, label in RunzeSyringePumpMode._value2member_map_.items()],
            readable=True,
            writable=True
        )

        self.id = NodeId("step_mode")
        self.icon = "360"
        self.label = "StepMode"

        self._master = master

    async def __aenter__(self):
        assert (device := self._master._device)

        self.connected = True

    @aexit_handler
    async def __aexit__(self):
        self.connected = False
    
    async def _read(self):
        assert (device := self._master._device)

        try:
            self.value = (time.time(), await device.query_step_mode().value)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError

    async def _write(self, value: int, /):
        assert (device := self._master._device)

        try:
            await device.set_step_mode(RunzeSyringePumpMode._value2member_map_[value])
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e


class RunzeSpeedGradeNode(EnumNode[str], StableReadableNode):
    def __init__(
        self,
        *,
        master: 'RunzeSyringePumpDevice'
    ):
        super().__init__(
            cases=[EnumNodeCase(id, label=label) for id, label in speed_grade.items()],
            readable=True,
            writable=True
        )

        self.id = NodeId("plunger_speed_grade")
        self.icon = "360"
        self.label = "Speed"

        self._master = master

    async def __aenter__(self):
        assert (device := self._master._device)

        self.connected = True

    @aexit_handler
    async def __aexit__(self):
        self.connected = False
    
    async def _read(self):
        assert (device := self._master._device)

        try:
            self.value = (time.time(), await device.query_speed_grade())
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError

    async def _write(self, value: str, /):
        assert (device := self._master._device)

        try:
            await device.set_speed_grade(value)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e


class RunzeSpeedSetpointNode(NumericNode, StableReadableNode):
    def __init__(
        self,
        *,
        master: 'RunzeSyringePumpDevice'
    ):
        super().__init__(
            context="flowrate",
            readable=True,
            writable=True,
            range=(0.0 * ureg.ul / ureg.s, 25000.0 * ureg.ul / ureg.s),
            resolution=(0.1 * ureg.ul / ureg.s)
        )

        self.id = NodeId("set_plunger_speed")
        self.icon = "360"
        self.label = "FlowRate"

        self._master = master

    async def __aenter__(self):
        assert (device := self._master._device)

        self.connected = True

    @aexit_handler
    async def __aexit__(self):
        self.connected = False
    
    async def _read(self):
        assert (device := self._master._device)

        try:
            pulse_freq, speed = await device.query_speed_max()
            self.value = (time.time(), speed * ureg.ul / ureg.s)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError

    async def _write(self, value: Quantity, /):
        assert (device := self._master._device)

        value_in_unit = value.magnitude_as(ureg.ul / ureg.s)
        try:
            await device.set_speed_max(int(value_in_unit))
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e


class RunzePlungerSetpointNode(NumericNode, StableReadableNode):
    def __init__(
        self,
        *,
        master: 'RunzeSyringePumpDevice',
        volume: float
    ):
        super().__init__(
            context="volume",
            readable=True,
            writable=True,
            range=(0.0 * ureg.ul, 25000.0 * ureg.ul),
            resolution=(0.1 * ureg.ul)
        )

        self.id = NodeId("plunger_position")
        self.icon = "360"
        self.label = "Plunger Position Setpoint"

        self._master = master
        self._volume = volume

    async def __aenter__(self):
        assert (device := self._master._device)

        if (observed_volume := device.volume) != self._volume:
            logger.error(f"Invalid volume, found {observed_volume}, expected {self._volume}")
            raise NodeUnavailableError

        self.connected = True

    @aexit_handler
    async def __aexit__(self):
        self.connected = False

    async def _read(self):
        assert (device := self._master._device)

        try:
            self.value = (time.time(), await device.query_plunger_position() * ureg.ul)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e

    async def _write(self, value: float, /):
        assert (device := self._master._device)

        try:
            await device.move_plunger_to(value)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e


class RunzePlungerReadoutNode(NumericNode, PollableReadableNode):
    def __init__(
        self,
        *,
        master: 'RunzeSyringePumpDevice',
        volume: float
    ):
        super().__init__(
            context="volume",
            readable=True,
            writable=True,
            range=(0.0 * ureg.ul, 25000.0 * ureg.ul),
            poll_interval=2,
            resolution=(0.1 * ureg.ul)
        )

        self.id = NodeId("plunger_position")
        self.icon = "360"
        self.label = "Plunger Position Readout"

        self._master = master
        self._volume = volume

    async def __aenter__(self):
        assert (device := self._master._device)

        if (observed_volume := device.volume) != self._volume:
            logger.error(f"Invalid volume, found {observed_volume}, expected {self._volume}")
            raise NodeUnavailableError

        self.connected = True

    @aexit_handler
    async def __aexit__(self):
        self.connected = False

    async def _read(self):
        assert (device := self._master._device)

        try:
            self.value = (time.time(), await device.report_position() * ureg.ul)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e
    
    async def _write(self, value: Quantity, /):
        assert (device := self._master._device)
        value_in_unit = value.magnitude_as(ureg.ul)
        logger.info(f"Moving plunger to {value_in_unit} ul")

        try:
            await device.move_plunger_to(value_in_unit)
        except RunzeSyringePumpConnectionError as e:
            raise NodeUnavailableError from e


class RunzeSyringePumpDevice(DeviceNode):
    owner = namespace

    def __init__(
        self,
        *,
        port: Optional[str],
        id: str,
        label: Optional[str],
        address: Optional[str] = "1",
        volume: float = 25000
    ):
        super().__init__()

        self.connected = False
        self.description = "Runze syringe pump"
        self.id = NodeId(id)
        self.label = label

        self._port = port
        self._address = address

        self._device: Optional[RunzeSyringePump] = None
        
        self.nodes = {
            "valve_position": RunzeValvePositionNode(master=self),
            # "step_mode": RunzeStepModeNode(master=self),
            "plunger_speed_grade": RunzeSpeedGradeNode(master=self),
            # "plunger_position": RunzePlungerSetpointNode(master=self, volume=volume),
            "plunger_position": RunzePlungerReadoutNode(master=self, volume=volume)
        }

    async def _connect(self):
        ready = False
        step = 0

        while True:
            self._device = await self._find_device()

            if self._device:
                logger.info(f"Configuring {self._label}")

                try:
                    try:
                        # Initialize the rotary valve
                        status = await self._device.query_device_status()
                        if status == "`" and step == 0:
                            await self._device.initialize()
                        
                        logger.info(f"{self._label} initialized")

                        self.connected = True
                        for node in self.nodes.values():
                            node.connected = True

                        async with self.nodes["valve_position"], \
                                   self.nodes["plunger_speed_grade"],\
                                   self.nodes["plunger_position"]:

                            if not ready:
                                ready = True
                                yield

                            # Wait for the device to disconnect
                            await self._device.wait_error()
                            logger.warning(f"Lost connection to {self._label}")
                    finally:
                        self.connected = False

                        await shield(self._device.close())
                        self._device = None
                except* (RunzeSyringePumpConnectionError, NodeUnavailableError):
                    pass

            # If the above failed, still mark the device as ready
            if not ready:
                ready = True
                yield
            else:
                step += 1

            # Wait before retrying
            await asyncio.sleep(2.0)

    async def _find_device(self):
        if self._port:
            return await self._create_device(lambda port = self._port: RunzeSyringePump(port))

        for info in RunzeSyringePump.list():
            if device := await self._create_device(info.create):
                return device
        else:
            return None

    async def _create_device(self, get_device: Callable[[], RunzeSyringePump], /):
        try:
            device = get_device()
        except RunzeSyringePumpConnectionError:
            return None

        try:
            await device.open()

            # Query the serial number even if not needed to detect protocol errors.
            address = device.address

            if (not self._address) or (address == self._address):
                return device
        except RunzeSyringePumpConnectionError:
            await shield(device.close())
        except BaseException:
            await shield(device.close())
            raise

        return None

    async def start(self):
        async with Pool.open() as pool:
            print("Starting Runze Syringe Pump")
            await pool.wait_until_ready(self._connect())
            
            for node in self.nodes.values():
                pool.start_soon(node.start())

            if not self.connected:
                logger.warning(f"Failed connecting to {self._label}")
            else:
                logger.info(f"Successfully Connected to {self._label}")

            yield
