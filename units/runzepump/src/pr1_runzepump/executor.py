from typing import Any, Optional, Protocol

import automancer as am

from .device import RunzeSyringePumpDevice, valve_info, speed_grade
from . import logger, namespace


class DeviceConf(Protocol):
    port: Optional[str]
    id: str
    label: Optional[str]
    address: Optional[str]
    volume: float

class Conf(Protocol):
    devices: list[DeviceConf]

class Executor(am.BaseExecutor):
    options_type = am.RecordType({
        'devices': am.Attribute(am.ListType(am.RecordType({
            'port': am.Attribute(am.StrType(), default=None),
            'id': am.IdentifierType(),
            'label': am.Attribute(am.StrType(), default=None),
            'address': am.Attribute(am.StrType(), default=None),
            'volume': am.Attribute(am.IntType(mode='positive'), default=25000)
        })), default=list())
    })

    def __init__(self, conf: Any, *, host):
        self._devices = dict[str, RunzeSyringePumpDevice]()
        self._host = host
        self._valve_info = valve_info
        self._valve_info_inv = {value: key for key, value in valve_info.items()}
        self._speed_grade = speed_grade

        executor_conf: Conf = conf.dislocate()

        for device_conf in executor_conf.devices:
            if device_conf.id in self._host.devices:
                raise Exception(f"Duplicate device id '{device_conf.id}'")

            device = RunzeSyringePumpDevice(
                port=device_conf.port,
                id=device_conf.id,
                label=device_conf.label,
                address=device_conf.address,
                volume=device_conf.volume
            )

            self._devices[device.id] = device
            self._host.devices[device.id] = device

    async def start(self):
        async with am.Pool.open() as pool:
            await am.try_all([
                pool.wait_until_ready(device.start()) for device in self._devices.values()
            ])

            yield

    async def device_run_protocol(self, device_id: str, speed: float, 
                                  valve_position: str, plunger_position: float):
        if device_id in self._devices:
            device = self._devices[device_id]._device
        else:
            device = list(self._devices.values())[0]._device
        logger.info(f"RunzePump: Running protocol on device {device}: {device.port}, {device.address}, {device.volume}, {device.mode}")
        
        # if speed_grade is not None:
        #     await device.set_speed_max(speed)
        await device.set_speed_grade("15")
        
        if valve_position is not None:
            await device.set_valve_position(self._valve_info_inv[valve_position])
        
        await device.move_plunger_to(plunger_position)