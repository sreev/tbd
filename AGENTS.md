# Repository Guidelines

## Project Structure & Module Organization

This repository is currently an empty scaffold: there are no source files, tests, assets, or build configuration yet. Keep new code in clearly named, purpose-specific directories (for example, `src/`, `tests/`, and `assets/`) and add project-specific structure here as it is established. Avoid placing generated output or local environment files in source directories.

## Build, Test, and Development Commands

No build, test, or local development commands are configured yet. When adding a toolchain, document its setup and canonical commands in this section (and in the relevant package or project manifest). Prefer reproducible commands that work from the repository root.

## Coding Style & Naming Conventions

There is no language-specific style configuration yet. Follow the conventions of the chosen language and add formatter or linter configuration alongside the initial implementation. Use descriptive, consistent names; keep filenames lowercase and use the standard convention for the language (for example, `snake_case.py` for Python modules or `kebab-case.ts` for TypeScript files). Keep changes focused and avoid committing generated or machine-specific files.

## Testing Guidelines

No test framework or coverage requirement is configured. Add tests with new behavior, keep them in a dedicated test directory or beside the code according to the selected framework, and use names that identify the behavior under test. Document how to run the test suite when it is introduced.

## Commit & Pull Request Guidelines

There is no commit history yet, so repository-specific commit conventions cannot be inferred. Use short, imperative commit subjects (for example, `Add input validation`) and keep each commit focused. Pull requests should summarize the change, explain how it was checked, link related issues when applicable, and include screenshots for user-facing visual changes.

## Security & Configuration

Keep credentials, tokens, and machine-specific settings out of version control. Provide safe examples or placeholders for required configuration, and document setup without embedding secrets.
