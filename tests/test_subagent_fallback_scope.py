"""A sub agent must not reset the parent run's engaged fallback.

The fallback is an ordered chain, and it is sticky for a whole run: once the
primary model has failed a turn for good, the remaining steps stay on whichever
link answered instead of re-probing a provider we already know is down. It is
cleared once, at the top of a run.

That breaks when the parent delegates. A sub agent is built with
``model=parent.model`` — the *same* ``AgentLLMModel`` object, not a copy — and
its ``run_stream`` runs that same reset at its top. The child therefore clears
the fallback the parent is currently relying on: when the child returns, the
parent goes back to the primary model that just failed and burns the full retry
budget again on every remaining step. The child loses the backup too, since it
is running inside the same outage and starts on the dead primary itself — and
with a chain it would also rewind the parent to link 1, throwing away the
progress of every link already proven to be down.

The reset has to be scoped to a *top-level* run: an outer scope that already set
a run id means this run is nested and must leave the parent's routing alone.
"""

import pytest

from bridge.agent_bridge import AgentLLMModel

FALLBACK = {
    "enabled": True,
    "chain": [
        {"provider": "openai", "model": "backup-model"},
        {"provider": "qianfan", "model": "backup-model-2"},
    ],
}


def _model(monkeypatch, chat_fallback, **extra_conf):
    """An AgentLLMModel with a stubbed config (no bridge, no real bot)."""
    conf = {"model": "primary-model", "chat_fallback": chat_fallback}
    conf.update(extra_conf)
    monkeypatch.setattr("bridge.agent_bridge.conf", lambda: conf, raising=False)
    return AgentLLMModel.__new__(AgentLLMModel)


@pytest.fixture
def executor_cls():
    from agent.protocol.agent_stream import AgentStreamExecutor

    return AgentStreamExecutor


def _reset_like_a_run(executor_cls, model, ambient_run_id=None):
    """Run the real reset decision the way a run enters it.

    run_stream mints a run id only when no outer scope set one, and the reset
    follows the same scope. Driving the executor's real method under the same
    identity_scope a sub agent spawn uses keeps this honest: it breaks if
    either contract changes.
    """
    from common.runtime_identity import identity_scope
    from common.utils import (
        set_agent_run_id,
        clear_agent_run_id,
        current_agent_run_id,
    )
    import uuid as _uuid

    executor = executor_cls.__new__(executor_cls)
    executor.model = model

    def _body():
        # Mirrors run_stream: capture "am I nested?" BEFORE minting a run id,
        # then hand that to the reset.
        nested = bool(current_agent_run_id())
        token = None
        if not nested:
            token = set_agent_run_id(_uuid.uuid4().hex)
        try:
            executor._reset_model_fallback(nested_run=nested)
        finally:
            if token is not None:
                clear_agent_run_id(token)

    if ambient_run_id:
        with identity_scope(run_id=ambient_run_id):
            _body()
    else:
        _body()


class TestSubAgentDoesNotClearParentFallback:

    def test_a_nested_run_keeps_the_parents_engaged_fallback(
        self, monkeypatch, executor_cls
    ):
        """The regression: the child's reset knocked the parent off the backup."""
        model = _model(monkeypatch, FALLBACK)
        assert model.use_fallback() is True
        assert model.model == "backup-model"

        # A sub agent spawning mid-run, with the parent's run id ambient.
        _reset_like_a_run(executor_cls, model, ambient_run_id="parent-run-123")

        assert model.model == "backup-model", (
            "the sub agent cleared the fallback the parent is still relying on; "
            "the parent will re-probe the failed primary on its next step"
        )

    def test_a_top_level_run_still_resets(self, monkeypatch, executor_cls):
        """The fix must not break the normal case: a new run starts fresh."""
        model = _model(monkeypatch, FALLBACK)
        assert model.use_fallback() is True
        assert model.model == "backup-model"

        # No ambient run id: this run is the top of its own run.
        _reset_like_a_run(executor_cls, model)

        assert model.model == "primary-model"

    def test_the_reset_still_lets_the_next_turn_walk_the_chain(self, monkeypatch, executor_cls):
        """After a top-level reset the run starts from link 1 again."""
        model = _model(monkeypatch, FALLBACK)
        model.use_fallback()
        _reset_like_a_run(executor_cls, model)

        assert model.model == "primary-model"
        assert model.fallback_available() is True
        assert model.use_fallback() is True
        assert model.model == "backup-model"

    def test_a_nested_run_leaves_the_chain_position_alone(
        self, monkeypatch, executor_cls
    ):
        """A nested run must not hand the parent extra links, nor rewind it."""
        model = _model(monkeypatch, FALLBACK)
        model.use_fallback()

        _reset_like_a_run(executor_cls, model, ambient_run_id="parent-run-123")

        # Still on the backup and still on link 1, so the parent's next failure
        # advances to link 2 rather than repeating the one that just failed.
        assert model.model == "backup-model"
        assert model.fallback_available() is True

    def test_a_parent_that_walked_two_links_keeps_its_position(
        self, monkeypatch, executor_cls
    ):
        """The regression a chain adds: the child must not rewind the parent to
        link 1 after it already proved link 1 was down."""
        model = _model(monkeypatch, FALLBACK)
        assert model.use_fallback() is True   # link 1
        assert model.use_fallback() is True   # link 2
        assert model.model == "backup-model-2"

        _reset_like_a_run(executor_cls, model, ambient_run_id="parent-run-123")

        assert model.model == "backup-model-2"
        # The point of the test: the child's run did NOT rewind the parent to
        # link 1. (Two passes are available now, so more advances remain —
        # position, not exhaustion, is what this pins down.)
        assert model.fallback_available() is True
        assert model.use_fallback() is True
        assert model.model == "backup-model"  # wrapped around: pass 2, link 1
