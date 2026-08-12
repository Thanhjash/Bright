"""Offline tests — fake HTTP transport, no network."""

from __future__ import annotations

import json

import pytest
from bright_contracts import ActPayload, AvailableAction, EmotionSpec

from bright_agent.act import ActEmitter, format_act, format_delay, to_text_stream
from bright_agent.base import Act, Done, TextDelta, ToolCall, ToolResult
from bright_agent.direct import LLMConfig, build_request_body
from bright_agent.prompt import SYSTEM_PROMPT, render_turn
from bright_agent.tools import CHOOSE_NEXT, RECORD_OBSERVATION, SAY, build_tools
from bright_agent.validation import REJECTION_LOG, validate_call

from .conftest import (
    FakeLLM,
    RecordingExecutor,
    finish_chunk,
    make_agent,
    make_ctx,
    sse,
    text_chunk,
    tool_chunk,
)


async def collect(agent, ctx):
    return [ev async for ev in agent.turn(ctx)]


# ------------------------------------------------------- request body shape


def test_thinking_disabled_is_a_top_level_field():
    body = build_request_body(LLMConfig(), [{"role": "user", "content": "hi"}])
    assert body["thinking"] == {"type": "disabled"}
    assert "extra_body" not in body
    # and nowhere nested
    assert "thinking" not in json.dumps(body["messages"])


def test_thinking_omitted_when_disabled_false():
    body = build_request_body(LLMConfig(disable_thinking=False), [])
    assert "thinking" not in body


def test_stream_options_requests_usage():
    body = build_request_body(LLMConfig(), [], stream=True)
    assert body["stream_options"] == {"include_usage": True}


# --------------------------------------------------------- streaming parse


async def test_streaming_text_is_yielded_in_order():
    fake = FakeLLM([sse([text_chunk("Look "), text_chunk("at the "), text_chunk("apple."), finish_chunk()])])
    agent = make_agent(fake, RecordingExecutor())
    events = await collect(agent, make_ctx())

    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Look ", "at the ", "apple."]
    done = events[-1]
    assert isinstance(done, Done) and done.reason == "complete"
    assert done.usage.prompt_tokens == 700
    assert done.usage.cached_tokens == 250
    assert done.usage.rounds == 1


async def test_reasoning_content_never_reaches_the_text_stream():
    chunk = {
        "choices": [{"index": 0, "delta": {"reasoning_content": "hmm let me think"}}],
    }
    fake = FakeLLM([sse([chunk, text_chunk("Hello."), finish_chunk()])])
    agent = make_agent(fake, RecordingExecutor())
    events = await collect(agent, make_ctx())
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello."


async def test_empty_response_is_no_action_not_error():
    fake = FakeLLM([sse([finish_chunk()])])
    agent = make_agent(fake, RecordingExecutor())
    events = await collect(agent, make_ctx())
    assert isinstance(events[-1], Done) and events[-1].reason == "no_action"


async def test_http_error_becomes_done_error_without_retry():
    fake = FakeLLM([], status=500)
    agent = make_agent(fake, RecordingExecutor())
    events = await collect(agent, make_ctx())
    assert events[-1].reason == "error"
    assert "500" in events[-1].detail
    assert len(fake.requests) == 1  # single attempt


async def test_undecodable_sse_chunk_is_skipped():
    body = b'data: {not json}\n\n' + sse([text_chunk("ok"), finish_chunk()])
    fake = FakeLLM([body])
    agent = make_agent(fake, RecordingExecutor())
    events = await collect(agent, make_ctx())
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "ok"


# -------------------------------------------------------- tool-call parsing


async def test_tool_call_split_across_chunks_is_merged():
    rounds = [
        sse(
            [
                text_chunk("Let's try again. "),
                tool_chunk(0, call_id="call_1", name=CHOOSE_NEXT, arguments='{"state_ver'),
                tool_chunk(0, arguments='sion": 88, "action_id"'),
                tool_chunk(0, arguments=': "scaffold_down"}'),
                finish_chunk("tool_calls"),
            ]
        )
    ]
    ex = RecordingExecutor({CHOOSE_NEXT: {"applied": True}})
    agent = make_agent(FakeLLM(rounds), ex)
    events = await collect(agent, make_ctx())

    call = next(e for e in events if isinstance(e, ToolCall))
    assert call.name == CHOOSE_NEXT
    assert call.arguments == {"state_version": 88, "action_id": "scaffold_down"}
    assert ex.calls == [(CHOOSE_NEXT, call.arguments)]
    assert isinstance(events[-1], Done) and events[-1].reason == "complete"


