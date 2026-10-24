# Higgs Realtime spike findings (A1: S1 + S2)

Run on 2026-10-23 with `backend/spikes/realtime_spike.py`. Raw event logs, WAVs and JSON reports are in `backend/spikes/out/` (gitignored, so re-run the script to regenerate them).

## Handshake (differs from OpenAI)
- **The server sends nothing until the client's first `session.update`.** It then replies with `session.created`, which echoes the *applied* config (voice, instructions, tools, turn detection). No `session.updated` arrives. **Treat `session.created` (or `session.updated`) as the ack.**
- The nested GA shape works: `session.audio.input.{format, turn_detection, transcription}` and `session.audio.output.{format, voice}`, plus `session.type: "realtime"` and `output_modalities: ["audio"]`.
- The `server_vad` defaults the server reports are `threshold 0.85`, `silence_duration_ms 500`, `prefix_padding_ms 300`, `create_response: true` and `interrupt_response: true`. The default temperature is 0.3.

## Voices (S1)
- All of `default, marcus, jake, oliver, chloe, eleanor, nora` were accepted, echoed back in `session.created`, and produced audio.
- `GET /v1/audio/voices` returns `{"data": []}`, so there are no extra presets on this account.
- **Kevin (cfo): `default` for now.** That's shared with Ryan, so a teammate clone is the fix if both appear in the demo. A listening pass may still change this (the files are in `spikes/out/<voice>.wav`).

## Injection (S2): **`INJECTION_MODE=user_message`**
| Variant | Result |
|---|---|
| per-response `instructions` (replace) | The reply **ignores the injected content** ("Hello! How can I assist you today?"), in both modes |
| per-response `instructions` = persona + guidance | Vague ("that report is ready"); still ignores the content |
| no per-response instructions | Relays the result accurately, in both modes |
| no per-response instructions, **guidance embedded in the payload** | Both modes work. `user_message` follows the guidance best ("Dwight just pinged… Want me to keep going or should I have you call him?") |

**Rule for the gateway:** never put `instructions` on an injection `response.create`. Embed the own-task or cross-team guidance in the injected content instead: a `how_to_mention_it` field in the `function_call_output` JSON, or appended to the `[notification from system, not the user]` text. Synthetic `function_call` items are accepted (no error), so `function_call` mode remains a working fallback.

## Interruption
- `input_audio_buffer.speech_started` and `speech_stopped` arrive as expected, and the user's speech is transcribed (`conversation.item.input_audio_transcription.completed`).
- **Audio is generated much faster than real time.** The injected response hit `response.done` (status `completed`) before the user's speech even began, while the browser would still have seconds of audio to play. So there was nothing to cancel server-side. Consequences:
  - `barge_in` must stop **client-side** playback. This is already in the §7a contract.
  - The injection gate cannot rely on `response.done` alone. `TurnState` also tracks the **estimated playback end**: the time of the first audio delta plus the received bytes ÷ 48 000 bytes/s. The 1.5 s quiet window counts from the later of that, `response.done` and `speech_stopped`.

## Events observed
`session.created`, `conversation.item.added`, `response.created`, `response.output_item.added/done`, `response.content_part.added/done`, `response.output_audio.delta/done`, `response.output_audio_transcript.delta/done`, `response.output_audio_transcript.length` (undocumented; ignore it), `response.function_call_arguments.delta/done`, `response.done`, `input_audio_buffer.speech_started/stopped`, `conversation.item.input_audio_transcription.completed`.

- Function calls appear in `response.done.response.output[]` as `{type: "function_call", call_id, name, arguments, status, executor: "client"}`. **The `executor` field is present.**
- No `error` events were seen, and no idle timeout was hit in these short runs.
- The model said "Task DM-900 is started" without the persona rule, which confirms the "never read out IDs" instruction is needed.

## Found later, during A7 (live calls through the gateway)
- **Per-response `instructions` on the greeting also break tool use for the rest of the call.** With them, `delegate_task` fired in about 1 of 3 runs; without them, 3 of 3. The greeting line now lives in a "Call start" section of the session instructions, and the first `response.create` is bare. **Rule: never send `instructions` on any `response.create`.**
- The model will claim work is delegated without calling the tool if anything in the prompt suggests it already was (for example, raw call notes saying "Dwight's on it"). The briefing now says past-call notes don't count as delegation, and the tool rules spell out that short go-aheads ("do it") mean "call delegate_task now".
- The model still sometimes answers from imagination instead of calling a tool (for example, inventing a deal). This is rare; plan for retakes when recording.
