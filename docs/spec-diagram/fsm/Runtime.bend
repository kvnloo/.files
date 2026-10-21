import Base
import ./WorkItem.bend as WorkItem
import ./WorkerSupervision.bend as WorkerSupervision
import ./IntegrationOwner.bend as IntegrationOwner
import ./Ops.bend as Ops
import ./OpsLayer.bend as OpsLayer

# ABI identity for adapter.mjs. Every transition decision is WorkItem.step /
# WorkItem.astep / WorkerSupervision.step / lstep / pstep / peff / IntegrationOwner.step /
# Ops.nstep / Ops.neff / Ops.rstep / OpsLayer.gate_step (over Ops.bend's gates), unchanged.
def abi_version() -> U32:
  1
