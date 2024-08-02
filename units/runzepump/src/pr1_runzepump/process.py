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
    flowrate: Quantity
    valve_position: str
    plunger_position: Quantity


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
            self._data.flowrate.value / (am.ureg.ul / am.ureg.s).value, 
            self._data.valve_position, 
            self._data.plunger_position.magnitude_as(am.ureg.ul)
        )

        yield am.ProcessTerminationEvent()
    
    async def __call__(self, context: am.ProcessContext[ProcessData, ProcessLocation, ProcessPoint]):
        data = context.data
        logger.info(f"Running with {data}")
        await self._executor.device_run_protocol(
            self._data.device, 
            self._data.flowrate.value / (am.ureg.ul / am.ureg.s).value, 
            self._data.valve_position, 
            self._data.plunger_position.magnitude_as(am.ureg.ul)
        )
    
    @staticmethod
    def export_data(data):
        return data.export()
