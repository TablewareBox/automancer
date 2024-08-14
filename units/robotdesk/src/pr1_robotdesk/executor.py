import asyncio
from typing import Any, Optional, Protocol

import automancer as am

from .device import RobotDeskMasterDevice, RMGripperDevice, GrblCNCDevice
from . import logger, namespace


class DeviceConf(Protocol):
    cnc_port: Optional[str]
    gripper_port: Optional[str]
    id: str
    label: Optional[str]
    limits: Optional[str] = "-150,150,-200,0,0,60"

class Conf(Protocol):
    devices: list[DeviceConf]

class Executor(am.BaseExecutor):
    options_type = am.RecordType({
        'devices': am.Attribute(am.ListType(am.RecordType({
            'cnc_port': am.Attribute(am.StrType(), default=None),
            'gripper_port': am.Attribute(am.StrType(), default=None),
            'id': am.IdentifierType(),
            'label': am.Attribute(am.StrType(), default=None),
            'limits': am.Attribute(am.StrType(), default=None)
        })), default=list())
    })

    def __init__(self, conf: Any, *, host):
        self._devices = dict[str, RobotDeskMasterDevice]()
        self._host = host

        executor_conf: Conf = conf.dislocate()

        for device_conf in executor_conf.devices:
            if device_conf.id in self._host.devices:
                raise Exception(f"Duplicate device id '{device_conf.id}'")

            device = RobotDeskMasterDevice(
                cnc_port=device_conf.cnc_port,
                gripper_port=device_conf.gripper_port,
                id=device_conf.id,
                label=device_conf.label,
                limits=device_conf.limits
            )

            self._devices[device.id] = device
            self._host.devices[device.id] = device

    async def start(self):
        async with am.Pool.open() as pool:
            await am.try_all([
                pool.wait_until_ready(device.start()) for device in self._devices.values()
            ])

            yield

    async def device_run_protocol(self, device_id: str,
                                  x: float, y: float, z: float, gripper_distance: float):
        if device_id in self._devices:
            master = self._devices[device_id]
        else:
            master = list(self._devices.values())[0]
        
        cnc_device = master.nodes["CNC"]._device
        gripper_device = master.nodes["Gripper"]._device
        logger.info(f"RobotDesk CNC: Running protocol on device {cnc_device}: {cnc_device.port}")
        
        # if speed_grade is not None:
        #     await device.set_speed_max(speed)
        await cnc_device.move_to(x, y, z)
        
        logger.info(f"RobotDesk Gripper: Running protocol on device {gripper_device}: {gripper_device.device}, moving to {gripper_distance}")
        
        if gripper_distance == 0:
            gripper_device.go_home()
        else:
            gripper_device.move_absolute(gripper_distance, 10, 500, 500, 0.1)
        await asyncio.sleep(20)
        logger.info(f"RobotDesk Gripper: Done moving gripper")