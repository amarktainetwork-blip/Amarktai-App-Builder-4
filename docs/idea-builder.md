# Idea Builder

Idea Builder is an authenticated dashboard feature for refining rough product ideas into build-ready prompts.

## Dashboard

Open `Dashboard -> Idea Builder`.

The user can:

- choose a target build mode
- chat through audience, product goals, workflows, visual direction, and constraints
- generate a final build prompt
- send the result to New Build with premium quality selected

The chat is non-blocking in the UI and shows loading states while messages are being processed.

## API

All routes require the normal bearer token.

### Create Session

`POST /api/idea-builder/sessions`

```json
{
  "seed_prompt": "optional rough idea",
  "mode": "website"
}
```

### Send Message

`POST /api/idea-builder/sessions/{session_id}/messages`

```json
{
  "message": "The audience is agencies that need client apps shipped faster."
}
```

### Finalize Prompt

`POST /api/idea-builder/sessions/{session_id}/finalize`

```json
{
  "project_name": "Amarktai Builder",
  "mode": "website"
}
```

Returns `final_prompt`, which can be passed directly to `POST /api/projects`.

## Provider Behavior

If `GENX_API_KEY` is configured, Idea Builder uses the model for chat and final prompt generation. If the provider is unavailable, it falls back to deterministic guidance and prompt generation. The fallback is intentionally explicit and does not claim model-backed brainstorming happened.
