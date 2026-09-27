---
name: Python web artifact runner
description: How to keep a FastAPI/Jinja app compatible with the workspace artifact lifecycle.
---

When a Python web app is created through the web artifact scaffold, keep the artifact registration but point the package dev script and production runner at Uvicorn instead of the scaffold's frontend server.

**Why:** The artifact router and preview depend on the registered service, while the requested application stack may not be the scaffold's default JavaScript runtime.

**How to apply:** Keep the managed artifact workflow, use the workspace's Python environment for dependencies, and update production metadata through the validated artifact TOML replacement flow.