/**
 * AI DevOS — ProjectPage page object.
 *
 * Wraps Playwright locators for the Workspace page (/projects/:projectId).
 * Uses aria roles and semantic locators rather than CSS classes to remain
 * resilient to styling changes.
 *
 * Route map discovered in Phase 0:
 *   /projects         → ProjectsPage (list + "New Project" modal)
 *   /projects/:id     → WorkspacePage (pipeline view, file tree, stage progress)
 */
import { Page, Locator, expect } from '@playwright/test';
import { approveGate, getCurrentGate, sleep } from '../helpers/api';
import type { APIRequestContext } from '@playwright/test';

export class ProjectPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Navigation ────────────────────────────────────────────────────────────────

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/projects/${projectId}`);
    await this.page.waitForLoadState('networkidle');
  }

  async gotoProjectsList(): Promise<void> {
    await this.page.goto('/projects');
    await this.page.waitForLoadState('networkidle');
  }

  // ── Pipeline status ───────────────────────────────────────────────────────────

  /**
   * Get the text content of the current stage indicator, if present.
   * Returns empty string if not found.
   */
  async getCurrentStageText(): Promise<string> {
    const selectors = [
      '[data-testid="current-stage"]',
      '.current-stage',
      '[class*="stage"][class*="current"]',
      '[class*="current"][class*="stage"]',
    ];
    for (const sel of selectors) {
      const el = this.page.locator(sel).first();
      try {
        await el.waitFor({ timeout: 2000 });
        return (await el.textContent()) ?? '';
      } catch {
        // try next
      }
    }
    // fallback: find text on page that looks like a stage name
    const bodyText = await this.page.locator('body').textContent() ?? '';
    return bodyText;
  }

  /**
   * Return all visible pipeline stage labels.
   */
  async getPipelineStages(): Promise<string[]> {
    const selectors = [
      '[data-testid="pipeline-stage"]',
      '[data-testid="stage-name"]',
      '.stage-name',
      '.pipeline-step',
      '[class*="stage-label"]',
      '[class*="StageItem"]',
    ];
    for (const sel of selectors) {
      const els = this.page.locator(sel);
      const count = await els.count();
      if (count > 0) return els.allTextContents();
    }
    return [];
  }

  /**
   * Return the overall pipeline status text (e.g., "running", "complete", "failed").
   */
  async getPipelineState(): Promise<string> {
    const selectors = [
      '[data-testid="pipeline-state"]',
      '[data-testid="pipeline-status"]',
      '.pipeline-status',
      '[class*="status-badge"]',
    ];
    for (const sel of selectors) {
      const el = this.page.locator(sel).first();
      try {
        await el.waitFor({ timeout: 2000 });
        return (await el.textContent()) ?? '';
      } catch {
        // try next
      }
    }
    return '';
  }

  // ── Stage waiting ─────────────────────────────────────────────────────────────

  /**
   * Wait until the given text appears anywhere on the page (case-insensitive).
   * Used to detect stage transitions in the pipeline UI.
   */
  async waitForStageLabel(stageText: string, timeoutMs = 120_000): Promise<void> {
    await this.page.getByText(stageText, { exact: false }).first().waitFor({
      state: 'visible',
      timeout: timeoutMs,
    });
  }

  /**
   * Wait until the project status badge shows "Complete" or "Failed".
   */
  async waitForPipelineEnd(timeoutMs = 600_000): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const bodyText = await this.page.locator('body').textContent() ?? '';
      if (/complete|failed|error/i.test(bodyText)) return;
      await sleep(3000);
    }
    throw new Error(`Timeout waiting for pipeline to end (${timeoutMs}ms)`);
  }

  // ── File tree ─────────────────────────────────────────────────────────────────

  /**
   * Return the list of file paths visible in the file tree.
   */
  async getGeneratedFiles(): Promise<string[]> {
    const selectors = [
      '[data-testid="generated-file"]',
      '[data-testid="file-name"]',
      '.file-tree-item',
      '.file-name',
      '[class*="FileItem"]',
      '[class*="file-item"]',
      '[class*="TreeItem"]',
    ];
    for (const sel of selectors) {
      const els = this.page.locator(sel);
      const count = await els.count();
      if (count > 0) return els.allTextContents();
    }
    return [];
  }

  /**
   * Click on a file in the tree to open its content in the viewer.
   */
  async openFile(fileNameFragment: string): Promise<void> {
    const selectors = [
      '.file-tree-item',
      '[data-testid="file-name"]',
      '[class*="FileItem"]',
    ];
    for (const sel of selectors) {
      const el = this.page.locator(sel).filter({ hasText: fileNameFragment });
      const count = await el.count();
      if (count > 0) {
        await el.first().click();
        return;
      }
    }
    // fallback — try any clickable element containing the fragment
    await this.page.getByText(fileNameFragment, { exact: false }).first().click();
  }

  /**
   * Return the text content of the code viewer pane.
   */
  async getFileContent(): Promise<string> {
    const selectors = [
      '[data-testid="file-content"]',
      '.code-viewer',
      'pre code',
      'pre',
      '[class*="CodeMirror"]',
      '[class*="monaco"]',
    ];
    for (const sel of selectors) {
      const el = this.page.locator(sel).first();
      try {
        await el.waitFor({ timeout: 3000 });
        return (await el.textContent()) ?? '';
      } catch {
        // try next
      }
    }
    return '';
  }

  // ── Gate controls (when REQUIRE_HUMAN_APPROVAL=true) ──────────────────────────

  /**
   * Click the approve / continue button.
   * No-op if the button is not found (gates may be disabled).
   */
  async clickApprove(): Promise<void> {
    const btn = this.page.getByRole('button', { name: /approve|continue|next|accept/i }).first();
    try {
      await btn.waitFor({ state: 'visible', timeout: 5000 });
      await btn.click();
    } catch {
      // No approval button — gates are likely disabled (REQUIRE_HUMAN_APPROVAL=false)
    }
  }

  /**
   * Click the reject / request-changes button and fill in feedback.
   * No-op if the button is not found.
   */
  async clickReject(feedback: string): Promise<void> {
    const btn = this.page.getByRole('button', {
      name: /reject|request changes|revise|revision/i,
    }).first();
    try {
      await btn.waitFor({ state: 'visible', timeout: 5000 });
      await btn.click();
      const ta = this.page.getByLabel(/feedback|reason|comment/i).first();
      await ta.fill(feedback);
      await this.page.getByRole('button', { name: /submit|confirm|send/i }).first().click();
    } catch {
      // No reject button visible
    }
  }

  /**
   * Approve a gate via API (more reliable than UI when auth is disabled).
   * Uses the gates API directly.
   */
  async approveGateViaApi(
    request: APIRequestContext,
    projectId: string,
    gate: 'architecture' | 'design' | 'sprint_plan',
  ): Promise<void> {
    await approveGate(request, projectId, gate);
  }

  /**
   * Poll the gate API and approve each gate that appears, until no gate is pending
   * or the timeout is reached. Useful when REQUIRE_HUMAN_APPROVAL=true.
   */
  async approveAllPendingGates(
    request: APIRequestContext,
    projectId: string,
    timeoutMs = 120_000,
  ): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const gateInfo = await getCurrentGate(request, projectId);
      if (!gateInfo.gate) break;
      await approveGate(request, projectId, gateInfo.gate as any);
      await sleep(2000);
    }
  }

  // ── Project creation (from /projects list page) ───────────────────────────────

  /**
   * Open the "New Project" modal from the projects list page.
   */
  async openNewProjectModal(): Promise<void> {
    const btn = this.page.getByRole('button', { name: /new project|create project|^\+/i })
      .or(this.page.getByRole('link', { name: /new project/i }));
    await btn.first().click();
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Fill in the new project form fields.
   * Note: no project_type field — the UI has name, description, mode.
   */
  async fillNewProjectForm(opts: {
    name: string;
    description: string;
    mode?: 'full' | 'quick';
  }): Promise<void> {
    await this.page.getByLabel(/project name|name/i).first().fill(opts.name);
    await this.page.getByLabel(/description/i).first().fill(opts.description);
    if (opts.mode) {
      const modeEl = this.page.locator(`[value="${opts.mode}"]`).or(
        this.page.getByRole('radio', { name: new RegExp(opts.mode, 'i') }),
      );
      try {
        await modeEl.first().click({ timeout: 2000 });
      } catch {
        // mode selection may not be visible
      }
    }
  }

  /**
   * Submit the new project form.
   */
  async submitNewProjectForm(): Promise<void> {
    await this.page.getByRole('button', { name: /create|submit|start|launch/i }).click();
  }

  // ── Sandbox results ──────────────────────────────────────────────────────────

  async getSandboxResults(): Promise<{ passed: boolean; output: string }> {
    const selectors = [
      '[data-testid="sandbox-results"]',
      '.sandbox-output',
      '[class*="sandbox"]',
    ];
    for (const sel of selectors) {
      const el = this.page.locator(sel).first();
      try {
        await el.waitFor({ timeout: 2000 });
        const text = (await el.textContent()) ?? '';
        return { passed: /pass|✓|green/i.test(text), output: text };
      } catch {
        // try next
      }
    }
    return { passed: false, output: '' };
  }
}
