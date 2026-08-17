"""PipelineSupervisor — orchestrates the full 3-phase AI DevOS pipeline.

Replaces the hardcoded state machine in WorkflowManager.run().
Manages three phases:
  1. Discovery: requirements, architecture, design (runs once)
  2. Sprints: iterative implementation (runs N times via SprintSupervisor)
  3. Release: QA, DevOps, Documentation (runs once after all sprints)

Key design:
- Resumes from current state (idempotent, crash-safe)
- Calls engine.run_stage() for discovery and release stages
- Calls sprint_supervisor.run_sprint() for each sprint
- Non-fatal failures in release stages are logged but don't block
- Pauses for user action (design review) when needed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..observability.tracing import pipeline_span, stage_span, sprint_span  # R10
from ..shared.dto.pipeline_result import PipelineResult
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.project_state import ProjectState
from ..workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# R9 — Quick Build mode configuration
# Stages skipped when mode="quick" (prototype pipeline)
# ---------------------------------------------------------------------------
_QUICK_BUILD_SKIP_DISCOVERY = frozenset({
    "strategic_review",  # no strategic brief needed for prototypes
    "security",          # security review skipped in quick mode
})

_QUICK_BUILD_SKIP_RELEASE = frozenset({
    "document",          # no full documentation for prototypes
    "retro",             # no retrospective for prototypes
})

# Human gate stages skipped in quick mode — pipeline advances without pausing
_QUICK_BUILD_SKIP_GATES = frozenset({
    "architect",         # skip architecture review gate
    "designer",          # skip design review gate
    "sprint_planner",    # skip sprint plan review gate in quick mode
})

# Maximum sprints allowed in quick mode
_QUICK_BUILD_MAX_SPRINTS = 1

# State groupings for phase-based execution
DISCOVERY_STATES = {
    ProjectState.EMPTY,
    ProjectState.CLARIFYING,
    ProjectState.QA_PENDING,
    ProjectState.QA_IN_PROGRESS,
    ProjectState.REQUIREMENTS_READY,
    ProjectState.ARCHITECTURE_READY,
    ProjectState.ARCHITECTURE_REVIEW_PENDING,  # Phase 4: human gate after Architect
    ProjectState.DESIGN_READY,
    ProjectState.DESIGN_REVIEW_PENDING,
    ProjectState.DESIGN_APPROVED,
}

SPRINT_STATES = {
    ProjectState.SPRINT_PLAN_READY,
    ProjectState.SPRINT_PLAN_REVIEW_PENDING,  # Phase 4: human gate after SprintPlanner
    ProjectState.SPRINT_IN_PROGRESS,
    ProjectState.SPRINT_BLOCKED,
}

RELEASE_STATES = {
    ProjectState.ALL_SPRINTS_COMPLETE,
    ProjectState.QA_COMPLETE,
}

from .dependency_graph import DependencyGraph

def get_discovery_stages() -> list[str]:
    """Dynamically get discovery stages from DependencyGraph up to sprint_planner."""
    order = DependencyGraph.STAGE_ORDER
    if not order:
        DependencyGraph._load_config()
        order = DependencyGraph.STAGE_ORDER
    
    stages = []
    for s in order:
        stages.append(s)
        if s == "sprint_planner":
            break
    return stages

def get_release_stages() -> list[str]:
    """Dynamically get release stages from DependencyGraph after sprint_planner."""
    order = DependencyGraph.STAGE_ORDER
    if not order:
        DependencyGraph._load_config()
        order = DependencyGraph.STAGE_ORDER
    
    stages = []
    found_sprint_planner = False
    for s in order:
        if found_sprint_planner:
            stages.append(s)
        if s == "sprint_planner":
            found_sprint_planner = True
    return stages


@dataclass
class _StageResult:
    """Internal result from running a single stage."""
    success: bool
    message: str = ""


class PipelineSupervisor:
    """Orchestrates the full 3-phase pipeline (Discovery → Sprints → Release).

    Single responsibility: advance the pipeline through Discovery → Sprints →
    Release phases by delegating to the right collaborator at each step.

    Parameters
    ----------
    workspace : WorkspaceManager
        Reads/writes project state and artifacts.
    engine
        WorkflowEngine — runs individual stages (execute→review→retry).
    sprint_executor
        SprintExecutor — runs one complete sprint end-to-end.
        Eliminates the circular dependency that previously existed when
        PipelineSupervisor called back into WorkflowManager._run_sprint_with_retry.
    settings
        Settings object with LLM and feature configuration.
    change_manager : optional
        ChangeManager — used by BugAnalyst spec/architecture rollback.
        If None, BugAnalyst spec/architecture rollback is skipped (logged only).
    memory_manager : optional
        MemoryManager — stores sandbox results so BugAnalyst can read them.
        If None, sandbox results are not persisted to memory.
    """

    def __init__(
        self,
        workspace,
        engine,
        sprint_executor,
        settings,
        file_indexer=None,
        dependency_graph=None,
        code_summarizer=None,
        code_sandbox=None,
        dependency_pinner=None,
        preview_manager=None,
        change_manager=None,
        memory_manager=None,
        blueprint_store=None,
    ) -> None:
        self.workspace = workspace
        self.engine = engine
        self._sprint_executor = sprint_executor
        self.settings = settings
        self._file_indexer = file_indexer            # Phase 3: intelligence layer — file indexer
        self._dependency_graph = dependency_graph    # Phase 3: intelligence layer — dep graph
        self._code_summarizer = code_summarizer      # Phase 3: intelligence layer — summarizer
        self._code_sandbox = code_sandbox            # Phase 5: code execution sandbox
        self._dependency_pinner = dependency_pinner  # R2: pin requirements to stable versions
        self._preview_manager = preview_manager      # R5: live app preview
        self._change_manager = change_manager        # BugAnalyst spec/arch rollback
        self._memory_manager = memory_manager        # sandbox result storage
        self._blueprint_store = blueprint_store      # BlueprintStore — blueprint persistence
        
        # Event store for event sourcing (dual-write)
        from ..memory.memory_repository import MemoryRepository
        from ..memory.manager import MemoryManager
        if memory_manager:
            if isinstance(memory_manager, MemoryRepository):
                storage_adapter = memory_manager.storage
            elif isinstance(memory_manager, MemoryManager):
                storage_adapter = memory_manager.repository.storage
            else:
                # Test mock or other - try to get storage adapter
                storage_adapter = getattr(memory_manager, 'storage', None) or getattr(getattr(memory_manager, 'repository', None), 'storage', None)
            from ..workflow.event_store import EventStore
            self._events = EventStore(storage_adapter) if storage_adapter else None
        else:
            self._events = None

    def _get_project_mode(self, project_id: str) -> str:
        """Read project mode from project.json. Returns 'full' if not set."""
        try:
            data = self.workspace.load_project_json(project_id) or {}
            return data.get("mode", "full") or "full"
        except Exception:
            return "full"

    def _get_project_type(self, project_id: str) -> str | None:
        """Read project_type from blueprint or project.json."""
        try:
            # Try blueprint first
            if self._blueprint_store is not None:
                bp = self._blueprint_store.get(project_id)
                if bp and bp.get("project_type"):
                    return bp["project_type"]
            # Fallback to project.json
            data = self.workspace.load_project_json(project_id) or {}
            return data.get("project_type")
        except Exception:
            return None

    def _create_react_native_scaffold(self, project_id: str) -> None:
        """Create mandatory React Native entry-point files if they don't exist.

        Creates: App.tsx, babel.config.js, tsconfig.json, metro.config.js
        Only runs for project_type == "react_native" or "mobile_app".
        Uses the project_writer mechanism to write files.
        """
        project_type = self._get_project_type(project_id)
        if not project_type:
            return
        pt = project_type.lower().strip()
        if pt not in ("react_native", "mobile_app", "mobile", "expo"):
            return

        try:
            from ..execution.project_writer import ProjectWriter
            writer = ProjectWriter(self.workspace)

            # App.tsx - Expo entry point
            app_tsx = '''import { StatusBar } from "expo-status-bar";
import { StyleSheet, Text, View } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import * as Font from "expo-font";
import * as SplashScreen from "expo-splash-screen";
import { useColorScheme } from "react-native";
import { useEffect, useState } from "react";

const Stack = createNativeStackNavigator();

function App() {
  const [fontsLoaded, setFontsLoaded] = useState(false);
  const colorScheme = useColorScheme();

  useEffect(() => {
    async function prepare() {
      try {
        await SplashScreen.preventAutoHideAsync();
        await Font.loadAsync({
          "Inter-Regular": require("./assets/fonts/Inter-Regular.ttf"),
        });
        setFontsLoaded(true);
      } catch (e) {
        console.warn(e);
        setFontsLoaded(true);
      }
    }
    prepare();
  }, []);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colorScheme === "dark" ? "#1a1a2e" : "#fff" },
          headerTintColor: colorScheme === "dark" ? "#fff" : "#000",
        }}
      >
        <Stack.Screen name="Home" component={HomeScreen} options={{ title: "Welcome" }} />
      </Stack.Navigator>
      <StatusBar style={colorScheme === "dark" ? "light" : "dark"} />
    </NavigationContainer>
  );
}

function HomeScreen({ navigation }: any) {
  return (
    <View style={styles.container}>
      <Text style={[styles.text, { color: colorScheme === "dark" ? "#fff" : "#000" }]}>
        Welcome to your React Native App!
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  text: {
    fontSize: 18,
    textAlign: "center",
  },
});

export default App;
'''

            # babel.config.js
            babel_config = '''module.exports = function(api) {
  api.cache(true);
  return {
    presets: ["babel-preset-expo"],
    plugins: [
      "nativewind/babel",
      ["module-resolver", { root: ["./src"] }],
    ],
  };
};
'''

            # tsconfig.json
            tsconfig = '''{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "isolatedModules": true,
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["react", "react-native", "jest", "@testing-library/jest-native"]
  },
  "include": ["**/*.ts", "**/*.tsx", ".expo/types/**/*.d.ts", "expo-env.d.ts"],
  "exclude": ["node_modules", "dist", ".expo"]
}
'''

            # metro.config.js
            metro_config = '''const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");

const config = getDefaultConfig(__dirname);

config.transformer = {
  ...config.transformer,
  babelTransformerPath: require.resolve("react-native-svg-transformer"),
};
config.resolver = {
  ...config.resolver,
  assetExts: config.resolver.assetExts.filter((ext: string) => ext !== "svg"),
  sourceExts: [...config.resolver.sourceExts, "svg"],
};

module.exports = withNativeWind(config, { input: "./global.css" });
'''

            # Write files only if they don't exist
            project_dir = self.workspace.get_workspace_path(project_id) / "project"
            project_dir.mkdir(parents=True, exist_ok=True)

            scaffold_files = {
                "App.tsx": app_tsx,
                "babel.config.js": babel_config,
                "tsconfig.json": tsconfig,
                "metro.config.js": metro_config,
            }

            for filename, content in scaffold_files.items():
                file_path = project_dir / filename
                if not file_path.exists():
                    writer.write_file(
                        project_id=project_id,
                        file_path=filename,
                        content=content,
                        attempt=1,
                    )
                    logger.info(
                        "[PipelineSupervisor] Created React Native scaffold file: %s",
                        filename,
                    )

        except Exception as exc:
            logger.warning(
                "[PipelineSupervisor] Failed to create React Native scaffold (non-fatal): %s",
                exc,
            )

    def run(
        self,
        project_id: str,
        request: str,
    ) -> PipelineResult:
        """Execute pipeline from current state, advancing through all phases.

        Resumes from the project's current ProjectState. Safe to call
        multiple times — each call is idempotent per state. Pauses at
        DESIGN_REVIEW_PENDING and SPRINT_BLOCKED states.

        Parameters
        ----------
        project_id : str
            Project identifier.
        request : str
            User-facing request/description for this project.

        Returns
        -------
        PipelineResult
            Result with final state, success flag, and completed stages.
        """
        try:
            mode = self._get_project_mode(project_id)
            with pipeline_span(project_id=project_id, mode=mode):
                return self._run_impl(project_id, request)
        except Exception as exc:
            logger.error(
                "[PipelineSupervisor] pipeline crashed: %s",
                exc,
                exc_info=True,
            )
            try:
                state = self.workspace.get_state(project_id)
                data = self.workspace.load_project_json(project_id) or {}
                stages = list(data.get("stages_completed", []))
            except Exception:
                state = ProjectState.FAILED
                stages = []
            return PipelineResult(
                project_id=project_id,
                state=state,
                success=False,
                message=f"Pipeline error: {exc}",
                completed_stages=stages,
            )

    def _run_impl(self, project_id: str, request: str) -> PipelineResult:
        """Internal pipeline execution."""
        state = self.workspace.get_state(project_id)
        logger.info(
            "[PipelineSupervisor] pipeline starting from state: %s",
            state.value if hasattr(state, "value") else state,
        )

        # ── RESUMING_FROM_CHANGE → REPLANNING ───────────────────────────────────
        # When ChangeManager.apply() sets RESUMING_FROM_CHANGE the pipeline has
        # no valid route and previously fell through to the terminal-state handler
        # (returning success=False with no explanation).  This block is the state
        # router that makes RESUMING_FROM_CHANGE a valid entry point.
        #
        # This does NOT implement actual replanning — it only transitions state
        # so the next pipeline invocation can detect REPLANNING and act.
        # Actual selective re-execution is implemented in a later task.
        if state == ProjectState.RESUMING_FROM_CHANGE:
            logger.info(
                "[PipelineSupervisor] RESUMING_FROM_CHANGE detected — "
                "transitioning to REPLANNING: project=%s",
                project_id,
            )
            self.workspace.update_state(project_id, ProjectState.REPLANNING)
            data = self.workspace.load_project_json(project_id) or {}
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.REPLANNING,
                success=True,
                message="Requirement change applied — pipeline is awaiting replanning.",
                requires_user_action=False,
                completed_stages=list(data.get("stages_completed", [])),
            )

        # ── REPLANNING → selective phase resume ────────────────────────────────
        # REPLANNING is set by the RESUMING_FROM_CHANGE router (block above).
        # At this point:
        #   - stages_completed already contains ONLY safe stages — ChangeManager
        #     removed the affected stages during apply(), so the affected ones are
        #     simply absent here.  _run_discovery() / _run_sprints() naturally
        #     re-run any stage not in stages_completed (their existing skip logic).
        #   - completed_sprints is NOT modified by ChangeManager — sprints whose
        #     sprint_number is already in that set are skipped by _run_sprints().
        #
        # Known limitation: changes that affect code inside a previously-completed
        # sprint (sprint_number in completed_sprints) do NOT cause that sprint to
        # re-run.  Resolving this requires a sprint-number → stage-name mapping
        # that does not yet exist in the architecture (future task).
        if state == ProjectState.REPLANNING:
            from .stage_lookup import resolve_stage_name as _rsn
            _data = self.workspace.load_project_json(project_id) or {}
            _completed_set = set(_data.get("stages_completed", []))
            _quick = self._get_project_mode(project_id) == "quick"

            # Check if every required discovery stage is represented in stages_completed.
            # Skip quick-build-excluded stages so quick mode doesn't appear incomplete.
            _discovery_required = [
                s for s in get_discovery_stages()
                if not (_quick and s in _QUICK_BUILD_SKIP_DISCOVERY)
            ]
            _discovery_complete = all(
                _rsn(s) in _completed_set for s in _discovery_required
            )

            if not _discovery_complete:
                # At least one discovery stage was removed by ChangeManager.
                # _run_discovery() will skip stages still in _completed_set and
                # only execute the missing (affected) ones.
                logger.info(
                    "[PipelineSupervisor] REPLANNING: discovery incomplete — "
                    "resuming from Discovery phase: project=%s",
                    project_id,
                )
                self.workspace.update_state(project_id, ProjectState.REQUIREMENTS_READY)
                state = ProjectState.REQUIREMENTS_READY
            else:
                # Discovery is intact — check whether sprint work is still pending.
                _sprint_plan = self.workspace.get_sprint_plan(project_id)
                _sprint_stale = _sprint_plan.stale if _sprint_plan else False
                _completed_sprint_nums = set(_data.get("completed_sprints", []))
                _pending_sprints = _sprint_plan is not None and any(
                    s.sprint_number not in _completed_sprint_nums
                    for s in _sprint_plan.sprints
                )

                if _sprint_stale or _pending_sprints:
                    logger.info(
                        "[PipelineSupervisor] REPLANNING: discovery intact — "
                        "resuming from Sprints phase "
                        "(stale=%s pending_sprints=%s): project=%s",
                        _sprint_stale, _pending_sprints, project_id,
                    )
                    self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
                    state = ProjectState.SPRINT_IN_PROGRESS
                else:
                    # Discovery complete and all sprints accounted for — resume Release.
                    logger.info(
                        "[PipelineSupervisor] REPLANNING: discovery and sprints intact — "
                        "resuming from Release phase: project=%s",
                        project_id,
                    )
                    # Clear release stages from stages_completed so they re-run.
                    # stages_completed is keyed by stage name string (e.g., "QA", "DevOps").
                    _release_stage_keys = set(get_release_stages())
                    _current_completed = set(_data.get("stages_completed", []))
                    _to_clear = _current_completed & _release_stage_keys
                    if _to_clear:
                        _new_completed = list(_current_completed - _to_clear)
                        self.workspace.update_project_json(project_id, {"stages_completed": _new_completed})
                        logger.info(
                            "[PipelineSupervisor] REPLANNING: cleared release stages from stages_completed: %s",
                            sorted(_to_clear),
                        )
                    self.workspace.update_state(project_id, ProjectState.ALL_SPRINTS_COMPLETE)
                    state = ProjectState.ALL_SPRINTS_COMPLETE
            # Fall through — the existing phase routing below picks up the
            # updated state and delegates to the correct phase method.

        # Resume from current state — do not re-run completed phases
        if state in DISCOVERY_STATES:
            result = self._run_discovery(project_id, request)
            if not result.success:
                return result
            # After discovery, check state again (may have paused for a gate)
            state = self.workspace.get_state(project_id)
            if state == ProjectState.ARCHITECTURE_REVIEW_PENDING:
                data = self.workspace.load_project_json(project_id) or {}
                return PipelineResult(
                    project_id=project_id,
                    state=state,
                    success=False,
                    message="Architecture ready for review",
                    requires_user_action=True,
                    action_needed="review_architecture",
                    completed_stages=list(data.get("stages_completed", [])),
                )
            if state == ProjectState.DESIGN_REVIEW_PENDING:
                data = self.workspace.load_project_json(project_id) or {}
                return PipelineResult(
                    project_id=project_id,
                    state=state,
                    success=False,
                    message="Design ready for review",
                    requires_user_action=True,
                    action_needed="review_design",
                    completed_stages=list(data.get("stages_completed", [])),
                )

        if state in SPRINT_STATES or state == ProjectState.DESIGN_APPROVED:
            result = self._run_sprints(project_id, request)
            if not result.success:
                return result
            state = self.workspace.get_state(project_id)

        if state in RELEASE_STATES or state == ProjectState.ALL_SPRINTS_COMPLETE:
            result = self._run_release(project_id, request)
            return result

        # Terminal states
        data = self.workspace.load_project_json(project_id) or {}
        
        # Append WORKFLOW_FAILED event if pipeline failed
        if state not in [ProjectState.DEPLOYABLE, ProjectState.DONE] and self._events:
            self._events.append(
                workflow_id=project_id,
                event_type="workflow.failed",
                actor="engine",
                trace_id=None,
                payload={"error": f"Pipeline ended in state: {state.value if hasattr(state, 'value') else state}"},
            )
        
        return PipelineResult(
            project_id=project_id,
            state=state,
            success=state in [ProjectState.DEPLOYABLE, ProjectState.DONE],
            message=f"Pipeline in state: {state.value if hasattr(state, 'value') else state}",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _run_discovery(self, project_id: str, request: str) -> PipelineResult:
        """Run Discovery phase: requirements, architecture, design.

        Runs stages in order (StrategicReview → ProductOwner → Architect →
        Designer → Security → SprintPlanner). ScrumMaster runs per-sprint
        inside _run_sprint(). Resumes from
        current stage. Pauses for design review after Designer.

        Returns
        -------
        PipelineResult
            success=True if discovery complete, success=False if a stage failed.
            May pause with requires_user_action=True at DESIGN_REVIEW_PENDING.
        """
        logger.info("[PipelineSupervisor] entering Discovery phase")
        data = self.workspace.load_project_json(project_id) or {}
        completed = set(data.get("stages_completed", []))
        quick_mode = self._get_project_mode(project_id) == "quick"
        if quick_mode:
            logger.info("[PipelineSupervisor] QUICK BUILD mode — skipping stages: %s", _QUICK_BUILD_SKIP_DISCOVERY)

        for stage_key in get_discovery_stages():
            # Resolve stage name to Stage enum value for completed check
            from .stage_lookup import resolve_stage_name
            stage_value = resolve_stage_name(stage_key)

            if stage_value in completed:
                logger.debug("[PipelineSupervisor] stage %s already completed, skipping", stage_key)
                continue

            # R9: skip stages not needed in quick build mode
            if quick_mode and stage_key in _QUICK_BUILD_SKIP_DISCOVERY:
                logger.info("[PipelineSupervisor] quick mode: skipping stage %s", stage_key)
                continue

            logger.debug("[PipelineSupervisor] running discovery stage: %s", stage_key)
            result = self._run_stage_safe(project_id, stage_key, request)
            if not result.success:
                logger.error(
                    "[PipelineSupervisor] discovery stage %s failed: %s",
                    stage_key, result.message,
                )
                return PipelineResult(
                    project_id=project_id,
                    state=self.workspace.get_state(project_id),
                    success=False,
                    message=f"Discovery stage {stage_key} failed: {result.message}",
                    failed_stage=stage_key,
                    completed_stages=list(data.get("stages_completed", [])),
                )

            if stage_key == "architect" and result.success:
                # Extract the structured blueprint from the Architect artifact and persist it.
                if self._blueprint_store is not None:
                    try:
                        artifact = getattr(result, "artifact", None)
                        structured = (
                            artifact.structured_content
                            if artifact and hasattr(artifact, "structured_content")
                            else {}
                        )
                        if structured:
                            self._blueprint_store.save(project_id, structured)
                        else:
                            logger.warning(
                                "[PipelineSupervisor] Architect produced no structured output — "
                                "blueprint not stored: project=%s", project_id,
                            )
                    except Exception as exc:
                        logger.warning(
                            "[PipelineSupervisor] blueprint save failed (non-fatal): project=%s error=%s",
                            project_id, exc,
                        )

            # Phase 4: After Architect — pause for architecture review gate.
            # R9: skip gate in quick mode (auto-approve).
            if stage_key == "architect" and not quick_mode:
                if self.engine.requires_human_review(stage_key):
                    logger.info("[PipelineSupervisor] architecture ready, pausing for human review gate")
                    self.workspace.update_state(project_id, ProjectState.ARCHITECTURE_REVIEW_PENDING)
                    data = self.workspace.load_project_json(project_id) or {}
                    return PipelineResult(
                        project_id=project_id,
                        state=ProjectState.ARCHITECTURE_REVIEW_PENDING,
                        success=True,
                        message="Architecture ready for review",
                        requires_user_action=True,
                        action_needed="review_architecture",
                        completed_stages=list(data.get("stages_completed", [])),
                    )
            if stage_key == "architect" and quick_mode:
                logger.info("[PipelineSupervisor] quick mode: auto-approving architecture gate")

            # After Designer: pause for design review before continuing to Security
            # R9: skip gate in quick mode (auto-approve).
            if stage_key == "designer" and not quick_mode:
                if self.engine.requires_human_review(stage_key):
                    logger.info("[PipelineSupervisor] design ready, pausing for review")
                    self.workspace.update_state(project_id, ProjectState.DESIGN_REVIEW_PENDING)
                    data = self.workspace.load_project_json(project_id) or {}
                    return PipelineResult(
                        project_id=project_id,
                        state=ProjectState.DESIGN_REVIEW_PENDING,
                        success=True,
                        message="Design ready for review",
                        requires_user_action=True,
                        action_needed="review_design",
                        completed_stages=list(data.get("stages_completed", [])),
                    )
            if stage_key == "designer" and quick_mode:
                logger.info("[PipelineSupervisor] quick mode: auto-approving design gate")

            # Phase 4: After SprintPlanner — pause for sprint plan review before sprint execution.
            # R9: skip gate in quick mode (auto-approve).
            if stage_key == "sprint_planner" and not quick_mode:
                if self.engine.requires_human_review(stage_key):
                    logger.info("[PipelineSupervisor] sprint plan ready, pausing for human review gate")
                    self.workspace.update_state(project_id, ProjectState.SPRINT_PLAN_REVIEW_PENDING)
                    data = self.workspace.load_project_json(project_id) or {}
                    return PipelineResult(
                        project_id=project_id,
                        state=ProjectState.SPRINT_PLAN_REVIEW_PENDING,
                        success=True,
                        message="Sprint plan ready for review",
                        requires_user_action=True,
                        action_needed="review_sprint_plan",
                        completed_stages=list(data.get("stages_completed", [])),
                    )
            if stage_key == "sprint_planner" and quick_mode:
                logger.info("[PipelineSupervisor] quick mode: auto-approving sprint plan gate")

        logger.info("[PipelineSupervisor] Discovery phase complete")
        self.workspace.update_state(project_id, ProjectState.DESIGN_APPROVED)
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.DESIGN_APPROVED,
            success=True,
            message="Discovery phase complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _run_sprints(self, project_id: str, request: str) -> PipelineResult:
        """Run Sprints phase: execute each sprint via SprintSupervisor.

        Loads sprint plan, finds unstarted sprints, runs each one.
        Stops if any sprint returns blocked=True (retry limits exceeded).
        Updates state to ALL_SPRINTS_COMPLETE when all sprints pass.

        Returns
        -------
        PipelineResult
            success=True if all sprints complete.
            success=False + blocked=True if a sprint hits retry limit.
            success=False otherwise.
        """
        logger.info("[PipelineSupervisor] entering Sprints phase")
        data = self.workspace.load_project_json(project_id) or {}
        completed_sprints = set(data.get("completed_sprints", []))
        quick_mode = self._get_project_mode(project_id) == "quick"

        state = self.workspace.get_state(project_id)
        # Phase 4: if we're still at SPRINT_PLAN_REVIEW_PENDING, the gate hasn't been approved yet.
        # R9: skip this gate in quick mode.
        if state == ProjectState.SPRINT_PLAN_REVIEW_PENDING and quick_mode:
            logger.info("[PipelineSupervisor] quick mode: auto-approving sprint plan gate")
            self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
        elif state == ProjectState.SPRINT_PLAN_REVIEW_PENDING:
            data = self.workspace.load_project_json(project_id) or {}
            return PipelineResult(
                project_id=project_id,
                state=state,
                success=False,
                message="Sprint plan ready for review",
                requires_user_action=True,
                action_needed="review_sprint_plan",
                completed_stages=list(data.get("stages_completed", [])),
            )

        sprint_plan = self.workspace.get_sprint_plan(project_id)
        if not sprint_plan or not sprint_plan.sprints:
            logger.warning("[PipelineSupervisor] no sprint plan found")
            self.workspace.update_state(project_id, ProjectState.ALL_SPRINTS_COMPLETE)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.ALL_SPRINTS_COMPLETE,
                success=True,
                message="No sprints to run",
                completed_stages=list(data.get("stages_completed", [])),
            )

        # R9: Quick Build mode caps sprint count at _QUICK_BUILD_MAX_SPRINTS (1)
        sprints_to_run = sprint_plan.sprints
        if quick_mode and len(sprints_to_run) > _QUICK_BUILD_MAX_SPRINTS:
            logger.info(
                "[PipelineSupervisor] quick mode: capping sprints to %d (of %d planned)",
                _QUICK_BUILD_MAX_SPRINTS, len(sprints_to_run),
            )
            sprints_to_run = sprints_to_run[:_QUICK_BUILD_MAX_SPRINTS]

        # SPRINT_BLOCKED: the sprint agent pipeline (ScrumMaster → FrontendDeveloper)
        # already completed for this sprint; only the sandbox verification
        # (install → build → test) failed.  Retry only the sandbox instead of
        # re-running all LLM-agent stages from scratch.
        if state == ProjectState.SPRINT_BLOCKED:
            sandbox_retry_result = self._retry_sandbox_for_blocked_sprint(
                project_id, sprints_to_run, completed_sprints,
            )
            if not sandbox_retry_result.success:
                return sandbox_retry_result
            # Sandbox passed (or a fallback was triggered) — refresh completed_sprints
            # so the regular loop below skips the now-complete blocked sprint.
            data = self.workspace.load_project_json(project_id) or {}
            completed_sprints = set(data.get("completed_sprints", []))

        for sprint in sprints_to_run:
            n = sprint.sprint_number
            if n in completed_sprints:
                logger.debug("[PipelineSupervisor] sprint %d already completed, skipping", n)
                continue

            logger.info("[PipelineSupervisor] running sprint %d", n)
            self.workspace.set_current_sprint(project_id, n)

            # R10: instrument each sprint with a tracing span (no-op when OTel not configured).
            with sprint_span(project_id=project_id, sprint_number=n):
                sprint_result = self._sprint_executor.run(project_id, sprint)

            # R2: Syntax check before marking sprint complete — fail fast on parse errors.
            # Only runs when CodeSandbox is enabled; skips silently in dev mode.
            if sprint_result.success and self._code_sandbox is not None:
                syntax_errors = self._code_sandbox.syntax_check(project_id, sprint=n)
                if syntax_errors:
                    error_text = "; ".join(syntax_errors[:5])  # cap for message length
                    logger.error(
                        "[PipelineSupervisor] sprint %d syntax errors — not marking complete: %s",
                        n, error_text,
                    )
                    return PipelineResult(
                        project_id=project_id,
                        state=self.workspace.get_state(project_id),
                        success=False,
                        message=f"Sprint {n} syntax errors (code not parseable):\n{chr(10).join(syntax_errors)}",
                        failed_stage=f"sprint_{n}_syntax",
                        current_sprint=n,
                        completed_stages=list(data.get("stages_completed", [])),
                    )

            if not sprint_result.success:
                logger.error(
                    "[PipelineSupervisor] sprint %d failed: %s",
                    n, sprint_result.message,
                )
                # AC-P2-08: transition to SPRINT_BLOCKED so the failure state is
                # visible, durable, and meaningful.  Without this the project stays
                # SPRINT_IN_PROGRESS even though execution has stopped.
                self.workspace.update_state(project_id, ProjectState.SPRINT_BLOCKED)
                # Persist the failure reason so it survives a process restart.
                self.workspace.update_project_json(
                    project_id,
                    {f"sprint_{n}_failure_reason": sprint_result.message},
                )
                data = self.workspace.load_project_json(project_id) or {}
                return PipelineResult(
                    project_id=project_id,
                    state=ProjectState.SPRINT_BLOCKED,
                    success=False,
                    message=f"Sprint {n} failed: {sprint_result.message}",
                    failed_stage=f"sprint_{n}",
                    current_sprint=n,
                    completed_stages=list(data.get("stages_completed", [])),
                )

            # SprintExecutor.run() already calls mark_sprint_complete before returning.
            # Calling it again here would cause a read-modify-write race on project.json
            # if any concurrent write occurs between the two calls.
            logger.info("[PipelineSupervisor] sprint %d complete", n)

            # Create React Native scaffold files on first sprint for mobile projects.
            # These entry-point files (App.tsx, babel.config.js, tsconfig.json, metro.config.js)
            # are required for React Native/Expo projects and must exist before code generation.
            if n == 1:
                self._create_react_native_scaffold(project_id)

            # Phase 3: trigger intelligence layer to index the newly written files.
            # Non-blocking — failures are logged but never stop the pipeline.
            self._trigger_intelligence_index(project_id, sprint_number=n)
            # R2: Pin dependencies to exact stable versions before running sandbox.
            # Non-blocking — failures are logged but never stop the pipeline.
            self._pin_dependencies(project_id, sprint_number=n)
            # Phase 5: run code execution sandbox to produce real lint/test/build results
            # for BugAnalyst to consume in the Release phase.
            self._run_sandbox(project_id, sprint_number=n)
            # R4: commit sprint files to git history.
            # Non-blocking — git errors never stop the pipeline.
            self._commit_sprint_to_git(project_id, n, sprint)
            # R5: start/restart the live preview after sprint passes sandbox.
            # Only starts if sandbox build succeeded (R2 must be green).
            self._start_preview(project_id, sprint_number=n)

        logger.info("[PipelineSupervisor] all sprints complete")
        self.workspace.update_state(project_id, ProjectState.ALL_SPRINTS_COMPLETE)
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.ALL_SPRINTS_COMPLETE,
            success=True,
            message="All sprints complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _retry_sandbox_for_blocked_sprint(
        self,
        project_id: str,
        sprints_to_run: list,
        completed_sprints: set,
    ) -> PipelineResult:
        """Re-run only sandbox verification for the sprint that caused SPRINT_BLOCKED.

        Called by _run_sprints() when the pipeline resumes from SPRINT_BLOCKED state.
        The sprint agent pipeline (ScrumMaster → SprintDelta → FileStructurePlanner
        → BackendDeveloper → FrontendDeveloper) already completed successfully for this
        sprint; only the sandbox verification (install → build → test) failed.  Retrying
        all agent stages is wasteful and unnecessary.

        Fallback paths:
        - No sandbox wired → transition to SPRINT_IN_PROGRESS (full re-run by caller).
        - current_sprint_number unknown / invalid → same fallback.
        - blocked sprint not found in plan → same fallback.
        All fallback paths return success=True so _run_sprints() continues normally.

        On sandbox retry success: marks the sprint complete and runs post-sprint steps
        (intelligence indexing, dependency pinning, sandbox memory write, git commit,
        preview start) — mirroring the successful-sprint path in _run_sprints().

        On sandbox retry failure: returns success=False with SPRINT_BLOCKED state so
        the pipeline surfaces the error without having wasted LLM-agent tokens.
        """
        data = self.workspace.load_project_json(project_id) or {}

        # ── Graceful fallback: no sandbox wired ──────────────────────────────
        if self._code_sandbox is None:
            logger.info(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: sandbox not wired — "
                "falling back to full sprint re-run: project=%s", project_id,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_IN_PROGRESS,
                success=True,
                message="SPRINT_BLOCKED fallback: no sandbox wired",
                completed_stages=list(data.get("stages_completed", [])),
            )

        # ── Determine which sprint is blocked ────────────────────────────────
        raw_num = data.get("current_sprint_number")
        if not raw_num:
            logger.warning(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: current_sprint_number not "
                "set in project data — falling back to full sprint re-run: project=%s",
                project_id,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_IN_PROGRESS,
                success=True,
                message="SPRINT_BLOCKED fallback: current_sprint_number unknown",
                completed_stages=list(data.get("stages_completed", [])),
            )

        try:
            blocked_num = int(raw_num)
        except (TypeError, ValueError):
            logger.warning(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: invalid "
                "current_sprint_number=%r — falling back to full sprint re-run: project=%s",
                raw_num, project_id,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_IN_PROGRESS,
                success=True,
                message="SPRINT_BLOCKED fallback: invalid current_sprint_number",
                completed_stages=list(data.get("stages_completed", [])),
            )

        # ── Stale SPRINT_BLOCKED: sprint already in completed_sprints ────────
        if blocked_num in completed_sprints:
            logger.info(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: sprint %d already "
                "in completed_sprints — transitioning to SPRINT_IN_PROGRESS: project=%s",
                blocked_num, project_id,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_IN_PROGRESS,
                success=True,
                message=f"Sprint {blocked_num} already completed (stale SPRINT_BLOCKED)",
                completed_stages=list(data.get("stages_completed", [])),
            )

        blocked_sprint = next(
            (s for s in sprints_to_run if s.sprint_number == blocked_num),
            None,
        )
        if blocked_sprint is None:
            logger.warning(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: sprint %d not found "
                "in sprint plan — falling back to full sprint re-run: project=%s",
                blocked_num, project_id,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_IN_PROGRESS,
                success=True,
                message="SPRINT_BLOCKED fallback: blocked sprint not found in plan",
                completed_stages=list(data.get("stages_completed", [])),
            )

        # ── Retry sandbox only ───────────────────────────────────────────────
        logger.info(
            "[PipelineSupervisor] SPRINT_BLOCKED resume: retrying only sandbox "
            "verification for sprint %d — skipping agent re-run: project=%s",
            blocked_num, project_id,
        )

        try:
            sandbox_result = self._code_sandbox.run(
                project_id,
                sprint=blocked_num,
                require_execution=True,
            )
        except Exception as exc:
            logger.error(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: sandbox raised: "
                "project=%s sprint=%d error=%s",
                project_id, blocked_num, exc,
                exc_info=True,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_BLOCKED)
            data = self.workspace.load_project_json(project_id) or {}
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_BLOCKED,
                success=False,
                message=f"Sprint {blocked_num} sandbox retry raised: {exc}",
                current_sprint=blocked_num,
                completed_stages=list(data.get("stages_completed", [])),
            )

        if not sandbox_result.build.success:
            errors = "; ".join(sandbox_result.build.errors[:3]) or "build failed"
            logger.error(
                "[PipelineSupervisor] SPRINT_BLOCKED resume: sandbox still failing "
                "for sprint %d: %s — project=%s",
                blocked_num, errors, project_id,
            )
            self.workspace.update_state(project_id, ProjectState.SPRINT_BLOCKED)
            self.workspace.update_project_json(
                project_id,
                {f"sprint_{blocked_num}_failure_reason": f"sandbox retry failed: {errors}"},
            )
            data = self.workspace.load_project_json(project_id) or {}
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.SPRINT_BLOCKED,
                success=False,
                message=f"Sprint {blocked_num} sandbox retry failed: {errors}",
                current_sprint=blocked_num,
                completed_stages=list(data.get("stages_completed", [])),
            )

        # ── Sandbox passed — mark sprint complete and run post-sprint steps ──
        logger.info(
            "[PipelineSupervisor] SPRINT_BLOCKED resume: sandbox retry passed for "
            "sprint %d — marking sprint complete: project=%s",
            blocked_num, project_id,
        )
        self.workspace.mark_sprint_complete(project_id, blocked_num)
        self.workspace.update_state(project_id, ProjectState.SPRINT_IN_PROGRESS)
        # Mirror the post-sprint steps from the successful path in _run_sprints().
        self._trigger_intelligence_index(project_id, sprint_number=blocked_num)
        self._pin_dependencies(project_id, sprint_number=blocked_num)
        self._run_sandbox(project_id, sprint_number=blocked_num)
        self._commit_sprint_to_git(project_id, blocked_num, blocked_sprint)
        self._start_preview(project_id, sprint_number=blocked_num)
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.SPRINT_IN_PROGRESS,
            success=True,
            message=f"Sprint {blocked_num} sandbox retry passed — sprint marked complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    # Maximum number of BugAnalyst-triggered code fixes before accepting the
    # result and advancing to DEPLOYABLE.  Prevents infinite fix loops when
    # the LLM oscillates or when tests are structurally incompatible with the
    # generated project (e.g. auth tests against a calculator app).
    _MAX_BUG_FIX_ITERATIONS = 2

    # Maximum number of spec_bug / architecture_bug rollbacks before giving up
    # and continuing to DEPLOYABLE.  Without this guard an unfixable architecture
    # defect (e.g. persistent schema parse failure) causes an infinite loop:
    # BugAnalyst → rollback → Architect re-runs → same defect → BugAnalyst → ...
    _MAX_ARCH_ROLLBACK_ITERATIONS = 2

    def _run_release(self, project_id: str, request: str) -> PipelineResult:
        """Run Release phase: Integration, QA, BugAnalyst, DevOps, Documentation, Retro.

        When BugAnalyst detects a code_bug it applies a targeted fix and
        restarts the release loop from QA (not from Integration).  A hard cap
        of _MAX_BUG_FIX_ITERATIONS prevents infinite oscillation.

        Non-fatal failures: if a stage fails, log WARNING but continue.
        Final state is DEPLOYABLE.
        """
        logger.info("[PipelineSupervisor] entering Release phase")
        quick_mode = self._get_project_mode(project_id) == "quick"
        if quick_mode:
            logger.info("[PipelineSupervisor] quick mode: skipping release stages %s", _QUICK_BUILD_SKIP_RELEASE)

        from .stage_lookup import resolve_stage_name

        bug_fix_iterations = 0
        arch_rollback_iterations = 0
        # Stages to restart from after a code_bug fix (skip Integration, re-run QA+)
        _POST_FIX_START = "qa"

        while True:
            # Reload completed stages at the start of each loop iteration so
            # that the idempotency check reflects fixes applied this iteration.
            data = self.workspace.load_project_json(project_id) or {}
            completed = set(data.get("stages_completed", []))

            restart_from_qa = False  # set True when a code_bug fix is applied

            for stage_key in get_release_stages():
                # R9: skip document/retro in quick mode
                if quick_mode and stage_key in _QUICK_BUILD_SKIP_RELEASE:
                    logger.info("[PipelineSupervisor] quick mode: skipping release stage %s", stage_key)
                    continue

                # After a code_bug fix, only re-run from QA onwards — Integration
                # result is still valid and re-running it wastes time.
                if restart_from_qa and stage_key not in self._release_stages_from("qa"):
                    continue

                # Idempotency: skip stages already completed in a previous run.
                stage_value = resolve_stage_name(stage_key)
                if stage_value in completed:
                    logger.info("[PipelineSupervisor] release stage %s already completed, skipping", stage_key)
                    continue

                logger.debug("[PipelineSupervisor] running release stage: %s", stage_key)
                result = self._run_stage_safe(project_id, stage_key, request)

                if stage_key == "qa" and self._blueprint_store is not None:
                    try:
                        outcome = "success" if result.success else "failed"
                        failure_reason = result.message if not result.success else None
                        self._blueprint_store.record_outcome(project_id, outcome, failure_reason)
                    except Exception as exc:
                        logger.warning(
                            "[PipelineSupervisor] blueprint outcome record failed (non-fatal): %s", exc,
                        )

                if not result.success:
                    logger.warning(
                        "[PipelineSupervisor] release stage %s failed (non-fatal): %s",
                        stage_key, result.message,
                    )
                else:
                    logger.info("[PipelineSupervisor] release stage %s complete", stage_key)

                    # Run sandbox after QA stage to execute newly generated test files.
                    if stage_key == "qa" and self._code_sandbox is not None:
                        logger.info("[PipelineSupervisor] Running sandbox with QA-generated test files: project=%s", project_id)
                        self._run_sandbox(project_id, sprint_number=0)

                    # R3: verify Dockerfile after DevOps stage
                    if stage_key in ("devops", "devops_developer") and self._code_sandbox is not None:
                        dockerfile_errors = self._code_sandbox.verify_dockerfile(project_id)
                        if dockerfile_errors:
                            logger.warning(
                                "[PipelineSupervisor] Dockerfile validation issues (non-fatal): project=%s errors=%s",
                                project_id, dockerfile_errors,
                            )
                        else:
                            logger.info("[PipelineSupervisor] Dockerfile validation passed: project=%s", project_id)

                    if stage_key == "bug_analyst" and hasattr(result, "artifact") and result.artifact:
                        structured = result.artifact.structured_content or {}
                        bug_type = structured.get("type")

                        if bug_type in ("spec_bug", "architecture_bug"):
                            logger.info("[PipelineSupervisor] BugAnalyst detected %s, rolling back pipeline", bug_type)
                            if arch_rollback_iterations >= self._MAX_ARCH_ROLLBACK_ITERATIONS:
                                logger.warning(
                                    "[PipelineSupervisor] BugAnalyst %s rollback limit reached "
                                    "(%d/%d) — skipping rollback and advancing to DEPLOYABLE. "
                                    "project=%s bug=%s",
                                    bug_type,
                                    arch_rollback_iterations,
                                    self._MAX_ARCH_ROLLBACK_ITERATIONS,
                                    project_id,
                                    structured.get("targeted_fix_instruction", ""),
                                )
                                # Do not roll back — fall through so the release loop
                                # finishes naturally (DevOps, Docs, Retro) and reaches DEPLOYABLE.
                            else:
                                arch_rollback_iterations += 1
                                if self._change_manager is not None:
                                    change = self._change_manager.submit(
                                        project_id=project_id,
                                        change_description=(
                                            f"BugAnalyst detected {bug_type}: "
                                            f"{structured.get('targeted_fix_instruction', structured.get('fix_instruction'))}"
                                        ),
                                    )
                                    self._change_manager.apply(
                                        project_id=project_id,
                                        change_id=change.change_id,
                                        confirmed=True,
                                    )
                                else:
                                    raise RuntimeError(
                                        "ChangeManager not injected — cannot perform rollback. "
                                        "Wire ChangeManager in PipelineSupervisor."
                                    )
                                return PipelineResult(
                                    project_id=project_id,
                                    state=ProjectState.RESUMING_FROM_CHANGE,
                                    success=True,
                                    message=f"Rollback triggered due to {bug_type}",
                                    completed_stages=[],
                                )

                        elif bug_type == "code_bug":
                            if bug_fix_iterations >= self._MAX_BUG_FIX_ITERATIONS:
                                logger.warning(
                                    "[PipelineSupervisor] BugAnalyst code_bug fix limit reached "
                                    "(%d/%d): project=%s",
                                    bug_fix_iterations, self._MAX_BUG_FIX_ITERATIONS, project_id,
                                )
                                # AC-P2-10: if the build is still failing at the limit,
                                # do NOT advance to DEPLOYABLE — transition to SPRINT_BLOCKED.
                                _failure_reason = self._check_build_state_from_memory(project_id)
                                if _failure_reason:
                                    logger.error(
                                        "[PipelineSupervisor] bug-fix limit exhausted with "
                                        "build still failing — transitioning to SPRINT_BLOCKED. "
                                        "project=%s reason=%s",
                                        project_id, _failure_reason,
                                    )
                                    self.workspace.update_state(
                                        project_id, ProjectState.SPRINT_BLOCKED,
                                    )
                                    self.workspace.update_project_json(
                                        project_id,
                                        {"bug_fix_failure_reason": _failure_reason},
                                    )
                                    _data = self.workspace.load_project_json(project_id) or {}
                                    return PipelineResult(
                                        project_id=project_id,
                                        state=ProjectState.SPRINT_BLOCKED,
                                        success=False,
                                        message=(
                                            f"Bug-fix limit ({self._MAX_BUG_FIX_ITERATIONS}) exhausted "
                                            f"with build still failing: {_failure_reason}"
                                        ),
                                        completed_stages=list(
                                            _data.get("stages_completed", [])
                                        ),
                                    )
                                # Build is passing — fall through so the release loop finishes
                                # naturally (DevOps, Docs, Retro) and reaches DEPLOYABLE.
                            else:
                                bug_fix_iterations += 1
                                affected = structured.get("affected_agent", "Backend")
                                target_stage = "backend" if affected.lower() == "backend" else "frontend"
                                fix = structured.get("targeted_fix_instruction", "")
                                logger.info(
                                    "[PipelineSupervisor] BugAnalyst code_bug fix %d/%d: stage=%s project=%s",
                                    bug_fix_iterations, self._MAX_BUG_FIX_ITERATIONS, target_stage, project_id,
                                )
                                fix_content = f"A bug was found. Your task is to apply the following fix: {fix}"
                                from .stage_lookup import resolve_stage_name as _resolve
                                self.engine.run(project_id, _resolve(target_stage), fix_content)

                                # AC-08: After the fix, re-run the sandbox so BugAnalyst's
                                # next iteration sees actual results for the patched code, not
                                # stale pre-fix results.  Non-blocking — failure is logged.
                                try:
                                    data_for_sprint = self.workspace.load_project_json(project_id) or {}
                                    current_sprint = int(data_for_sprint.get("current_sprint_number", 0))
                                    if self._code_sandbox is not None and current_sprint > 0:
                                        logger.info(
                                            "[PipelineSupervisor] re-running sandbox after bug fix %d/%d: "
                                            "project=%s sprint=%d",
                                            bug_fix_iterations, self._MAX_BUG_FIX_ITERATIONS,
                                            project_id, current_sprint,
                                        )
                                        fresh_result = self._code_sandbox.run(
                                            project_id,
                                            sprint=current_sprint,
                                            require_execution=True,
                                        )
                                        if self._memory_manager is not None:
                                            self._memory_manager.store(
                                                project_id, "sandbox:latest", fresh_result.to_json(),
                                            )
                                        # Also update ArtifactStore so the fresh result is persistent.
                                        store = self.workspace.get_artifact_store(project_id)
                                        store.write(
                                            scope=f"sprint_{current_sprint}",
                                            name=f"sandbox_result_fix_{bug_fix_iterations}",
                                            data=fresh_result._to_dict(),
                                        )
                                        logger.info(
                                            "[PipelineSupervisor] post-fix sandbox: build=%s tests=%d/%d",
                                            fresh_result.build.success,
                                            fresh_result.test.passed,
                                            fresh_result.test.total,
                                        )
                                except Exception as sandbox_exc:
                                    logger.warning(
                                        "[PipelineSupervisor] post-fix sandbox re-run failed (non-fatal): %s",
                                        sandbox_exc,
                                    )

                                # Clear only QA and BugAnalyst from completed so they re-run.
                                # Integration result is still valid — leave it in completed.
                                data = self.workspace.load_project_json(project_id) or {}
                                existing = list(data.get("stages_completed", []))
                                qa_and_after = {
                                    resolve_stage_name(s)
                                    for s in get_release_stages()
                                    if s in self._release_stages_from("qa")
                                }
                                new_completed = [s for s in existing if s not in qa_and_after]
                                self.workspace.update_project_json(project_id, {"stages_completed": new_completed})

                                # Restart the inner for-loop from QA
                                restart_from_qa = True
                                break  # break for-loop → while continues

            else:
                # for-loop completed without a break — all release stages done
                break
            # while continues only when restart_from_qa caused a break

        logger.info("[PipelineSupervisor] Release phase complete, marking DEPLOYABLE")
        self.workspace.update_state(project_id, ProjectState.DEPLOYABLE)
        
        # Append WORKFLOW_COMPLETED event (dual-write)
        if self._events:
            self._events.append(
                workflow_id=project_id,
                event_type="workflow.completed",
                actor="engine",
                trace_id=None,
            )
        
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.DEPLOYABLE,
            success=True,
            message="Release phase complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _check_build_state_from_memory(self, project_id: str) -> str:
        """AC-P2-10: Return a failure reason string if the latest sandbox build is
        still failing, or an empty string if the build is passing (or unknown).

        Reads from memory_manager at "sandbox:latest" — the key written by
        both _run_sandbox() (post-sprint) and the post-fix sandbox re-run.

        Returns
        -------
        str
            Non-empty if build is broken (message describes the failure).
            Empty string if build is passing or if no sandbox result is available
            (no evidence of failure → give benefit of the doubt).
        """
        if self._memory_manager is None or self._code_sandbox is None:
            # No sandbox wired — we cannot verify, assume passing for backward compat.
            return ""
        try:
            import json as _json
            from ..shared.dto.sandbox_result import SandboxResult
            raw = self._memory_manager.load(project_id, "sandbox:latest")
            if not raw:
                return ""
            data = _json.loads(raw) if isinstance(raw, str) else raw
            result = SandboxResult.from_dict(data)
            if not result.build.success:
                errors = "; ".join(result.build.errors[:3]) or "build error"
                return f"build failed: {errors}"
            if result.test.failed > 0 and result.test.total > 0:
                return (
                    f"tests failing: {result.test.failed}/{result.test.total} failed"
                )
            return ""
        except Exception as exc:
            logger.warning(
                "[PipelineSupervisor] _check_build_state_from_memory error "
                "(treating as passing): project=%s error=%s",
                project_id, exc,
            )
            return ""

    def _start_preview(self, project_id: str, sprint_number: int = 0) -> None:
        """R5: Start or restart the live preview after a sprint sandbox passes.

        Only activates when PREVIEW_ENABLED=true. Reads the sandbox result to
        check that the build succeeded before launching the preview subprocess.
        Non-blocking — any exception is caught and logged.
        """
        if self._preview_manager is None:
            return
        try:
            # Only start if build was successful (R2 gate)
            memory_manager = self._memory_manager
            if memory_manager is not None:
                import json as _json
                raw = memory_manager.load(project_id, "sandbox:latest")
                if raw:
                    data = _json.loads(raw) if isinstance(raw, str) else raw
                    build_ok = data.get("build", {}).get("success", True)
                    if not build_ok:
                        logger.info(
                            "[PipelineSupervisor] preview skipped — build failed: project=%s sprint=%d",
                            project_id, sprint_number,
                        )
                        return
                    stack = data.get("stack", "python")
                else:
                    stack = "python"  # default assumption
            else:
                stack = "python"

            workspace_path = self.workspace.get_workspace_path(project_id)
            project_dir = workspace_path / "project"
            if not project_dir.exists():
                project_dir = workspace_path

            port = self._preview_manager.start(project_id, project_dir, stack)
            if port is not None:
                logger.info(
                    "[PipelineSupervisor] preview started: project=%s sprint=%d port=%d",
                    project_id, sprint_number, port,
                )
                # Store port in memory so UI/API can look it up
                if memory_manager is not None:
                    memory_manager.store(project_id, "preview:port", str(port))
        except Exception as exc:
            logger.warning(
                "[PipelineSupervisor] preview start failed (non-fatal): project=%s sprint=%d error=%s",
                project_id, sprint_number, exc,
            )

    def _commit_sprint_to_git(self, project_id: str, sprint_number: int, sprint: object) -> None:
        """R4: Commit all sprint-generated files to the workspace git repository.

        Non-blocking — any exception is caught and logged; git errors never stop the pipeline.
        """
        try:
            from ..workspace.git_manager import GitManager
            workspace_path = self.workspace.get_workspace_path(project_id)
            git = GitManager(workspace_path)
            # Collect written files from sprint object if available
            files_written: list[str] = []
            if hasattr(sprint, "files") and sprint.files:
                files_written = [f.path if hasattr(f, "path") else str(f) for f in sprint.files]
            summary_name = getattr(sprint, "name", "") or f"Sprint {sprint_number}"
            commit_hash = git.commit_sprint(sprint_number, summary_name, files_written)
            if commit_hash:
                logger.info(
                    "[PipelineSupervisor] sprint %d git commit: %s project=%s",
                    sprint_number, commit_hash, project_id,
                )
        except Exception as exc:
            logger.warning(
                "[PipelineSupervisor] git commit_sprint failed (non-fatal): project=%s sprint=%d error=%s",
                project_id, sprint_number, exc,
            )

    def _pin_dependencies(self, project_id: str, sprint_number: int = 0) -> None:
        """Pin requirements.txt and package.json to exact stable versions.

        R2: Called after sprint syntax check passes and before sandbox run.
        Non-blocking — any exception is caught and logged. Uses DependencyPinner
        which caches resolved versions in-process to avoid repeated API calls.
        """
        if self._dependency_pinner is None:
            return
        try:
            workspace_path = self.workspace.get_workspace_path(project_id)
            project_dir = workspace_path / "project"
            if not project_dir.exists():
                project_dir = workspace_path

            pinned_total = 0
            for req_file in project_dir.rglob("requirements.txt"):
                if "node_modules" in str(req_file):
                    continue
                pinned_total += self._dependency_pinner.pin_requirements(req_file)

            for pkg_file in project_dir.rglob("package.json"):
                if "node_modules" in str(pkg_file):
                    continue
                pinned_total += self._dependency_pinner.pin_package_json(pkg_file)

            if pinned_total > 0:
                logger.info(
                    "[PipelineSupervisor] pinned %d dependency spec(s): project=%s sprint=%d",
                    pinned_total, project_id, sprint_number,
                )
        except Exception as exc:
            logger.warning(
                "[PipelineSupervisor] dependency pinning failed (non-fatal): project=%s sprint=%d error=%s",
                project_id, sprint_number, exc,
            )

    def _trigger_intelligence_index(self, project_id: str, sprint_number: int = 0) -> None:
        """Trigger the intelligence layer after a sprint completes.

        Calls FileIndexer, ProjectDependencyGraph, and CodeSummarizer in order:
          1. file_indexer.index_project() — walks the workspace and indexes every
             source file into SQLite so subsequent queries are up to date.
          2. dependency_graph.build() — (re-)builds the reverse dep graph from
             the freshly indexed data.
          3. code_summarizer.build_project_overview() — pre-computes the project
             overview so ContextOrchestrator can serve it without an extra query.

        Non-blocking: the entire block is wrapped in try/except — any failure is
        logged as WARNING and never propagates to the sprint loop.  Each
        component is only called when it was wired into the constructor.
        """
        if self._file_indexer is None:
            return
        try:
            workspace_path = self.workspace.get_workspace_path(project_id)
            self._file_indexer.index_project(project_id, str(workspace_path), sprint_number)
            if self._dependency_graph is not None:
                self._dependency_graph.build(project_id)
            if self._code_summarizer is not None:
                self._code_summarizer.build_project_overview(project_id)
            logger.info(
                "intelligence layer updated: project_id=%s sprint=%d",
                project_id, sprint_number,
            )
        except Exception as exc:
            logger.warning(
                "intelligence layer update failed: %s — continuing",
                exc,
            )

    def _run_sandbox(self, project_id: str, sprint_number: int = 0) -> None:
        """Load or run the code execution sandbox result after a sprint completes.

        Phase 1: SprintExecutor already runs the sandbox (install → build → test)
        and persists the result to ArtifactStore at sprint_N/sandbox_result.
        This method first checks whether that result exists; if so, it loads it
        instead of re-running to avoid double execution.  If SprintExecutor did
        not run the sandbox (backward compat when code_sandbox is not wired to
        SprintExecutor), falls back to running it fresh here.

        Either way, the result is stored in memory_manager at "sandbox:latest"
        so BugAnalyst can read it in the Release phase and _start_preview() can
        check build success.

        Non-blocking — exceptions are caught and logged.
        """
        if self._code_sandbox is None:
            return
        try:
            from ..shared.dto.sandbox_result import SandboxResult

            # ── Try to load the already-persisted result from SprintExecutor ──
            sandbox_result: SandboxResult | None = None
            try:
                store = self.workspace.get_artifact_store(project_id)
                if store.exists(f"sprint_{sprint_number}", "sandbox_result"):
                    data = store.read(f"sprint_{sprint_number}", "sandbox_result")
                    if data:
                        sandbox_result = SandboxResult.from_dict(data)
                        logger.info(
                            "[PipelineSupervisor] sandbox result loaded from ArtifactStore "
                            "(no re-run): project=%s sprint=%d build=%s",
                            project_id, sprint_number, sandbox_result.build.success,
                        )
            except Exception as load_exc:
                logger.debug(
                    "[PipelineSupervisor] could not load persisted sandbox result: %s", load_exc,
                )

            # ── Fall back to running fresh if not already persisted ──────────
            if sandbox_result is None:
                sandbox_result = self._code_sandbox.run(project_id, sprint=sprint_number)
                logger.info(
                    "[PipelineSupervisor] sandbox ran fresh: project=%s sprint=%d build=%s",
                    project_id, sprint_number, sandbox_result.build.success,
                )

            # ── Store in memory for BugAnalyst + _start_preview ───────────────
            memory_manager = self._memory_manager
            if memory_manager is not None:
                memory_manager.store(project_id, "sandbox:latest", sandbox_result.to_json())
                logger.info(
                    "[PipelineSupervisor] sandbox results in memory: project=%s sprint=%d "
                    "install=%s lint=%d test=%d/%d build=%s",
                    project_id, sprint_number,
                    sandbox_result.install.success,
                    sandbox_result.lint.error_count,
                    sandbox_result.test.passed, sandbox_result.test.total,
                    sandbox_result.build.success,
                )
            else:
                logger.debug(
                    "[PipelineSupervisor] sandbox result not persisted to memory "
                    "(memory_manager not wired): project=%s sprint=%d", project_id, sprint_number,
                )
        except Exception as exc:
            logger.warning(
                "[PipelineSupervisor] sandbox step failed (non-fatal): project=%s sprint=%d error=%s",
                project_id, sprint_number, exc,
            )

    def _run_stage_safe(
        self,
        project_id: str,
        stage_key: str,
        request: str,
    ) -> WorkflowResult | _StageResult:
        """Wrap engine.run() with exception handling."""
        try:
            from .stage_lookup import resolve_stage_name
            resolved_stage = resolve_stage_name(stage_key)
            result: WorkflowResult = self.engine.run(project_id, resolved_stage, request)
            if result.success:
                logger.debug(
                    "[PipelineSupervisor] stage %s succeeded",
                    stage_key,
                )
                return result
            else:
                logger.warning(
                    "[PipelineSupervisor] stage %s failed: %s",
                    stage_key, result.message,
                )
                return result
        except Exception as exc:
            logger.error(
                "[PipelineSupervisor] stage %s raised exception: %s",
                stage_key, exc,
                exc_info=True,
            )
            return _StageResult(
                success=False,
                message=f"{type(exc).__name__}: {exc}",
            )
    @staticmethod
    def _release_stages_from(start_key: str) -> set[str]:
        """Return the set of release stage keys at and after start_key.

        Used by the BugAnalyst code_bug handler to determine which stages
        must be re-run after a targeted fix (everything from QA onwards)
        versus which stages can be skipped (Integration, which runs before QA).
        """
        stages = get_release_stages()
        try:
            idx = stages.index(start_key)
            return set(stages[idx:])
        except ValueError:
            # start_key not found — return everything (safe fallback)
            return set(stages)

    # End of PipelineSupervisor
