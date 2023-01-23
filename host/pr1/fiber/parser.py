from collections import namedtuple
from dataclasses import KW_ONLY, dataclass, field
from pint import UnitRegistry
from types import EllipsisType
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional, Protocol, Sequence

from ..util.misc import Exportable
from . import langservice as lang
from .eval import EvalEnv, EvalEnvs, EvalStack
from .expr import PythonExpr, PythonExprAugmented
from .. import reader
from ..reader import LocatedValue, LocationArea
from ..draft import Draft, DraftDiagnostic, DraftGenericError
from ..ureg import ureg
from ..util import schema as sc
from ..util.decorators import debug

if TYPE_CHECKING:
  from .master2 import Master
  from ..host import Host


@debug
class MissingProcessError(Exception):
  def __init__(self, area: LocationArea):
    self.area = area

  def diagnostic(self):
    return DraftDiagnostic(f"Missing process", ranges=self.area.ranges)


class BlockUnitState:
  def __or__(self, other):
    return other

  def __and__(self, other):
    return self, other

  # def __rand__(self, other):
  #   ...

  def export(self) -> object:
    ...

class BlockState(dict[str, Optional[BlockUnitState]]):
  def __or__(self, other: 'BlockState'):
    return other.__ror__(self)

  def __ror__(self, other: Optional['BlockState']):
    if other is None:
      return self
    else:
      result = dict()

      for key, value in self.items():
        other_value = other[key]

        if value is None:
          result[key] = other_value
        elif other_value is None:
          result[key] = value
        else:
          result[key] = other_value | value

      return BlockState(result)

  def __and__(self, other: 'BlockState'):
    self_result = dict()
    other_result = dict()

    for namespace, value in self.items():
      other_value = other[namespace]

      if (value is not None) or (other_value is not None):
        self_result[namespace], other_result[namespace] = value & other_value # type: ignore
      else:
        self_result[namespace], other_result[namespace] = None, None

    return BlockState(self_result), BlockState(other_result)

  def export(self):
    return { namespace: state and state.export() for namespace, state in self.items() if state }


@debug
class BlockData:
  def __init__(
    self,
    *,
    state: BlockState,
    transforms: 'Transforms'
  ):
    self.state = state
    self.transforms = transforms

@debug
class BlockUnitData:
  def __init__(
    self,
    *,
    envs: Optional[list[EvalEnv]] = None,
    state: Optional[BlockUnitState] = None,
    transforms: Optional[list['BaseTransform']] = None
  ):
    self.envs = envs or list()
    self.state = state
    self.transforms = transforms or list()

@dataclass
class BlockUnitPreparationData:
  prep: Optional[Any] = None
  _: KW_ONLY
  envs: list[EvalEnv] = field(default_factory=list)

BlockPreparationData = dict[str, BlockUnitPreparationData]

class BlockProgram(Protocol):
  def __init__(self, block: 'BaseBlock', master: 'Master', parent: 'BlockProgram | Master'):
    self._parent: 'BlockProgram | Master'

  @property
  def busy(self):
    ...

  def import_message(self, message: Any):
    ...

  def halt(self):
    ...

  # def jump(self, point: Any):
  #   ...

  def pause(self):
    ...

  def call_resume(self):
    self._parent.call_resume()

  def run(self, child: Any, /, parent_state_program, stack: EvalStack, symbol) -> AsyncIterator[Any]:
    ...

class BaseProgramPoint(Protocol):
  @classmethod
  def import_value(cls, data: Any, /, block: 'BaseBlock', *, master) -> 'BaseProgramPoint':
    ...

class BaseBlock(Protocol):
  Point: type[BaseProgramPoint]
  Program: type[BlockProgram]

  def export(self):
    ...

# @deprecated
BlockAttrs = dict[str, dict[str, Any | EllipsisType]]

Attrs = dict[str, Any]
AttrsOptional = dict[str, Any | EllipsisType]

class BaseParser(Protocol):
  namespace: str
  priority: int = 0
  root_attributes = dict[str, lang.Attribute]()
  segment_attributes = dict[str, lang.Attribute]()

  def __init__(self, fiber: 'FiberParser'):
    pass

  def enter_protocol(self, attrs: Attrs, /, adoption_envs: EvalEnvs, runtime_envs: EvalEnvs):
    return lang.Analysis()

  def prepare_block(self, attrs: Attrs, /, adoption_envs: EvalEnvs, runtime_envs: EvalEnvs) -> tuple[lang.Analysis, BlockUnitPreparationData | EllipsisType]:
    return lang.Analysis(), BlockUnitPreparationData(attrs)

  def parse_block(self, attrs, /, adoption_stack: EvalStack) -> tuple[lang.Analysis, BlockUnitData | EllipsisType]:
    return lang.Analysis(), BlockUnitData()

