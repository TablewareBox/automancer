from importlib.resources import files
from pathlib import Path

from pr1.units.base import Metadata, MetadataIcon, logger as parent_logger
from pr1.util.blob import Blob


namespace = "runzepump"
version = 0

logo = Blob(
  data=(Path(__file__).parent / "data/logo.png").open("rb").read(),
  type="image/png"
)

metadata = Metadata(
  description="Runze Fluid",
  icon=MetadataIcon(kind='bitmap', value=logo.to_url()),
  title="润泽流体",
  version="6.0"
)

client_path = files(__name__ + '.client')
logger = parent_logger.getChild(namespace)

from .executor import Executor