async def test_choose_next_is_terminal():
    """Once an action is chosen the turn ends — no second round."""
    fake = FakeLLM(
        [
            sse(
                [
                    tool_chunk(0, call_id="c1", name=CHOOSE_NEXT,
                               arguments='{"state_version":88,"action_id":"next_activity"}'),
                    finish_chunk("tool_calls"),
                ]
            ),
            sse([text_chunk("should never be requested"), finish_chunk()]),
        ]
    )
    agent = make_agent(fake, RecordingExecutor())
    events = await collect(agent, make_ctx())
    assert len(fake.requests) == 1
    assert events[-1].reason == "complete"


async def test_say_then_choose_next_across_two_rounds():
    fake = FakeLLM(
        [
            sse(
                [
                    tool_chunk(0, call_id="c1", name=SAY,
                               arguments='{"text":"Nearly! Look again.","style":"warm"}'),
                    finish_chunk("tool_calls"),
                ]
            ),
            sse(
                [
                    tool_chunk(0, call_id="c2", name=CHOOSE_NEXT,
                               arguments='{"state_version":88,"action_id":"repeat_activity"}'),
                    finish_chunk("tool_calls"),
                ]
            ),
        ]
    )
    ex = RecordingExecutor()
    agent = make_agent(fake, ex)
    events = await collect(agent, make_ctx())

    assert [n for n, _ in ex.calls] == [SAY, CHOOSE_NEXT]
    # the tool result was fed back to the model
    assert fake.requests[1]["messages"][-1]["role"] == "tool"
    assert events[-1].reason == "complete"


async def test_unparseable_arguments_end_the_turn_without_executing():
    fake = FakeLLM(
        [
            sse(
                [
                    tool_chunk(0, call_id="c1", name=CHOOSE_NEXT, arguments='{"action_id": '),
                    finish_chunk("tool_calls"),
                ]
            )
        ]
    )
    ex = RecordingExecutor()
    agent = make_agent(fake, ex)
    events = await collect(agent, make_ctx())

    assert ex.calls == []
    assert events[-1].reason == "error"
    assert REJECTION_LOG[-1].code == "bad_arguments"


async def test_tool_loop_is_bounded():
    """A model that never chooses must not spin. max_rounds then error."""
    round_body = sse(
        [
            tool_chunk(0, call_id="c", name=SAY, arguments='{"text":"hmm"}'),
            finish_chunk("tool_calls"),
        ]
    )
    fake = FakeLLM([round_body] * 5)
    agent = make_agent(fake, RecordingExecutor(), max_rounds=3)
    events = await collect(agent, make_ctx())
    assert len(fake.requests) == 3
    assert events[-1].reason == "error"
    assert "max_rounds" in events[-1].detail


async def test_executor_failure_is_not_retried():
    fake = FakeLLM(
        [
            sse(
                [
                    tool_chunk(0, call_id="c1", name=CHOOSE_NEXT,
                               arguments='{"state_version":88,"action_id":"next_activity"}'),
                    finish_chunk("tool_calls"),
                ]
            )
        ]
    )
    ex = RecordingExecutor({CHOOSE_NEXT: RuntimeError("core said no")})
    agent = make_agent(fake, ex)
    events = await collect(agent, make_ctx())

    assert len(ex.calls) == 1
    result = [e for e in events if isinstance(e, ToolResult)][-1]
    assert result.ok is False and "core said no" in result.error
    assert events[-1].reason == "error"


# ---------------------------------------------------------- validation


def test_rejects_action_id_not_in_available_actions():
    ctx = make_ctx()
    r = validate_call(ctx, CHOOSE_NEXT, {"state_version": 88, "action_id": "open_explore"})
    assert r is not None and r.code == "unknown_action_id"
    # eval material: everything needed to replay the decision
    assert r.available_action_ids == [a.id for a in ctx.available_actions]
    assert r.ctx_state_version == 88
    assert r.lesson_id == "en-a1-market-01"
    assert r.arguments["action_id"] == "open_explore"
    assert REJECTION_LOG[-1] is r


def test_rejects_stale_state_version():
    ctx = make_ctx(state_version=88)
    r = validate_call(ctx, CHOOSE_NEXT, {"state_version": 84, "action_id": "next_activity"})
    assert r is not None and r.code == "stale_state_version"


