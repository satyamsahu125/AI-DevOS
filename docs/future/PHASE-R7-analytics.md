# Phase R7 — Analytics Dashboard

**Timeline:** Week 9–10  
**Depends on:** R1 complete (LearningLoop and LessonStore wired and recording data)  
**Problem:** CostTracker records every LLM call. LearningLoop records every approved trajectory. LessonStore records every rejection lesson. None of this is visible anywhere in the UI.  
**Outcome:** An Analytics page surfaces cost by project/stage, stage success rates, and learning insights. Data is already being collected — this is pure UI + API work.

---

## Why This Matters

AI DevOS has rich telemetry already built and recording:
- `CostTracker` — token count, latency, cost per call
- `LearningLoop` — trajectory (stage, approved, retry_count, agent_model, latency_ms)
- `LessonStore` — rejection lessons (stage, what_failed, reviewer_said, retry_count)
- `PromptQualityAnalyzer` — prompt quality scores per stage
- `PerformanceScorer` — per-stage performance scores

None of this is surfaced to the user. An analytics dashboard costs a few days of UI + API work and turns AI DevOS from a black box into a transparent, data-driven system.

---

## New API Endpoints

### GET /analytics/overview
```json
{
  "total_projects": 12,
  "total_pipeline_runs": 38,
  "total_tokens_used": 4823400,
  "total_cost_usd": 14.83,
  "avg_tokens_per_project": 401950,
  "most_expensive_stage": "BackendDeveloper",
  "stage_success_rates": {
    "Architect": 0.92,
    "Designer": 0.88,
    "BackendDeveloper": 0.74,
    "QA": 0.81
  }
}
```

### GET /analytics/projects/{id}
Per-project breakdown: cost by stage, stage completion times, retry counts.

### GET /analytics/stage/{stage_name}
```json
{
  "stage": "BackendDeveloper",
  "total_runs": 45,
  "approval_rate": 0.74,
  "avg_retry_count": 1.3,
  "common_failures": ["missing import", "undefined variable", "wrong return type"],
  "avg_tokens": 8400,
  "avg_latency_ms": 12400
}
```

### GET /analytics/learning
Returns aggregated lessons from LessonStore — patterns across all projects:
```json
{
  "total_lessons": 127,
  "by_stage": {
    "BackendDeveloper": {
      "lesson_count": 34,
      "top_failures": ["missing import for {module}", "undefined variable {var}"]
    }
  }
}
```

---

## UI: Analytics Page

**Route:** `/analytics`

**Sections:**

### System Overview (top cards)
- Total cost this month
- Total projects
- Average cost per project
- Most-used model

### Cost by Stage (bar chart)
Horizontal bar chart: stage name → average token cost. Uses CostTracker data.

### Stage Success Rates (heat map or table)
Grid of stages × (approval_rate, avg_retries, avg_latency). Color-coded: green = high approval, red = low approval.

### Context Window Usage
Per-project gauge: tokens used / provider limit. Alert icon when > 75%.

### Learning Insights
Top 5 lessons from LessonStore: what stages fail most, what feedback patterns trigger most retries.

---

## Context Window Warning

This is important enough to implement in R7 rather than waiting for R9.

**File:** `backend/app/workflow/engine.py`

Track cumulative tokens per project run. When crossing 75% of the provider's context limit:
```python
limit = self._llm.context_limit()  # provider-specific: 200K for Claude, 128K for GPT-4
used = self._cost_tracker.total_tokens_for_run(project_id, run_id)
if used / limit > 0.75:
    self._event_broadcaster.broadcast(project_id, {
        "type": "context_warning",
        "used_tokens": used,
        "limit": limit,
        "pct": round(used / limit * 100),
        "message": f"Context window {round(used/limit*100)}% full. Consider completing remaining work in fewer stages."
    })
```

**UI:** Show a yellow warning banner in WorkspacePage when a context_warning event arrives via WebSocket.

---

## Exit Criteria

- [ ] `GET /analytics/overview` returns real data (not zeros) after 3+ pipeline runs
- [ ] `GET /analytics/stage/BackendDeveloper` returns approval_rate computed from LearningLoop data
- [ ] Analytics page visible in frontend with cost bar chart
- [ ] Stage success rate table shows at least 5 stages with real data
- [ ] Context window warning appears in UI (yellow banner) when project exceeds 75% of provider token limit
- [ ] All R1–R6 exit criteria still passing
