import automancer as am

from . import namespace
from .executor import Executor
from .process import Process


class Parser(am.BaseParser):
    namespace = namespace

    def __init__(self, fiber):
        super().__init__(fiber)

        executor: Executor = fiber.host.executors[namespace]
        valve_info = list(executor._valve_info.values())
        speed_grade = list(executor._speed_grade.values())

        assert valve_info is not None
        assert speed_grade is not None

        self.transformers = [am.ProcessTransformer(Process, {
            'Pump.motion': am.Attribute(
                description="Moving the pump",
                type=am.RecordType({
                    'device': am.StrType(),
                    'valve_position': am.EnumType(*valve_info),
                    'flowrate': am.Attribute(
                        am.QuantityType('microliter/second', min=(0 * am.ureg.ul / am.ureg.s)),
                        default=(0.0 * am.ureg.ul / am.ureg.s),
                        description="The flowrate"
                    ),
                    'plunger_position': am.Attribute(
                        am.QuantityType('microliter', min=(0 * am.ureg.ul)),
                        default=(0.0 * am.ureg.ul),
                        description="The target position the plunger should move to"
                    )
                })
            )
        }, parser=fiber)]
