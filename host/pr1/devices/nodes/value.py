from abc import ABC, abstractmethod
from asyncio import Lock
from typing import Generic, NewType, Optional, TypeVar, final

from .common import BaseNode, ConfigurableNode, NodeUnavailableError
from ..claim import Claimable


@final
class NullType:
  pass

Null = NullType()


T = TypeVar('T')

NodeRevision = NewType('NodeRevision', int)

class ValueNode(ConfigurableNode, BaseNode, ABC, Generic[T]):
  def __init__(self, *, nullable: bool = False, readable: bool = False, writable: bool = False):
    super().__init__()

    self._lock = Lock()
    self._revision = NodeRevision(0)
    self._target_value: T | NullType = Null

    self.nullable = nullable
    self.readable = readable
    self.writable = writable

    if self.writable:
      self._claimable = Claimable()

  # To be implemented

  async def _read(self) -> bool:
    """
    Updates the node's value.

    There will never be two concurrent calls to this method nor any call when the node is disconnected. The node may however be disconnected during the call, in which it might be cancelled; if not, this method should raise a `NodeUnavailableError` upon reaching a disconnection error.

    Returns
      `True` if the node's value has changed, `False` otherwise.

    Raises
      asyncio.CancelledError
      NodeUnavailableError: If the node is unavailable, for instance if it disconnects while its value is being fetched.
      NotImplementedError: If the node is not readable.
    """

    raise NotImplementedError


  def _target_reached(self) -> bool:
    raise NotImplementedError

  async def _write(self, value: T | NullType, /):
    """
    Writes the node's value.

    Raises
      asyncio.CancelledError
      NodeUnavailableError
      NotImplementedError: If the node is not writable.
    """

    raise NotImplementedError

  # Called by the producer

  async def _configure(self):
    try:
      await self._read()
    except NotImplementedError:
      pass

    if not self._target_reached():
      await self.write(self._target_value)

  # Called by the consumer

  def claim(self):
    if not self.writable:
      raise NotImplementedError

    return self._claimable.claim()

  async def read(self):
    """
    Updates the node's value.

    Returns
      A boolean indicating whether the node's value could be updated.

    Raises
      asyncio.CancelledError
      NotImplementedError
    """

    if not self.readable:
      raise NotImplementedError

    async with self._lock:
      if self.connected:
        try:
          changed = await self._read()
        except NodeUnavailableError:
          pass
        else:
          if changed:
            self._revision = NodeRevision(self._revision + 1)

          return True

    return False

  async def write(self, value: T | NullType, /):
    self._target_value = value

    if value is not None:
      async with self._lock:
        if self.connected:
          try:
            await self._write(value)
          except NodeUnavailableError:
            pass