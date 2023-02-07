import asyncio
import bisect
import copy
from asyncio import Event, Task
from enum import IntEnum
import time
from dataclasses import KW_ONLY, dataclass, field
import traceback
from types import EllipsisType
from typing import Any, Callable, Optional

from pr1.devices.claim import Claim
from pr1.devices.node import AsyncCancelable, BaseWatchableNode, BaseWritableNode, NodePath
from pr1.error import Error
from pr1.fiber.eval import EvalStack
from pr1.fiber.expr import PythonExprAugmented, export_value
from pr1.fiber.master2 import ProgramHandle
from pr1.fiber.parser import BlockUnitState
from pr1.fiber.process import ProgramExecEvent
from pr1.host import Host
from pr1.state import StateEvent, StateInstanceNotifyCallback, StateProgramItem, UnitStateManager
from pr1.units.base import BaseProcessRunner, BaseRunner
from pr1.util.asyncio import run_anonymous
from pr1.util.misc import race

from . import logger, namespace
from .parser import DevicesState


class NodeDisconnectedError(Error):
  def __init__(self, path: NodePath):
    super().__init__(
      f"Disconnected node '{'.'.join(path)}'"
    )

class NodeUnclaimableError(Error):
  def __init__(self, path: NodePath):
    super().__init__(
      f"Unclaimable node '{'.'.join(path)}'"
    )


@dataclass
class NodeStateLocation:
  value: Any
  _: KW_ONLY
  error_disconnected: bool = False
  error_evaluation: bool = False
  error_unclaimable: bool = False

  def export(self):
    return {
      "errors": {
        "disconnected": self.error_disconnected,
        "evaluation": self.error_evaluation,
        "unclaimable": self.error_unclaimable
      },
      "value": export_value(self.value)
    }

@dataclass
class DevicesStateItemLocation:
  values: dict[NodePath, NodeStateLocation] = field(default_factory=dict)

  def export(self):
    return {
      "values": [
        [path, node_location.export()] for path, node_location in self.values.items()
      ]
    }

  # claim: Optional[PerpetualClaim]
  # label: str
  # node: BaseWritableNode
  # path: NodePath
  # task: Optional[Task[None]]
  # value: Any
  # written: bool

@dataclass
class DevicesStateItemInfo:
  item: StateProgramItem
  location: DevicesStateItemLocation = field(default_factory=DevicesStateItemLocation, init=False)
  nodes: set[BaseWritableNode] = field(default_factory=set, init=False)
  notify: Callable[[StateEvent], None] = field(kw_only=True)

  def __hash__(self):
    return id(self)

  def do_notify(self, manager: 'DevicesStateManager'):
    self.notify(StateEvent(self.location, settled=self.is_settled(manager)))

  def is_settled(self, manager: 'DevicesStateManager'):
    return all(node_info.settled for node in self.nodes if (node_info := manager._node_infos[node]).current_candidate and (node_info.current_candidate.item_info is self)) # type: ignore

@dataclass
class DevicesStateNodeCandidate:
  item_info: DevicesStateItemInfo
  value: Any

@dataclass(kw_only=True)
class DevicesStateNodeInfo:
  candidates: list[DevicesStateNodeCandidate] = field(default_factory=list)
  claim: Optional[Claim] = None
  current_candidate: Optional[DevicesStateNodeCandidate] = None
  path: NodePath
  settled: bool = False
  task: Optional[Task] = None
  update_event: Optional[Event] = None

