# AI DevOS — New Frontend Product Specification

## 1. Product Purpose
AI DevOS is an AI-powered software development operating system.  
It orchestrates a multi-agent pipeline that takes a project description from concept to deployable code.  
The frontend is an engineering control surface — not a marketing site, not a generic dashboard.

## 2. Primary Users
- **Developers**: Running projects, reviewing artifacts, monitoring execution
- **Tech Leads**: Reviewing architecture gates, approving sprint plans
- **Admins**: Managing users and LLM configuration

## 3. Core Workflows (Backend-Verified)
1. Create Project → Full or Quick mode
2. Monitor Pipeline → WebSocket + REST polling
3. Human Gates → approve/revise Architecture, Sprint Plan
4. Design Review → inspect + approve/revise Designer stage output
5. QA Questionnaire → answer structured questions during Clarifying stage
6. View Artifacts → per-stage content
7. View Files → generated code browser
8. Chat with Project → AI assistant
9. Requirement Changes → submit + confirm/cancel mid-workflow
10. Analytics → usage overview, learning patterns
11. LLM Settings → configure provider/model/keys
12. User Admin → manage roles (admin only)

## 4. Verified API Capabilities
65+ endpoints covering: Projects, Workflow, Gates, Design Review, QA,
Changes, Artifacts, Files, Logs, Metrics/Cost, Memory, Chat,
Settings, Analytics, Auth, Admin, WebSocket

## 5. 20 Verified Pipeline Stages (from STAGES in api.ts)
DomainResearch, Clarifying, StrategicReview, ProductOwner, Architect,
Designer, Security, SprintPlanning, ScrumMaster, FileStructurePlanner,
BackendDeveloper, FrontendDeveloper, Integration, SprintDeploy, SprintReview,
QA, BugAnalyst, DevOps, Document, Retro

## 6. Design System
- Background: #0c0c0e
- Surface-1: #111115 (cards/panels)
- Surface-2: #18181c (elevated/hover)
- Border: rgba(255,255,255,0.07)
- Accent: #6366f1 (indigo)
- Text-primary: #f0f0f2
- Text-muted: #6b6b78
- Success: #22c55e | Warning: #f59e0b | Error: #ef4444
- Fonts: Inter (UI) + JetBrains Mono (code/data)

## 7. NOT IMPLEMENTED / UNSUPPORTED
- Per-template quality ranking (Phase C gate not reached)
- template_similarity_score (always NULL under Phase A)
- Real-time cost streaming (polling only)