def test_rejects_future_state_version_too():
    r = validate_call(make_ctx(), CHOOSE_NEXT, {"state_version": 999, "action_id": "next_activity"})
    assert r is not None and r.code == "stale_state_version"


def test_rejects_missing_required_action_param():
    r = validate_call(make_ctx(), CHOOSE_NEXT, {"state_version": 88, "action_id": "call_student"})
    assert r is not None and r.code == "missing_field" and "student_id" in r.detail


def test_accepts_action_with_its_param():
    assert (
        validate_call(
            make_ctx(),
            CHOOSE_NEXT,
            {"state_version": 88, "action_id": "call_student", "params": {"student_id": "s17"}},
        )
        is None
    )


def test_rejects_unknown_tool():
    r = validate_call(make_ctx(), "board_show_vocabulary", {})
    assert r is not None and r.code == "unknown_tool"


def test_rejects_empty_say():
    assert validate_call(make_ctx(), SAY, {"text": "   "}).code == "empty_text"


def test_rejects_bad_observation():
    assert validate_call(
        make_ctx(), RECORD_OBSERVATION,
        {"student_id": "s17", "skill": "food_vocab", "result": "great", "evidence": "x"},
    ).code == "bad_arguments"
    assert validate_call(make_ctx(), RECORD_OBSERVATION, {"student_id": "s17"}).code == "missing_field"


def test_rejects_choose_next_when_core_offered_nothing():
    ctx = make_ctx(actions=[])
    r = validate_call(ctx, CHOOSE_NEXT, {"state_version": 88, "action_id": "next_activity"})
    assert r is not None and r.code == "no_available_actions"


async def test_illegal_action_never_reaches_the_executor():
    fake = FakeLLM(
        [
            sse(
                [
                    tool_chunk(0, call_id="c1", name=CHOOSE_NEXT,
                               arguments='{"state_version":88,"action_id":"launch_rocket"}'),
                    finish_chunk("tool_calls"),
                ]
            )
        ]
    )
    ex = RecordingExecutor()
    agent = make_agent(fake, ex)
    events = await collect(agent, make_ctx())

    assert ex.calls == []
    assert len(fake.requests) == 1  # and no reprompt
    assert events[-1].reason == "error"
    assert REJECTION_LOG[-1].code == "unknown_action_id"


# ---------------------------------------------------------------- tools


def test_choose_next_enum_is_populated_per_turn():
    ctx = make_ctx()
    schema = next(
        t for t in build_tools(ctx) if t["function"]["name"] == CHOOSE_NEXT
    )
    enum = schema["function"]["parameters"]["properties"]["action_id"]["enum"]
    assert enum == [a.id for a in ctx.available_actions]

    other = make_ctx(actions=[AvailableAction(id="start_roleplay", label="start market roleplay")])
    schema2 = next(t for t in build_tools(other) if t["function"]["name"] == CHOOSE_NEXT)
    assert schema2["function"]["parameters"]["properties"]["action_id"]["enum"] == ["start_roleplay"]


def test_choose_next_is_omitted_when_no_actions_are_legal():
    names = [t["function"]["name"] for t in build_tools(make_ctx(actions=[]))]
    assert CHOOSE_NEXT not in names
    assert len(names) == 4


def test_tool_surface_stays_at_five():
    assert len(build_tools(make_ctx())) == 5


# ------------------------------------------------------------------ act


def test_format_act_matches_protocol_grammar():
    assert format_act(ActPayload(emotion="happy", motion="nod")) == '<|ACT {"emotion":"happy","motion":"nod"}|>'
    assert format_act(ActPayload(emotion=EmotionSpec(name="think", intensity=0.6))) == (
        '<|ACT {"emotion":{"name":"think","intensity":0.6}}|>'
    )
    assert format_delay(1.5) == "<|DELAY 1.5|>"


def test_only_the_nine_emotions_exist():
    from bright_agent.act import EMOTIONS, make_act

    assert set(EMOTIONS) == {
        "happy", "sad", "angry", "think", "surprised",
        "awkward", "question", "curious", "neutral",
    }
    with pytest.raises(ValueError):
        make_act("excited")  # type: ignore[arg-type]


