"""Sprint-internal dependency graph for agent execution within one sprint.

This is separate from PipelineSupervisor — it declares the stage ordering
and feedback edges specific to a single sprint's execution. SprintSupervisor
(and eventually PipelineSupervisor) reads this to determine which agents
can run next based on what's already complete.
"""

from __future__ import annotations


class SprintGraph:
    """Declares the dependency graph for sprint-internal agent execution.

    Normal edges map agent → list of agents that must complete first.
    Feedback edges map agent X → agent Y: when X fails, route to Y for diagnosis.

    SprintSupervisor uses this to determine execution order and feedback routing.
    """

    # Normal edges: agent → list of agents that must complete before it
    DEPENDENCIES: dict[str, list[str]] = {
        "scrum_master":   [],
        "file_planner":   ["scrum_master"],
        "backend":        ["file_planner"],
        "frontend":       ["file_planner"],
        "tech_lead":      ["backend", "frontend"],
        "qa":             ["tech_lead"],
        "sprint_deploy":  ["qa"],
        "sprint_review":  ["sprint_deploy"],
        "sprint_retro":   ["sprint_review"],
    }

    # Feedback edges: when agent X fails, route to agent Y
    FEEDBACK: dict[str, str] = {
        "tech_lead":   "backend",     # violations → re-run backend (and frontend)
        "qa":          "bug_analyst", # failures  → classify root cause
        "bug_analyst": "backend",     # code_bug  → re-run backend (and frontend)
    }

    @classmethod
    def ready_agents(cls, completed: set[str]) -> list[str]:
        """Return agents whose all dependencies are in completed.

        Parameters
        ----------
        completed : set[str]
            Set of agents that have completed execution.

        Returns
        -------
        list[str]
            Agents that can run next (all deps satisfied, not yet completed).
        """
        return [
            agent for agent, deps in cls.DEPENDENCIES.items()
            if agent not in completed and all(d in completed for d in deps)
        ]

    @classmethod
    def get_feedback_target(cls, agent: str) -> str | None:
        """Return the agent to route to when agent fails, or None if no feedback edge.

        Parameters
        ----------
        agent : str
            Agent name that failed.

        Returns
        -------
        str | None
            Next agent name for diagnosis/retry, or None if no feedback path.
        """
        return cls.FEEDBACK.get(agent)
