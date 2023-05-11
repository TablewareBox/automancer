from dataclasses import dataclass
from types import EllipsisType
from typing import Literal, TypedDict

from pr1.fiber.eval import EvalContext, EvalEnv, EvalEnvValue
from pr1.fiber.expr import Evaluable
from pr1.fiber.langservice import (Analysis, Attribute, IntType,
                                   PotentialExprType)
from pr1.fiber.parser import (BaseBlock, BaseParser, BasePassiveTransformer,
                              PassiveTransformerPreparationResult,
                              TransformerAdoptionResult)
from pr1.reader import LocatedValue

from . import namespace


class Attributes(TypedDict, total=False):
  repeat: Evaluable[LocatedValue[int]]

class Transformer(BasePassiveTransformer):
  priority = 400
  attributes = {
    'repeat': Attribute(
      description="Repeats a block a fixed number of times.",
      type=PotentialExprType(IntType(mode='positive_or_null'))
    )
  }

  def __init__(self):
    self.env = EvalEnv({
      'index': EvalEnvValue()
    }, name="Repeat", readonly=True)

  def prepare(self, data: Attributes, /, adoption_envs, runtime_envs):
    if (attr := data.get('repeat')):
      return Analysis(), PassiveTransformerPreparationResult(attr, runtime_envs=[self.env])
    else:
      return Analysis(), None

  def adopt(self, data: Evaluable[LocatedValue[int | Literal['forever']]], /, adoption_stack, trace):
    analysis, count = data.eval(EvalContext(adoption_stack), final=False)

    if isinstance(count, EllipsisType):
      return analysis, Ellipsis

    return analysis, TransformerAdoptionResult(count)

  def execute(self, data: Evaluable[LocatedValue[int | Literal['forever']]], /, block):
    return Analysis(), Block(block, count=data, env=self.env)

class Parser(BaseParser):
  namespace = namespace
  transformers = [Transformer()]


@dataclass
class Block(BaseBlock):
  block: BaseBlock
  count: Evaluable[LocatedValue[int | Literal['forever']]]
  env: EvalEnv

  def __get_node_children__(self):
    return [self.block]

  def __get_node_name__(self):
    return ["Repeat"]

  def create_program(self, handle):
    from .program import Program
    return Program(self, handle)

  def import_point(self, data, /):
    from .program import ProgramPoint
    return ProgramPoint(
      child=self.block.import_point(data["child"]),
      iteration=data["iteration"]
    )

  def export(self):
    return {
      "name": "_",
      "namespace": namespace,
      "count": self.count.export(),
      "child": self.block.export()
    }