def test_emitter_dedupes_think_and_maps_outcomes():
    em = ActEmitter()
    assert em.on_tool_call(CHOOSE_NEXT).act.emotion == "think"
    assert em.on_tool_call(RECORD_OBSERVATION) is None  # deduped, once per turn
    assert em.on_tool_result(RECORD_OBSERVATION, {"result": "correct"}).act.emotion == "happy"
    assert em.on_tool_result(RECORD_OBSERVATION, {"result": "wrong"}).act.emotion == "curious"
    assert em.on_tool_result(SAY, {"result": "correct"}) is None
    assert em.on_done().act.emotion == "neutral"
    assert em.on_done() is None


def test_neutral_maps_to_idle_motion_group():
    from bright_agent.act import motion_group

    assert motion_group("neutral") == "Idle"
    assert motion_group("happy") == "Happy"


async def test_act_events_are_emitted_around_tool_activity():
    fake = FakeLLM(
        [
            sse(
                [
                    text_chunk("Good try. "),
                    tool_chunk(0, call_id="c1", name=RECORD_OBSERVATION,
                               arguments='{"student_id":"s17","skill":"food_vocab",'
                                         '"result":"wrong","evidence":"picked banana"}'),
                    finish_chunk("tool_calls"),
                ]
            ),
            sse(
                [
                    tool_chunk(0, call_id="c2", name=CHOOSE_NEXT,
                               arguments='{"state_version":88,"action_id":"scaffold_down"}'),
                    finish_chunk("tool_calls"),
                ]
            ),
        ]
    )
    ex = RecordingExecutor({RECORD_OBSERVATION: {"result": "wrong"}})
    agent = make_agent(fake, ex)
    events = await collect(agent, make_ctx())

    emotions = [e.act.emotion for e in events if isinstance(e, Act)]
    assert emotions == ["think", "curious", "neutral"]


async def test_to_text_stream_interleaves_act_tokens_inline():
    fake = FakeLLM(
        [
            sse(
                [
                    text_chunk("Nearly! "),
                    tool_chunk(0, call_id="c1", name=CHOOSE_NEXT,
                               arguments='{"state_version":88,"action_id":"scaffold_down"}'),
                    finish_chunk("tool_calls"),
                ]
            )
        ]
    )
    agent = make_agent(fake, RecordingExecutor())
    text = "".join([c async for c in to_text_stream(agent.turn(make_ctx()))])
    assert text == 'Nearly! <|ACT {"emotion":"think"}|><|ACT {"emotion":"neutral"}|>'


# --------------------------------------------------------------- prompt


def test_system_prompt_is_stable_and_small():
    assert render_turn(make_ctx()) not in SYSTEM_PROMPT
    # ~4 chars/token; keep well under the 600-token budget
    assert len(SYSTEM_PROMPT) < 2400, "system prompt is growing — it is sized for a 4.5B model"
    for e in ("happy", "sad", "angry", "think", "surprised", "awkward", "question", "curious", "neutral"):
        assert e in SYSTEM_PROMPT
    assert "Vietnamese hint" in SYSTEM_PROMPT


def test_turn_render_carries_everything_volatile():
    out = render_turn(make_ctx())
    assert "en-a1-market-01" in out and "PRACTICE" in out and "activity 3/9" in out
    assert "Which one is the apple?" in out
    assert "Minh (s17)" in out and "food_vocab 0.82" in out
    assert "picked banana → wrong" in out
    assert "2026-08-04" in out
    assert "state_version 88" in out
    for i, name in enumerate(
        ["next_activity", "repeat_activity", "scaffold_down", "call_student"], 1
    ):
        assert f"{i}. {name}" in out
    assert "[params: student_id]" in out


def test_volatile_content_is_only_in_the_user_message():
    from bright_agent.prompt import build_messages

    msgs = build_messages(make_ctx())
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == SYSTEM_PROMPT
    assert "88" not in msgs[0]["content"]
    assert msgs[1]["role"] == "user" and "state_version 88" in msgs[1]["content"]


def test_scene_summary_is_semantic_never_dom():
    from bright_agent.prompt import summarize_scene
    from bright_contracts import Scene

    s = Scene(
        stateVersion=1,
        kind="vocabulary",
        props={"items": [{"id": "a", "text": "apple"}, {"id": "b", "text": "rice"}],
               "highlightId": "a"},
    )
    out = summarize_scene(s)
    assert "apple" in out and "rice" in out and "highlight a" in out
    assert "<" not in out and "div" not in out
