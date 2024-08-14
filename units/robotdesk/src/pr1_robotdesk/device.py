import asyncio
import time
import traceback
from typing import Callable, Optional

from grbl_cnc import GrblCNC, GrblCNCInfo, GrblCNCConnectionError
from gripper_rm import RMAxis
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


class GrblCNCDevice(DeviceNode):
    owner = namespace

    def __init__(
        self,
        *,
        port: Optional[str],
        id: str,
        label: Optional[str],
        address: Optional[str] = "1",
        limits: str = "-150,150,-200,0,0,60"
    ):
        super().__init__()

        self.connected = False
        self.description = "Grbl CNC"
        self.id = NodeId(id)
        self.label = label

        self._port = port
        self._address = address
        self._limits = tuple([int(x) for x in limits.split(",")])

        self._device: Optional[GrblCNC] = None
        
        self.nodes = {}

    async def _connect(self):
        ready = False
        step = 0

        while True:
            logger.info(f"GrblCNC: Searching for device, step {step}")
            self._device = await self._find_device()
            logger.info(f"GrblCNC: Found device: {self._device}")

            if self._device:
                logger.info(f"Configuring {self._label}")

                try:
                    try:
                        # Initialize the rotary valve
                        status = await self._device.query_device_status()
                        if "Idle" in status and step == 0:
                            await self._device.initialize()
                        
                        logger.info(f"{self._label} initialized")

                        self.connected = True
                        for node in self.nodes.values():
                            node.connected = True

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
                except* (GrblCNCConnectionError, NodeUnavailableError):
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
            logger.info(f"GrblCNC: Creating device with port {self._port}")
            return await self._create_device(lambda port = self._port: GrblCNC(port, limits=self._limits))

        for info in GrblCNC.list():
            if device := await self._create_device(info.create):
                return device
        else:
            return None

    async def _create_device(self, get_device: Callable[[], GrblCNC], /):
        try:
            device = get_device()
        except GrblCNCConnectionError:
            return None

        try:
            await device.open()

            # Query the serial number even if not needed to detect protocol errors.
            address = device.address

            if (not self._address) or (address == self._address):
                return device
        except GrblCNCConnectionError:
            await shield(device.close())
        except BaseException:
            await shield(device.close())
            raise

        return None

    async def start(self):
        async with Pool.open() as pool:
            logger.info("Starting Grbl CNC")
            await pool.wait_until_ready(self._connect())
            
            for node in self.nodes.values():
                pool.start_soon(node.start())

            if not self.connected:
                logger.warning(f"Failed connecting to {self._label}")
            else:
                logger.info(f"Successfully Connected to {self._label}")

            yield


class RMGripperDevice(DeviceNode):
    owner = namespace

    def __init__(
        self,
        *,
        port: Optional[str],
        id: str,
        label: Optional[str],
        address: Optional[int] = 0
    ):
        super().__init__()

        self.connected = False
        self.description = "RM Gripper"
        self.id = NodeId(id)
        self.label = label

        self._port = port
        self._address = address

        self._device: Optional[RMAxis] = None
        
        self.nodes = {}

    async def _connect(self):
        ready = False
        step = 0

        while True:
            logger.info(f"RMGripper: Searching for device, step {step}")
            self._device = await self._find_device()

            if self._device:
                logger.info(f"Configuring {self._label}")

                try:
                    try:
                        # Initialize the rotary valve
                        self._device.go_home()
                        asyncio.sleep(10)
                        
                        logger.info(f"{self._label} initialized")

                        self.connected = True
                        if not ready:
                            ready = True
                            yield
                        
                        # Wait for the device to disconnect
                        await self._device.wait_error()
                    finally:
                        self.connected = False

                        await shield(self._device.close())
                        self._device = None
                except* (NodeUnavailableError):
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
            return await self._create_device(lambda port = self._port: RMAxis.create_rmaxis_modbus_rtu(self._port, baudrate=115200, slave_id=self._address))

        # for info in RMAxis.list():
        #     if device := await self._create_device(info.create):
        #         return device
        else:
            return None

    async def _create_device(self, get_device: Callable[[], RMAxis], /):
        try:
            device = get_device()
        except:
            return None
        
        return device

        # try:
        #     await device.open()

        #     # Query the serial number even if not needed to detect protocol errors.
        #     address = device.address

        #     if (not self._address) or (address == self._address):
        #         return device
        # except:
        #     await shield(device.close())
        #     raise

        return None

    async def start(self):
        async with Pool.open() as pool:
            logger.info("Starting RMGripper")
            await pool.wait_until_ready(self._connect())
            
            for node in self.nodes.values():
                await pool.wait_until_ready(node.start())
            
            logger.debug(f"RMGripper Started: Status is {self.connected} {self._device}")

            if not self.connected:
                logger.warning(f"Failed connecting to {self._label}")
            else:
                logger.info(f"Successfully Connected to {self._label}")

            yield


class RobotDeskMasterDevice(DeviceNode):
    owner = namespace

    def __init__(
        self,
        *,
        cnc_port: Optional[str],
        gripper_port: Optional[str],
        id: str,
        label: Optional[str],
        limits: str = "-150,150,-200,0,0,60"
    ):
        super().__init__()

        self.connected = False
        self.description = "Desktop Robot"
        self.id = id
        self.label = label

        # These will be added by the executor.
        self.cnc_port = cnc_port
        self.gripper_port = gripper_port

        self.nodes = {
            "CNC": GrblCNCDevice(port=cnc_port, id="cnc", label="CNC", limits=limits),
            "Gripper": RMGripperDevice(port=gripper_port, id="gripper", label="Gripper")
        }

    async def _connect(self, pool: Pool):
        ready = False
        
        logger.info("Connecting to RobotDesk")
        await pool.wait_until_ready(self.nodes["CNC"]._connect())
        await pool.wait_until_ready(self.nodes["Gripper"]._connect())
        self.connected = True

        ready = True
        yield

    async def _find_device(self):
        return None

    async def _create_device(self, /):
        return None

    async def start(self):
        async with Pool.open() as pool:
            logger.info("Starting RobotDesk")
            # await pool.wait_until_ready(self._connect(pool))
            # await pool.wait_until_ready(self.nodes["CNC"]._connect())
            # await pool.wait_until_ready(self.nodes["Gripper"]._connect())
            self.connected = True
            
            logger.debug("RobotDesk Starting nodes")
            
            for node in self.nodes.values():
                await pool.wait_until_ready(node.start())

            if not self.connected:
                logger.warning(f"Failed connecting to {self._label}")
            else:
                logger.info(f"Successfully Connected to {self._label}")

            yield