from collections import namedtuple
from pathlib import Path
import asyncio
import logging
import platform
import sys
import time
import uuid

from . import reader, units
from .chip import Chip
from .master import Master
from .model import Model
from .protocol import Protocol
from .util import schema as sc


Draft = namedtuple("Draft", ['id', 'errors', 'protocol', 'source'])
DraftError = namedtuple("DraftError", ['message', 'range'])

logger = logging.getLogger("pr1-host")

class Host:
  def __init__(self, backend):
    self.backend = backend
    self.data_dir = backend.get_data_dir()

    self.chips = dict()
    self.drafts = dict()

    # os.chmod(self.data_dir, 0o775)


    # -- Load configuration -------------------------------

    conf_schema = sc.Schema({
      'id': str,
      'name': str,
      'units': sc.Noneable(dict),
      'version': sc.ParseType(int)
    })

    conf_path = self.data_dir / "setup.yml"

    if conf_path.exists():
      try:
        conf = reader.loads((self.data_dir / "setup.yml").open().read())
        conf = conf_schema.transform(conf)
      except reader.LocatedError as e:
        e.display()
        sys.exit(1)
    else:
      conf = {
        'id': hex(uuid.getnode())[2:],
        'name': platform.node(),
        'units': dict(),
        'version': 1
      }

      conf_path.open("w").write(reader.dumps(conf))

    self.id = conf['id']
    self.name = conf['name']
    self.start_time = round(time.time() * 1000)
    self.units = units.units


    # -- Load units ---------------------------------------

    logger.info(f"Registering {len(self.units)} units: {', '.join(self.units.keys())}")

    conf_units = conf['units'] or dict()

    self.executors = {
      namespace: unit.Executor(conf_units.get(namespace, dict())) for namespace, unit in self.units.items() if hasattr(unit, 'Executor')
    }


    # -- Load models --------------------------------------

    logger.debug(f"Loading models")

    self.models = dict()

    for path in (self.data_dir / "models").glob("**/*.yml"):
      try:
        chip_model = Model.load(path, self.units)
        self.models[chip_model.id] = chip_model
      except reader.LocatedError as e:
        e.display()
        sys.exit(1)

  async def initialize(self):
    logger.info("Initializing host")
    logger.debug("Initializing executors")

    for executor in self.executors.values():
      await executor.initialize()

    logger.debug("Done initializing executors")

  async def destroy(self):
    logger.info("Destroying host")
    logger.debug("Destroying executors")

    for executor in self.executors.values():
      await executor.destroy()

    logger.debug("Done destroying executors")


  def _debug(self):
    # -- Debug --------------------------------------------

    chip = self.create_chip(model_id=list(self.models.keys())[0], name="Default chip")
    # _chip = self.create_chip(model_id=list(self.models.keys())[1], name="Other chip")
    draft = self.create_draft(str(uuid.uuid4()), (Path(__file__).parent.parent.parent / "test.yml").open().read())

    codes = {
      'control': {
        'arguments': [None, 0, None, 1]
      }
    }

    return chip, codes, draft

    # self.start_plan(chip, codes, draft, update_callback=update_callback)

    # try:
    #   protocol = Protocol(
    #     (Path(__file__).parent.parent / "test.yml").open().read(),
    #     parsers={ namespace: unit.Parser for namespace, unit in self.units.items() },
    #     models=self.models
    #   )

    #   pprint(protocol.export())
    # except reader.LocatedError as e:
    #   e.display()
    #   # raise e


  def create_chip(self, model_id, name):
    model = self.models[model_id]
    matrices = { namespace: unit.Matrix.load(model.sheets[namespace]) for namespace, unit in self.units.items() if hasattr(unit, 'Matrix') }
    chip = Chip(id=str(uuid.uuid4()), master=None, matrices=matrices, model=model, name=name, runners=dict())

    for namespace, executor in self.executors.items():
      chip.runners[namespace] = executor.create_runner(chip)

    self.chips[chip.id] = chip
    return chip

  def create_draft(self, draft_id, source):
    errors = list()
    protocol = None

    try:
      protocol = Protocol(
        source,
        parsers={ namespace: unit.Parser for namespace, unit in self.units.items() },
        models=self.models
      )
    except reader.LocatedError as e:
      errors.append(DraftError(message=e.args[0], range=(e.location.start, e.location.end)))

    draft = Draft(
      id=draft_id,
      errors=errors,
      protocol=protocol,
      source=source
    )

    self.drafts[draft_id] = draft
    return draft

  def start_plan(self, chip, codes, draft, *, update_callback):
    if chip.master:
      raise Exception("Already running")

    chip.master = Master(chip=chip, codes=codes, protocol=draft.protocol, update_callback=update_callback)
    chip.master.start()

    del self.drafts[draft.id]


    async def a():
      # await asyncio.sleep(1.5)
      # chip.master.pause()
      # await asyncio.sleep(1)
      await asyncio.sleep(5)
      chip.master.resume()

    loop = asyncio.get_event_loop()
    # loop.create_task(a())

    # import asyncio
    # asyncio.run(chip.master.wait())


  def get_state(self):
    return {
      "info": {
        "id": self.id,
        "name": self.name,
        "startTime": self.start_time
      },
      "chips": {
        chip.id: {
          "id": chip.id,
          "master": chip.master and chip.master.export(),
          "matrices": {
            namespace: matrix.export() for namespace, matrix in chip.matrices.items()
          },
          "modelId": chip.model.id,
          "name": chip.name,
          "runners": {
            namespace: runner.export() for namespace, runner in chip.runners.items()
          }
        } for chip in self.chips.values()
      },
      "models": {
        model.id: {
          "id": model.id,
          "name": model.name,
          "sheets": {
            namespace: sheet.export() for namespace, sheet in model.sheets.items()
          }
        } for model in self.models.values()
      },
      "devices": {
        device.id: device.export() for namespace, executor in self.executors.items() for device in executor.get_devices()
      },
      "drafts": {
        draft.id: {
          "id": draft.id,
          "errors": [{
            "message": error.message,
            "range": error.range
          } for error in draft.errors],
          "protocol": draft.protocol and draft.protocol.export(),
          "source": draft.source
        } for draft in self.drafts.values()
      },
      "executors": {
        namespace: executor.export() for namespace, executor in self.executors.items()
      }
    }

  def process_message(self, message, *, update_callback):
    if message["type"] == "command":
      chip = self.chips[message["chipId"]]
      namespace, command = next(iter(message["command"].items()))
      chip.runners[namespace].command(command)

    if message["type"] == "createChip":
      self.create_chip(model_id=message["modelId"], name="Untitled chip")

    if message["type"] == "createDraft":
      self.create_draft(draft_id=message["draftId"], source=message["source"])

    if message["type"] == "deleteChip":
      # TODO: checks
      del self.chips[message["chipId"]]

    if message["type"] == "pause":
      chip = self.chips[message["chipId"]]
      chip.master.pause({
        'neutral': message["options"]["neutral"]
      })

    if message["type"] == "resume":
      chip = self.chips[message["chipId"]]
      chip.master.resume()

    if message["type"] == "setMatrix":
      chip = self.chips[message["chipId"]]

      for namespace, matrix_data in message["update"].items():
        chip.matrices[namespace].update(matrix_data)

    if message["type"] == "skipSegment":
      chip = self.chips[message["chipId"]]
      chip.master.skip_segment(
        process_state=message["processState"],
        segment_index=message["segmentIndex"]
      )

    if message["type"] == "startPlan":
      chip = self.chips[message["chipId"]]
      draft = self.drafts[message["draftId"]]

      self.start_plan(chip=chip, codes=message["codes"], draft=draft, update_callback=update_callback)

    update_callback()