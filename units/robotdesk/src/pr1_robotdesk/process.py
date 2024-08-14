from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast, final

import automancer as am
from quantops import Quantity
from pr1.fiber.expr import export_value

from . import logger, namespace
from .executor import Executor
# from .process import Runner


class ProcessData(Protocol):
    device: str
    x: Quantity
    y: Quantity
    z: Quantity
    gripper_distance: Quantity


@dataclass
class ProcessPoint(am.BaseProcessPoint):
    pass

@dataclass
class ProcessLocation(am.Exportable):
    def export(self):
        return {}

@final
@am.provide_logger(logger)
class Process(am.BaseProcess[ProcessData, ProcessPoint]):
    name = "_"
    namespace = namespace

    def __init__(self, data: ProcessData, /, master):
        logger.info(f"RunzePump: Initializing process with data: {data}")
        self._data = data
        self._executor: Executor = master.host.executors[namespace]
        logger.info(f"RunzePump: Executor: {self._executor}")
        
        # self._runner = cast(Runner, master.runners[namespace])

    async def run(self, point, stack):
        logger.info("RunzePump: Running process")
        yield am.ProcessExecEvent(
            location=ProcessLocation()
        )

        await self._executor.device_run_protocol(
            self._data.device, 
            self._data.x.magnitude_as(am.ureg.mm),
            self._data.y.magnitude_as(am.ureg.mm),
            self._data.z.magnitude_as(am.ureg.mm),
            self._data.gripper_distance.magnitude_as(am.ureg.mm),
        )

        yield am.ProcessTerminationEvent()
    
    async def __call__(self, context: am.ProcessContext[ProcessData, ProcessLocation, ProcessPoint]):
        data = context.data
        logger.info(f"Running with {data}")
        await self._executor.device_run_protocol(
            self._data.device, 
            self._data.x.magnitude_as(am.ureg.mm),
            self._data.y.magnitude_as(am.ureg.mm),
            self._data.z.magnitude_as(am.ureg.mm),
            self._data.gripper_distance.magnitude_as(am.ureg.mm),
        )
    
    @staticmethod
    def export_data(data):
        return data.export()
