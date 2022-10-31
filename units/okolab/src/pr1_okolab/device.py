import asyncio
import traceback
from typing import Callable, Optional

from okolab import OkolabDevice, OkolabDeviceDisconnectedError, OkolabDeviceStatus
from pr1.devices.adapter import GeneralDeviceAdapter
from pr1.devices.node import DeviceNode, PolledNodeUnavailableError, PolledReadonlyNode, ReadonlyScalarNode

from . import logger, namespace


class BoardTemperatureNode(PolledReadonlyNode, ReadonlyScalarNode):
  id = "boardTemperature"
  label = "Board temperature"

  def __init__(self, *, master: 'MasterDevice'):
    PolledReadonlyNode.__init__(self, min_interval=1.0)
    ReadonlyScalarNode.__init__(self)

    self._master = master

  async def _read(self):
    try:
      return await self._master._adapter.device.get_board_temperature()
    except OkolabDeviceDisconnectedError as e:
      raise PolledNodeUnavailableError() from e


class TemperatureReadoutNode(PolledReadonlyNode, ReadonlyScalarNode):
  id = "readout"
  label = "Temperature readout"

  def __init__(self, *, index: int, master: 'MasterDevice'):
    PolledReadonlyNode.__init__(self, min_interval=1.0)
    ReadonlyScalarNode.__init__(self)

    self._index = index
    self._master = master

  async def _read(self):
    try:
      match self._index:
        case 1: return await self._master._adapter.device.get_temperature1()
    except OkolabDeviceDisconnectedError as e:
      raise PolledNodeUnavailableError() from e

# class TemperatureSetpointNode(ScalarNode):
#   id = "setpoint"
#   label = "Temperature setpoint"

#   def __init__(self, *, index: int, master: 'MasterDevice'):
#     self._index = index
#     self._master = master

#     self.target_value = None
#     self.value = None
#     self.value_range = (25.0, 60.0)

#   @property
#   def connected(self):
#     return self._master.connected

#   async def write(self, value: float, /):
#     self.target_value = value

#     if self._master.connected:
#       await self._write()

#   async def _configure(self):
#     self.value = await self._master.get_temperature_setpoint1()

#     if self.target_value is None:
#       self.target_value = self.value

#     if self.value != self.target_value:
#       await self._write()

#     self.value_range = await self._master.get_temperature_setpoint_range1()

#   async def _write(self):
#     assert self.target_value is not None

#     try:
#       match self._index:
#         case 1: await self._master.set_temperature_setpoint1(self.target_value)
#     except OkolabDeviceDisconnectedError:
#       pass
#     else:
#       self.value = self.target_value


class MasterDevice(DeviceNode):
  owner = namespace

  def __init__(
    self,
    *,
    id: str,
    label: Optional[str],
    serial_number: str,
    update_callback: Callable[[], None],
  ):
    super().__init__()

    self.id = id
    self.label = label
    self.model = "Generic Okolab device"

    self._adapter = GeneralDeviceAdapter(
      OkolabDevice,
      on_connection=self._on_connection,
      on_connection_fail=self._on_connection_fail,
      on_disconnection=self._on_disconnection,
      reconnect=True,
      serial_number=serial_number
    )

    self._node_board_temperature = BoardTemperatureNode(master=self)
    self._serial_number = serial_number
    self._workers: set['WorkerDevice'] = set()

    self.nodes = { node.id: node for node in {self._node_board_temperature, *self._workers} }

  async def _on_connection(self, *, reconnection: bool):
    logger.info(f"Connected to '{self._serial_number}'")
    self.model = await self._adapter.device.get_product_name()

    await self._node_board_temperature._configure()

    for worker in self._workers:
      await worker._configure()

    if len(self._workers) < 1:
      await self._adapter.device.set_device1(None)
    if len(self._workers) < 2:
      await self._adapter.device.set_device2(None)

  async def _on_connection_fail(self, reconnection: bool):
    if not reconnection:
      logger.warning(f"Failed connecting to '{self._serial_number}'")

  async def _on_disconnection(self, *, lost: bool):
    if lost:
      logger.warning(f"Lost connection to '{self._serial_number}'")

    await self._node_board_temperature._unconfigure()

    for worker in self._workers:
      await worker._unconfigure()

  @property
  def connected(self):
    return self._adapter.connected

  async def initialize(self):
    await self._adapter.start()

  async def destroy(self):
    await self._adapter.stop()


class WorkerDevice(DeviceNode):
  owner = namespace

  def __init__(
    self,
    *,
    id: str,
    index: int,
    label: Optional[str],
    master: MasterDevice,
    side: Optional[int],
    type: int
  ):
    super().__init__()

    self.id = id
    self.label = label
    self.model = f"Okolab device (type {type})"

    self._index = index
    self._master = master
    self._side = side
    self._type = type

    self._node_readout = TemperatureReadoutNode(index=index, master=master)
    # self._node_setpoint = TemperatureSetpointNode(index=index, master=master)
    self._status = None
    self._status_check_task = None

    # self.nodes = { node.id: node for node in {self._node_readout, self._node_setpoint} }
    self.nodes = { node.id: node for node in {self._node_readout} }

  async def _configure(self):
    match self._index:
      case 1: await self._master._adapter.device.set_device1(self._type, side=self._side)

    await self._node_readout._configure()
    # await self._node_setpoint._configure()

    async def status_check_loop():
      try:
        while True:
          self._status = await self._master._adapter.device.get_status1()
          await asyncio.sleep(1)
      except (asyncio.CancelledError, OkolabDeviceDisconnectedError):
        pass
      except Exception:
        traceback.print_exc()
      finally:
        self._status_check_task = None

    self._status_check_task = asyncio.create_task(status_check_loop())

  async def _unconfigure(self):
    if self._status_check_task:
      self._status_check_task.cancel()

    await self._node_readout._unconfigure()

  @property
  def connected(self):
    return self._status in {OkolabDeviceStatus.Alarm, OkolabDeviceStatus.Ok, OkolabDeviceStatus.Transient}
