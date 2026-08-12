# Bright non-live identity

The pinned live-classroom profile intentionally does not load SOUL or any
context file. Its complete server-owned policy lives in `config.yaml` under
`gateway.api_server.bright_live.system_prompt`.

This file is reserved for a future, separately hosted planner profile. Never
point the single-slot live teacher process at that planner profile.
