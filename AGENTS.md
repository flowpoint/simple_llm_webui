# Repository Guidelines

## Project Structure & Module Organization
The repository is intentionally lean; place all UI code in `src/` and organize by feature (`src/features/chat`, `src/features/auth`). Keep shared UI primitives in `src/components`, hooks in `src/hooks`, utilities in `src/lib`, and state containers in `src/stores`. Co-locate CSS modules with components or add shared styles to `src/styles`. Put integration and smoke tests in `tests/`, while static assets live in `public/` for bundler access.

## Build, Test, and Development Commands
- `npm install` – install or refresh dependencies.
- `npm run dev` – start the local dev server with hot reload.
- `npm run build` – compile an optimized production bundle.
- `npm run lint` – apply ESLint + Prettier rules across the codebase.
- `npm run test` – run the automated unit and component suite.

## Coding Style & Naming Conventions
Prefer TypeScript for new modules. Use two-space indentation, trailing commas, and double quotes to satisfy lint settings. Name React components, classes, and Zustand stores in PascalCase; keep functions, hooks, and variables in camelCase; reserve SCREAMING_SNAKE_CASE for environment keys. Prefer pure functional components, avoid default exports, and leave concise comments only for non-obvious behavior. Run `npm run lint` before committing to prevent style-only review cycles.

## Testing Guidelines
Use Vitest with Testing Library for unit and component coverage. Co-locate fast specs in a `__tests__` directory or suffix files with `.spec.tsx` (for example, `Button.spec.tsx`). Place MSW handlers and fixtures in `tests/mocks`. Each feature PR should add a happy-path test and at least one guard-rail scenario. Maintain 80%+ statement coverage; if a gap is necessary, justify the exception in the PR.

## Commit & Pull Request Guidelines
Adopt Conventional Commits (`feat: add chat composer`) with subjects under 65 characters; elaborate in the body when behavior changes. Rebase or squash local history before requesting review. PRs must include a concise summary, testing notes (`npm run test`, `npm run lint`), linked issues (`Closes #123`), and UI captures when applicable. Flag reviewers early if shared modules or API contracts shift, and wait for green CI before merging.

## Environment & Configuration Tips
Target Node 20 via `nvm use` to align with the lockfile. Keep secrets in `.env.local` (git-ignored) and document new variables in the PR description. Do not commit production credentials; add required keys to the deployment pipeline or secret manager instead.
