# Common DUT Scripts

Put reusable DUT-side helper scripts here when:
- a plain command is not enough
- the logic should work across multiple platforms or cases
- we want the agent to execute only repo-defined scripts

Rules:
- keep scripts focused and explainable
- prefer read-only collection or non-destructive validation
- do not write to the OS disk
- emit structured stdout when possible so the agent can reuse the result

Current scripts:
- `collect_tracking_relevant_inventory.py`
  Collects CPU, memory, storage, and GPU inventory in structured JSON.

- `collect_pcie_device_inventory.py`
  Collects PCIe-facing GPU, NIC, and storage-controller inventory with readable summaries.

- `collect_operational_attention.py`
  Collects simple operational attention signals such as failed services, kernel-error samples, and BMC SEL presence.
