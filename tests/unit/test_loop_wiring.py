"""The reviser loop's structure is load-bearing: the critic must be
advisory (no exit tool) and the verifier must hold the only exit, running
between critic and reviser. See the 2026-08-04 loop-verifier design.
"""

from cv_agents.sub_agents.writer.agent import reviser_loop_agent


def _tool_names(agent):
    return [getattr(tool, "__name__", getattr(tool, "name", "")) for tool in agent.tools]


def test_loop_order_is_critic_verifier_reviser():
    names = [a.name for a in reviser_loop_agent.sub_agents]
    assert names == ["critic_agent", "verifier_agent", "reviser_agent"]


def test_verifier_holds_the_only_exit():
    critic, verifier, reviser = reviser_loop_agent.sub_agents
    assert "exit_loop" in _tool_names(verifier)
    assert "exit_loop" not in _tool_names(critic)
    assert "exit_loop" not in _tool_names(reviser)


def test_verifier_writes_the_report_the_reviser_reads():
    _, verifier, reviser = reviser_loop_agent.sub_agents
    assert verifier.output_key == "verifier_report"
    assert "{verifier_report}" in reviser.instruction
