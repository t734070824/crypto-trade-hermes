# Hermes profile visibility settings

Session-derived notes for reviewing a Hermes profile `config.yaml` against a user's request to see real-time activity and context usage in Telegram/gateway sessions.

## Config keys

Use the authoritative Hermes docs first, then verify the actual profile config.

Recommended gateway visibility settings:

```yaml
display:
  tool_progress: verbose        # off | new | all | verbose
  tool_progress_command: true   # allows /verbose in messaging gateway
  interim_assistant_messages: true
  runtime_footer:
    enabled: true
    fields:
      - model
      - context_pct
      - cwd
```

Effects:
- `tool_progress: verbose` shows tool/action progress while the agent works.
- `tool_progress_command: true` lets the user change verbosity with `/verbose` from messaging platforms.
- `interim_assistant_messages: true` allows natural mid-turn updates.
- `runtime_footer.enabled: true` appends runtime metadata to final gateway replies.
- `context_pct` is the key footer field for showing current context-window usage.

## Related preference checks

For users who require explicit timezone labeling, consider setting:

```yaml
timezone: Asia/Shanghai
```

Still label time values in responses as UTC or 北京时间（UTC+8）; config timezone does not replace explicit labeling.

For Chinese messaging UI prompts:

```yaml
display:
  language: zh
```

## Verification

After editing config:

```bash
hermes config check
python3 - <<'PY'
import yaml
p='config.yaml'
data=yaml.safe_load(open(p))
print(data.get('display',{}).get('tool_progress'))
print(data.get('display',{}).get('runtime_footer'))
print(data.get('timezone'))
PY
```

Gateway/display config generally requires `/restart` or `hermes gateway restart` to affect the running Telegram gateway.

## Git-policy note

In this profile repository, `config.yaml` is intentionally ignored. When changing it, do not claim it was pushed. Report that the config change is local and that only tracked allowlisted artifacts are pushed.