class BaseTransform:
  def execute(self, state: BlockState, transforms: 'Transforms', *, origin_area: LocationArea) -> tuple[lang.Analysis, BaseBlock | EllipsisType]:
    ...

Transforms = list[BaseTransform]


# ----


@dataclass(kw_only=True)
class AnalysisContext:
  envs_list: list[EvalEnvs] = field(default_factory=list)
  eval_depth: int = 0
  symbolic: bool = False

  def update(self, **kwargs):
    return type(self)(**{ **self.__dict__, **kwargs })


class UnresolvedBlockData:
  def evaluate(self, stack: EvalStack) -> tuple[lang.Analysis, BlockData | EllipsisType]:
    ...

@debug
class UnresolvedBlockDataExpr(UnresolvedBlockData):
  def __init__(self, expr: PythonExprAugmented):
    self._expr = expr

  def evaluate(self, stack: EvalStack):
    from .opaque import ConsumedValueError

    analysis, value = self._expr.evaluate(stack)

    if value is Ellipsis:
      return analysis, Ellipsis

    try:
      return analysis, value.value.as_block()
    except ConsumedValueError:
      analysis.errors.append(DraftGenericError("Value already consumed", ranges=value.area.ranges))
      return analysis, Ellipsis

@debug
class UnresolvedBlockDataLiteral(UnresolvedBlockData):
  def __init__(self, attrs: Any, /, adoption_envs: EvalEnvs, runtime_envs: EvalEnvs, fiber: 'FiberParser'):
    self._attrs = attrs
    self._fiber = fiber
    self._adoption_envs = adoption_envs
    self._runtime_envs = runtime_envs

  def evaluate(self, stack: EvalStack):
    return lang.Analysis(), self._fiber.parse_block_attrs(self._attrs, adoption_envs=self._adoption_envs, adoption_stack=stack, runtime_envs=self._runtime_envs)


# ----


@dataclass(kw_only=True)
class FiberProtocol(Exportable):
  draft: Draft
  global_env: EvalEnv
  name: Optional[str]
  root: BaseBlock
  user_env: EvalEnv

  def export(self):
    return {
      "draft": self.draft.export(),
      "name": self.name,
      "root": self.root.export()
    }


