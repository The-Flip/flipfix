# Contributing

This guide covers how to contribute to the project and submit a PR.


## Getting Started

1. **Developer setup** - Follow [README.md](README.md) to get the app running locally (including development tools)
2. **Read the docs** - Review [docs/README.md](docs/README.md) to understand technical conventions

## Development Workflow

1. **Create a feature branch** (see [Branch Naming Convention](#branch-naming-convention) below)
2. **Make your changes** following the code quality guidelines
3. **Write tests** for new functionality
4. **Run tests** to ensure nothing breaks
5. **Commit your changes** with clear commit messages
6. **Push your branch** to GitHub
7. **Create a Pull Request** following the PR template

## Code Quality

### Code Quality Checks

**Before committing, run:**

```bash
# Check for linting issues
make lint # Or .venv/bin/ruff check .

# Auto-format code
make format # Or .venv/bin/ruff format .

# Type checking
make typecheck # Or .venv/bin/mypy the_flip

# Template linting
make lint-templates # Or .venv/bin/djlint templates/ --check

# Run all quality checks at once
make quality
```

### Pre-commit Hooks

If you installed pre-commit hooks (`pre-commit install`), these checks run automatically before each commit. If checks fail, the commit is blocked until you fix the issues.

To manually run all pre-commit checks:
```bash
pre-commit run --all-files
```

## Testing

**Before submitting a PR, ensure tests pass:**

```bash
# Run all tests
make test

# Run tests with coverage report
make coverage
```

**For detailed testing guidelines, see [docs/Testing.md](docs/Testing.md)**

## Pull Request Process

- **Push your branch** to GitHub
- **Create a Pull Request** against the `main` branch
- **Fill out the [PR template](.github/pull_request_template.md)**
- **Test in hosted env**.  When you create a PR, a temporary test environment is automatically created with a unique URL to click-test your changes before merging. For details, see [docs/Deployment.md](docs/Deployment.md).
- **Address review feedback** by pushing new commits to your branch
- **Wait for approval** - maintainers will review and may request changes
- **Merge** - Once approved, your PR will be merged



## Branch Naming Convention

Branch names should follow this pattern: `<type>/<author>/<brief-description>`

### Types

- `feat` - New features or enhancements
- `fix` - Bug fixes
- `docs` - Documentation changes
- `chore` - Maintenance tasks (dependencies, tooling, config)
- `test` - Test additions or modifications
- `refactor` - Code refactoring without functional changes

### Author

Your username or identifier (e.g., `moses`, `claude`, `yourname`)

### Examples

- `feat/claude/add-contributing-guide`
- `fix/moses/video-upload-timeout`
- `docs/codex/architecture-overview`
- `chore/moses/update-dependencies`
- `test/gemini/add-catalog-tests`

## Commit Messages

Write clear, descriptive commit messages:

**Good:**
```
Add pre-commit hooks for code quality checks

- Configure ruff for linting and formatting
- Add mypy for type checking
- Update CONTRIBUTING.md with setup instructions
```

**Avoid:**
```
fixed stuff
wip
updates
```
