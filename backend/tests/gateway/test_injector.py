import json

from company.types import TaskResult
from gateway.injector import NOTIFICATION_PREFIX, NotificationQueue, TurnState, injection_events


def result(task_id="DM-200", from_role="engineer", requested_by="eng_lead", title="Fix bulk discount"):
    return TaskResult(task_id, title, from_role, requested_by, "Fixed it; tests pass.", [])


def quiet_state(t=0.0) -> TurnState:
    s = TurnState()
    s.on_upstream("response.created", t)
    s.on_upstream("response.done", t)
    return s


def test_ready_initially():
    assert TurnState().ready(0.0)


def test_not_ready_while_response_active():
    s = TurnState()
    s.on_upstream("response.created", 0)
    assert not s.ready(100)
    s.on_upstream("response.done", 1)
    assert s.ready(2.6)


def test_not_ready_while_user_speaking():
    s = TurnState()
    s.on_upstream("input_audio_buffer.speech_started", 0)
    assert not s.ready(100)


def test_ready_after_1_5s_quiet():
    s = TurnState()
    s.on_upstream("input_audio_buffer.speech_started", 9)
    s.on_upstream("input_audio_buffer.speech_stopped", 10)
    assert not s.ready(11.4)
    assert s.ready(11.6)


def test_waits_for_estimated_playback_end():
    # Boson generates audio faster than real time: response.done arrives long before playback ends.
    s = TurnState()
    s.on_upstream("response.created", 0)
    s.on_audio(48000 * 4, 0.1)  # 4 s of 24 kHz PCM16
    s.on_upstream("response.done", 0.5)
    assert not s.ready(3.0)
    assert not s.ready(5.5)
    assert s.ready(5.7)


def test_barge_in_resets_playback_estimate():
    s = TurnState()
    s.on_audio(48000 * 10, 0)
    s.on_upstream("input_audio_buffer.speech_started", 1)
    s.on_upstream("input_audio_buffer.speech_stopped", 2)
    assert s.ready(3.6)


def test_not_ready_twice_without_user_turn():
    s = quiet_state()
    assert s.ready(5)
    s.mark_injected(5)
    s.on_upstream("response.created", 5.1)
    s.on_upstream("response.done", 6)
    assert not s.ready(20)
    s.on_upstream("input_audio_buffer.speech_started", 21)
    s.on_upstream("input_audio_buffer.speech_stopped", 22)
    assert s.ready(23.6)


def test_queue_fifo_and_dedupe():
    q = NotificationQueue()
    q.push(result("A"))
    q.push(result("B"))
    q.push(result("A"))
    assert [r.task_id for r in q.pending()] == ["A", "B"]
    assert q.pop().task_id == "A"
    assert q.pop().task_id == "B"
    assert q.pop() is None


def test_requeue_front():
    q = NotificationQueue()
    q.push(result("A"))
    q.push(result("B"))
    a = q.pop()
    q.requeue_front(a)
    assert [r.task_id for r in q.pending()] == ["A", "B"]


def test_discard():
    q = NotificationQueue()
    q.push(result("A"))
    q.push(result("B"))
    q.discard({"A"})
    assert [r.task_id for r in q.pending()] == ["B"]


def test_function_call_mode_events_shape(roles):
    evs = injection_events(result(), roles["eng_lead"], roles, "function_call")
    assert [e["type"] for e in evs] == ["conversation.item.create", "conversation.item.create", "response.create"]
    call, output = evs[0]["item"], evs[1]["item"]
    assert call["type"] == "function_call" and call["name"] == "task_update"
    assert output["type"] == "function_call_output" and output["call_id"] == call["call_id"]
    payload = json.loads(output["output"])
    assert payload["from_name"] == "Dwight Schrute"
    assert payload["result_summary"] == "Fixed it; tests pass."
    assert "how_to_mention_it" in payload
    # spike finding: per-response instructions make the model ignore the injected content
    assert "instructions" not in evs[2].get("response", {})


def test_fresh_call_ids(roles):
    a = injection_events(result(), roles["eng_lead"], roles, "function_call")
    b = injection_events(result(), roles["eng_lead"], roles, "function_call")
    assert a[0]["item"]["call_id"] != b[0]["item"]["call_id"]


def test_own_task_instruction(roles):
    evs = injection_events(result(), roles["eng_lead"], roles, "function_call")
    guidance = json.loads(evs[1]["item"]["output"])["how_to_mention_it"]
    assert "ask if they want to go through it now" in guidance


def test_cross_team_instruction_names_sender(roles):
    evs = injection_events(result(), roles["sales_lead"], roles, "function_call")
    guidance = json.loads(evs[1]["item"]["output"])["how_to_mention_it"]
    assert "Dwight" in guidance and "Fix bulk discount" in guidance


def test_user_message_mode_prefix(roles):
    evs = injection_events(result(), roles["sales_lead"], roles, "user_message")
    assert [e["type"] for e in evs] == ["conversation.item.create", "response.create"]
    item = evs[0]["item"]
    assert item["role"] == "user"
    text = item["content"][0]["text"]
    assert item["content"][0]["type"] == "input_text"
    assert text.startswith(NOTIFICATION_PREFIX) and NOTIFICATION_PREFIX == "[notification from system, not the user]"
    assert "Dwight" in text and "Fixed it; tests pass." in text
    assert "DM-200" not in text
