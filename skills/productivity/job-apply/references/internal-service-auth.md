# HTTP integration credentials (compatibility reference)

Ordinary local applications use the canonical skill's session start. They require
neither HTTP authentication nor a running dashboard. See
[APPLICATION_RUNTIME](../../../../docs/jobbot-v1/APPLICATION_RUNTIME.md).

Explicit HTTP integrations still resolve the configured credential environment
name, then the exact private JSON file/key reference. Keep operator and worker
roles separate; never print, export or pass secret values in arguments. See
[HERMES_CONNECTION](../../../../docs/jobbot-v1/HERMES_CONNECTION.md) for the current
connection and historical evidence. This file is not an extra local startup gate.
