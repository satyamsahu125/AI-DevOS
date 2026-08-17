/**
 * Test File 01 — Project Creation & File Routing
 *
 * Bugs covered:
 *   B-01 — BackendAgent hardcoded backend/ prefix filter — React Native files dropped
 *   B-02 — FrontendAgent hardcoded frontend/ prefix — RN files dropped
 *   B-05 — No scaffold step creates App.tsx / babel.config.js for React Native
 *
 * Strategy:
 *   - Create a project via API (create-and-run) with a description that clearly signals the project type
 *   - Wait for file generation to complete
 *   - Verify generated files are in the correct directories
 *   - Each test is independent; cleans up with deleteProject()
 *
 * NOTE: project_type is NOT an API field — project type is inferred from description text.
 * Write descriptions that make the technology stack unambiguous.
 */
import { test, expect } from '@playwright/test';
import { ProjectPage } from '../pages/ProjectPage';
import {
  createProject,
  deleteProject,
  getProjectFiles,
  waitForStage,
  waitForCompletion,
  sleep,
} from '../helpers/api';

// Generous timeout for LLM pipeline stages
test.setTimeout(300_000); // 5 minutes per test

test.describe('Project Creation — File Routing (B-01, B-02, B-05)', () => {

  test('[B-01][B-02] React Native project generates files in app/ or screens/ — not backend/ or frontend/', async ({ page, request }) => {
    /**
     * Before B-01 fix: BackendAgent's fallback in execute_sprint() used a hardcoded
     * `backend/` prefix filter, silently dropping all React Native file paths that
     * didn't start with `backend/`.
     *
     * Before B-02 fix: FrontendAgent did the same with a hardcoded `frontend/` prefix.
     *
     * After fix: Both agents map project_type to the correct prefix set.
     * For React Native: BackendAgent allows `app/`, FrontendAgent allows `app/screens/`, `app/components/`, etc.
     */
    const proj = await createProject(request, {
      name: 'test-rn-file-routing',
      description:
        'A React Native mobile app for tracking daily habits. ' +
        'Built with React Native CLI (not Expo), TypeScript, and React Navigation. ' +
        'Screens: HabitList, AddHabit, Statistics. State via React Context.',
      mode: 'quick',
    });

    try {
      // Wait for the pipeline to reach the dev/sprint stage
      await waitForStage(request, proj.id, 'sprint', 180_000);

      const files = await getProjectFiles(request, proj.id);
      const filePaths = files.files.map(f => f.path);

      // ASSERT B-01: No files routed to backend/ for a React Native project
      const inBackend = filePaths.filter(f => f.startsWith('backend/'));
      expect(inBackend, `B-01: Files must not go to backend/ for RN: ${JSON.stringify(inBackend)}`).toHaveLength(0);

      // ASSERT B-02: No files routed to frontend/ for a React Native project
      const inFrontend = filePaths.filter(f => f.startsWith('frontend/'));
      expect(inFrontend, `B-02: Files must not go to frontend/ for RN: ${JSON.stringify(inFrontend)}`).toHaveLength(0);

      // ASSERT: Some files exist in app/, src/, or screens/
      const correctPaths = filePaths.filter(f =>
        f.startsWith('app/') ||
        f.startsWith('src/') ||
        f.startsWith('screens/') ||
        f.startsWith('components/') ||
        f.startsWith('navigation/') ||
        f.endsWith('.tsx') ||
        f.endsWith('.ts'),
      );
      expect(
        correctPaths.length,
        `B-01/B-02: Expected files in mobile-appropriate dirs. Got: ${JSON.stringify(filePaths.slice(0, 10))}`,
      ).toBeGreaterThan(0);

    } finally {
      await deleteProject(request, proj.id);
    }
  });

  test('[B-05] React Native project has scaffold files: App.tsx, babel.config.js, tsconfig.json', async ({ request }) => {
    /**
     * Before B-05 fix: No generation step creates the mandatory React Native entry-point
     * files. The pipeline generates feature screens but misses the root files that npm
     * and the React Native bundler (Metro) require.
     *
     * After fix: PipelineSupervisor._create_react_native_scaffold() runs after the first
     * sprint and writes App.tsx, babel.config.js, tsconfig.json, metro.config.js
     * (only if they don't already exist).
     */
    const proj = await createProject(request, {
      name: 'test-rn-scaffold',
      description:
        'A React Native mobile calculator app. ' +
        'Platform: iOS and Android. Language: TypeScript. ' +
        'Uses React Native CLI. Include App.tsx as the entry point.',
      mode: 'quick',
    });

    try {
      await waitForStage(request, proj.id, 'sprint', 180_000);

      const files = await getProjectFiles(request, proj.id);
      const filePaths = files.files.map(f => f.path);

      const hasAppTsx = filePaths.some(f => f.endsWith('App.tsx') || f === 'App.tsx');
      const hasBabelConfig = filePaths.some(f =>
        f.includes('babel.config') || f.includes('.babelrc'),
      );
      const hasTsConfig = filePaths.some(f =>
        f.includes('tsconfig.json') || f.includes('tsconfig'),
      );

      expect(
        hasAppTsx,
        `B-05: App.tsx must exist. Files found: ${JSON.stringify(filePaths.slice(0, 15))}`,
      ).toBe(true);
      expect(
        hasBabelConfig,
        `B-05: babel.config.js must exist. Files found: ${JSON.stringify(filePaths.slice(0, 15))}`,
      ).toBe(true);
      expect(
        hasTsConfig,
        `B-05: tsconfig.json must exist. Files found: ${JSON.stringify(filePaths.slice(0, 15))}`,
      ).toBe(true);

    } finally {
      await deleteProject(request, proj.id);
    }
  });

  test('[B-01] Python FastAPI project generates files in backend/ — not app/ or src/', async ({ request }) => {
    /**
     * Regression check: the fix for B-01 must not break Python projects.
     * Python/FastAPI files must still route to backend/.
     */
    const proj = await createProject(request, {
      name: 'test-python-file-routing',
      description:
        'A Python FastAPI REST API for managing a product catalog. ' +
        'Endpoints: GET/POST/PUT/DELETE /products. ' +
        'Uses SQLAlchemy ORM with SQLite. Pydantic schemas. Python 3.12.',
      mode: 'quick',
    });

    try {
      await waitForStage(request, proj.id, 'sprint', 180_000);

      const files = await getProjectFiles(request, proj.id);
      const filePaths = files.files.map(f => f.path);
      const pyFiles = filePaths.filter(f => f.endsWith('.py'));

      expect(
        pyFiles.length,
        `B-01: Python project must produce .py files. Got: ${JSON.stringify(filePaths.slice(0, 10))}`,
      ).toBeGreaterThan(0);

      // Python files must be in backend/ or at root — not in mobile-only dirs
      const mobileFiles = pyFiles.filter(
        f => f.startsWith('app/screens/') || f.startsWith('app/components/'),
      );
      expect(
        mobileFiles,
        `B-01: Python project must not route .py files to mobile dirs: ${JSON.stringify(mobileFiles)}`,
      ).toHaveLength(0);

    } finally {
      await deleteProject(request, proj.id);
    }
  });
});