class FiberParser:
  def __init__(self, draft: Draft, *, Parsers: Sequence[type[BaseParser]], host: 'Host'):
    self._parsers: list[BaseParser] = [Parser(self) for Parser in Parsers]

    self.draft = draft
    self.host = host
    self.user_env = EvalEnv()

    self.analysis_context = AnalysisContext() # @deprecated

    self.analysis, protocol = self._parse()
    self.protocol = protocol if not isinstance(protocol, EllipsisType) else None

  def _parse(self):
    analysis = lang.Analysis()

    data, reader_errors, reader_warnings = reader.loads(self.draft.entry_document.source)

    analysis.errors += reader_errors
    analysis.warnings += reader_warnings

    root_type = lang.DivisibleCompositeDictType({
      'name': lang.Attribute(
        label="Protocol name",
        description="The protocol's name.",
        type=lang.StrType()
      ),
      'steps': lang.Attribute(
        type=lang.AnyType(),
        required=True
      )
    })


    for parser in self._parsers:
      root_type.add(parser.root_attributes, namespace=parser.namespace)

    self.segment_type = lang.DivisibleCompositeDictType()

    for parser in self._parsers:
      self.segment_type.add(parser.segment_attributes, namespace=parser.namespace)

    context = AnalysisContext()
    root_result = analysis.add(root_type.analyze(data, context))

    if isinstance(root_result, EllipsisType):
      raise Exception()

    root_result_native = analysis.add(root_type.analyze_namespace(root_result, context, namespace=None))

    print("1", root_result_native)
    print()

    if isinstance(root_result_native, EllipsisType):
      return analysis, Ellipsis

    global_env = EvalEnv()
    adoption_envs = [global_env]
    adoption_stack: EvalStack = {
      global_env: {
        'unit': ureg
      }
    }

    root_block_prep = analysis.add(self.prepare_block(root_result_native['steps'], adoption_envs=adoption_envs, runtime_envs=[global_env]))

    print("2", root_block_prep)
    print()

    if isinstance(root_block_prep, EllipsisType):
      return analysis, Ellipsis

    if isinstance(root_block_prep, EllipsisType):
      raise Exception()

    root_block_data = analysis.add(self.parse_block(root_block_prep, adoption_stack))

    print("3", root_block_data)
    print()

    if isinstance(root_block_data, EllipsisType):
      return analysis, Ellipsis

    root_block = analysis.add(self.execute(root_block_data.state, root_block_data.transforms, origin_area=root_result_native['steps'].area))

    print("\x1b[1;31mAnalysis >\x1b[22;0m", analysis.errors)
    print(root_block)

    if isinstance(root_block, EllipsisType):
      return analysis, Ellipsis

    return analysis, FiberProtocol(
      draft=self.draft,
      global_env=global_env,
      name=root_result_native['name'],
      root=root_block,
      user_env=self.user_env
    )


  def prepare_block(self, attrs: Any, /, adoption_envs: EvalEnvs, runtime_envs: EvalEnvs):
    analysis = lang.Analysis()
    context = AnalysisContext(
      envs_list=[adoption_envs, runtime_envs],
      # eval_depth=2
    )

    block_result = analysis.add(self.segment_type.analyze(attrs, context))

    if isinstance(block_result, EllipsisType):
      return analysis, Ellipsis

    prep = Attrs()

    failure = False
    runtime_envs = runtime_envs.copy()

    for parser in self._parsers:
      unit_attrs = analysis.add(self.segment_type.analyze_namespace(block_result, context, namespace=parser.namespace))

      if isinstance(unit_attrs, EllipsisType):
        failure = True
        continue

      unit_data = analysis.add(parser.prepare_block(unit_attrs, adoption_envs, runtime_envs))

      if isinstance(unit_data, EllipsisType):
        # TODO: Problem here: what if this error will cause more errors due to missing runtime environments?
        # Add a flag on the analysis context to ignore these errors.
        failure = True
        continue

      prep[parser.namespace] = unit_data.prep
      runtime_envs += unit_data.envs

    return analysis, (prep if not failure else Ellipsis)

  def parse_block(self, preps: dict[str, Any], /, adoption_stack: EvalStack):
    analysis = lang.Analysis()
    state = BlockState()
    transforms = list[BaseTransform]()

    # for namespace, prep in preps.items():
    #   attrs[namespace] = { attr_name: analysis.add(attr_prep.evaluate(adoption_envs, adoption_stack, done=True)) for attr_name, attr_prep in prep.items() }

    failure = False

    for parser in self._parsers:
      prep = preps[parser.namespace]

      if prep is None:
        continue

      block_data = analysis.add(parser.parse_block(prep, adoption_stack))

      if isinstance(block_data, EllipsisType):
        failure = True
        continue

      state[parser.namespace] = block_data.state
      transforms += block_data.transforms

    return analysis, BlockData(state=state, transforms=transforms) if not failure else Ellipsis

  # def parse_block_expr(self, data_block: Any, /, adoption_envs: EvalEnvs, runtime_envs: EvalEnvs) -> UnresolvedBlockData | EllipsisType:
  #   from .opaque import OpaqueValue

  #   analysis, data_attrs = lang.LiteralOrExprType(self.segment_type, expr_type=lang.PrimitiveType(OpaqueValue), static=True).analyze(data_block, self.analysis_context)
  #   self.analysis += analysis

  #   if isinstance(data_attrs, EllipsisType):
  #     return Ellipsis

  #   if isinstance(data_attrs, LocatedValue) and isinstance(data_attrs.value, PythonExpr):
  #     return UnresolvedBlockDataExpr(data_attrs.value.augment(adoption_envs))

  #   return UnresolvedBlockDataLiteral(data_attrs, adoption_envs=adoption_envs, runtime_envs=runtime_envs, fiber=self)

  def execute(self, state: BlockState, transforms: Transforms, *, origin_area: LocationArea):
    if not transforms:
      return lang.Analysis(errors=[MissingProcessError(origin_area)]), Ellipsis

    return transforms[0].execute(state, transforms[1:], origin_area=origin_area)
