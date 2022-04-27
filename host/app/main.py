import asyncio
from pathlib import Path
import appdirs
import json
import logging
import websockets

from runner import Host


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pr1-app")


class DefaultBackend:
  def __init__(self):
    # self.data_dir = Path(appdirs.site_data_dir("PR-1", "Hsn"))
    self.data_dir = Path(appdirs.site_data_dir("PR-1", "Hsn"))
    self.data_dir.mkdir(exist_ok=True)

  def get_data_dir(self):
    return self.data_dir


class App():
  def __init__(self):
    self.host = Host(backend=DefaultBackend())
    self.clients = set()

    self.hostname = "127.0.0.1"
    self.port = 4567

  async def connect(self, client):
    await client.send(json.dumps(self.host.get_state()))
    # self.broadcast(json.dumps(self.state))

    async for msg in client:
      message = json.loads(msg)

      if message["type"] == "command":
        chip = self.host.chips[message["chipId"]]
        namespace, command = next(iter(message["command"].items()))
        chip.runners[namespace].command(command)

      if message["type"] == "createChip":
        self.host.create_chip(model_id=message["modelId"], name="Untitled chip")

      if message["type"] == "createDraft":
        self.host.create_draft(draft_id=message["draftId"], source=message["source"])

      if message["type"] == "deleteChip":
        # TODO: checks
        del self.host.chips[message["chipId"]]

      if message["type"] == "setMatrix":
        chip = self.host.chips[message["chipId"]]

        for namespace, matrix_data in message["update"].items():
          chip.matrices[namespace].update(matrix_data)

      if message["type"] == "startPlan":
        chip = self.host.chips[message["chipId"]]
        draft = self.host.drafts[message["draftId"]]

        def update_callback():
          self.update()

        self.host.start_plan(chip=chip, codes=message["codes"], draft=draft, update_callback=update_callback)

      self.update()
      # await client.send(json.dumps(self.get_state()))

    # import asyncio
    # await asyncio.Future()

  def broadcast(self, message):
    websockets.broadcast(self.clients, message)

  def update(self):
    self.broadcast(json.dumps(self.host.get_state()))

  def start(self):
    loop = asyncio.get_event_loop()

    self.host._debug()

    loop.run_until_complete(self.host.initialize())

    loop.create_task(self.serve())
    loop.run_forever()

  async def serve(self):
    async def handler(client):
      self.clients.add(client)

      try:
        await self.connect(client)
      finally:
        self.clients.remove(client)

    server = await websockets.serve(handler, host=self.hostname, port=self.port)
    await server.wait_closed()


app = App()
app.start()
