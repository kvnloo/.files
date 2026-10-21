import Base
import ./WorkItem.bend as WorkItem
import ./WorkerSupervision.bend as WorkerSupervision

# ABI identity for adapter.mjs. Every transition decision is WorkItem.step /
# WorkItem.astep / WorkerSupervision.step / lstep / pstep / peff, unchanged.
def abi_version() -> U32:
  1
