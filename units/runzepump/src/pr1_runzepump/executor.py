from typing import Any, Optional, Protocol

import automancer as am

from .device import RunzeSyringePumpDevice


class DeviceConf(Protocol):
    port: Optional[str]
    id: str
    label: Optional[str]
    address: Optional[str]
    volume: float

class Conf(Protocol):
    devices: list[DeviceConf]``

class Executor(am.BaseExecutor):
    options_type = am.RecordType({
        'devices': am.Attribute(am.ListType(am.RecordType({
            'port': am.Attribute(am.StrType(), default=None),
            'id': am.IdentifierType(),
            'label': am.Attribute(am.StrType(), default=None),
            'address': am.Attribute(am.StrType(), default=None),
            'volume': am.AnyType
        })), default=list())
    })

    def __init__(self, conf: Any, *, host):
        self._devices = dict[str, RunzeSyringePumpDevice]()
        self._host = host

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
