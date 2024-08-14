import automancer as am

from . import namespace
from .executor import Executor
from .process import Process


class Parser(am.BaseParser):
    namespace = namespace

    def __init__(self, fiber):
        super().__init__(fiber)

        self.transformers = [am.ProcessTransformer(Process, {
            'Robot.motion': am.Attribute(
                description="Moving the DesktopRobot",
                type=am.RecordType({
                    'device': am.StrType(),
                    'x': am.Attribute(
                        am.QuantityType('micrometer', min=(-150 * am.ureg.mm), max=(150 * am.ureg.mm)),
                        default=(0.0 * am.ureg.mm),
                        description="The target position of X"
                    ),
                    'y': am.Attribute(
                        am.QuantityType('micrometer', min=(-200 * am.ureg.mm), max=(0 * am.ureg.mm)),
                        default=(0.0 * am.ureg.mm),
                        description="The target position of Y"
                    ),
                    'z': am.Attribute(
                        am.QuantityType('micrometer', min=(0 * am.ureg.mm), max=(60 * am.ureg.mm)),
                        default=(0.0 * am.ureg.mm),
                        description="The target position of Z"
                    ),
                    'gripper_distance': am.Attribute(
                        am.QuantityType('micrometer', min=(0 * am.ureg.mm), max=(30 * am.ureg.mm)),
                        default=(0.0 * am.ureg.mm),
                        description="The target position of Gripper"
                    ),
                })
            )
        }, parser=fiber)]