class DevicesStateManager(UnitStateManager):
  def __init__(self, runner: 'DevicesRunner'):
    self._item_infos = dict[StateProgramItem, DevicesStateItemInfo]()
    self._node_infos = dict[BaseWritableNode, DevicesStateNodeInfo]()
    self._runner = runner
    self._updated_nodes = set[BaseWritableNode]()

  async def _node_lifecycle(self, node: BaseWritableNode, node_info: DevicesStateNodeInfo):
    assert node_info.claim
    assert node_info.update_event

    def listener():
      pass

    reg = node.watch(listener) if isinstance(node, BaseWatchableNode) else None

    try:
      while True:
        await node_info.claim.wait()
        # info.current_candidate.item_info.notify(NodeStateLocation(info.current_candidate.value))

        while True:
          if node_info.current_candidate:
            await node.write(node_info.current_candidate.value)

            node_info.settled = True
            node_info.current_candidate.item_info.do_notify(self)

          race_index, _ = await race(node_info.claim.lost(), node_info.update_event.wait())

          if race_index == 0:
            # The claim was lost.
            # node_info.current_candidate.item_info.notify(NodeStateLocation(node_info.current_candidate.value, error_unclaimable=True))
            break
          else:
            # The node was updated.
            node_info.update_event.clear()
    except asyncio.CancelledError:
      pass
    finally:
      if reg:
        reg.cancel()

      node_info.claim.destroy()

  def add(self, item, state: DevicesState, *, notify, stack):
    item_info = DevicesStateItemInfo(item, notify=notify)
    self._item_infos[item] = item_info

    for node_path, node_value in state.values.items():
      node = self._runner._host.root_node.find(node_path)
      assert isinstance(node, BaseWritableNode)
      item_info.nodes.add(node)

      analysis, value = node_value.evaluate(stack)

      if isinstance(value, EllipsisType):
        raise Exception

      # TODO: Handle errors
      # print(node, analysis, value)

      if node in self._node_infos:
        node_info = self._node_infos[node]
      else:
        node_info = DevicesStateNodeInfo(path=node_path)
        self._node_infos[node] = node_info

      item_info.location.values[node_info.path] = NodeStateLocation(value)
      bisect.insort_left(node_info.candidates, DevicesStateNodeCandidate(item_info, value), key=(lambda candidate: candidate.item_info.item))

    self._updated_nodes |= item_info.nodes

  async def remove(self, item):
    nodes = self._item_infos[item].nodes

    for node in nodes:
      node_info = self._node_infos[node]
      node_info.candidates = [candidate for candidate in node_info.candidates if candidate.item_info.item is not item]

      if node_info.current_candidate and (node_info.current_candidate.item_info.item is item):
        node_info.current_candidate = None

    self._updated_nodes |= self._item_infos[item].nodes
    del self._item_infos[item]

  def apply(self, item, items):
    events = dict[StateProgramItem, StateEvent]()

    print()
    print()
    print("Apply")

    relevant_items = { ancestor_item for ancestor_item in item.ancestors() if not ancestor_item.applied }

    for node in self._updated_nodes:
      node_info = self._node_infos[node]
      new_candidate = next((candidate for candidate in node_info.candidates[::-1] if (candidate_item := candidate.item_info.item).applied or (candidate_item in relevant_items)), None)

      # print("Check", [(c.value, (candidate_item := c.item_info.item).applied or (candidate_item in relevant_items)) for c in node_info.candidates])
      # print(">", new_candidate)
      # print()
      # print(">", node_info.current_candidate)

      if new_candidate:
        print("Write", node, new_candidate.value)

      if node_info.current_candidate is not new_candidate:
        if node_info.current_candidate:
          current_item_info = node_info.current_candidate.item_info
          current_node_location = current_item_info.location.values[node_info.path]

          current_node_location.error_disconnected = False
          current_node_location.error_evaluation = False
          current_node_location.error_unclaimable = False
          current_item_info.do_notify(self)

        node_info.current_candidate = new_candidate

      if not node_info.claim:
        node_info.claim = node.claim()

      if not node_info.task:
        node_info.task = run_anonymous(self._node_lifecycle(node, node_info))
        node_info.update_event = Event()

    print()
    print()

    self._updated_nodes.clear()

    for relevant_item in relevant_items:
      relevant_item_info = self._item_infos[relevant_item]

      # for node in relevant_item_info.nodes:
      #   node_info = self._node_infos[node]

      events[relevant_item] = StateEvent(relevant_item_info.location, settled=all(node_info.settled for node_info in self._node_infos.values() if node_info.current_candidate and (node_info.current_candidate.item_info.item is relevant_item)))

      # node_info.update_event = Event()

      # node = self._runner._host.root_node.find(('Okolab', 'temperature'))
      # assert isinstance(node, BaseWritableNode)

      # events[ancestor] = StateEvent(DevicesStateItemLocation({
      #   ('Okolab', 'temperature'): NodeStateLocation(error_disconnected=True, value={ "type": "ellipsis" })
      # }), settled=True)

    return events

  async def suspend(self, item):
    return StateEvent(DevicesStateItemLocation({}))


class DevicesRunner(BaseRunner):
  StateConsumer = DevicesStateManager

  def __init__(self, chip, *, host: Host):
    self._chip = chip
    self._host = host
