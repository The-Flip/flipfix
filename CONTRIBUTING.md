# Contributing

This guide covers how to contribute to the project and submit a PR.

## Getting Started

- Get your environment configured in [README.md](README.md)
- Understand developing conventions in [docs/README.md](docs/README.md)

## Workflow

- **Create a branch** (e.g., `feature/new-icons`, `fix/login-bug`, `docs/api-guide`)
- **Make your changes & tests**

```bash
make quality     # Format, lint, check Python types
make test        # Run test suite
```

- **Commit changes** (pre-commit hooks automatically run formatting, linting, and security checks)
- **Push branch to GitHub**
- **Create a Pull Request** against `main`
- **Wait for CI checks**. GitHub Actions will automatically run tests, linting, type checking, etc
- **Merge when ready**. You can self-merge PR once CI passes
