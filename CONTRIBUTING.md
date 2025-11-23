# Contributing to The Flip

This guide covers the contribution workflow, code quality standards, and pull request process.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Quality](#code-quality)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Branch Naming Convention](#branch-naming-convention)
- [Code of Conduct](#code-of-conduct)

## Getting Started

1. **Complete setup** - Follow [README.md](README.md) to get the app running locally (including development tools)
2. **Read the docs** - Review [docs/](docs/) to understand technical conventions:
   - [Project Structure](docs/Project_Structure.md) - Directory layout and app organization
   - [Data Model](docs/Datamodel.md) - Database schema and relationships
   - [Django/Python](docs/Django_Python.md) - Coding conventions and patterns
   - [HTML/CSS](docs/HTML_CSS.md) - Frontend conventions
   - [Testing](docs/Testing.md) - Testing strategies

## Development Workflow

1. **Create a feature branch** (see [Branch Naming Convention](#branch-naming-convention) below)
2. **Make your changes** following the code quality guidelines
3. **Write tests** for new functionality
4. **Run tests** to ensure nothing breaks
5. **Commit your changes** with clear commit messages
6. **Push your branch** to GitHub
7. **Create a Pull Request** following the PR template

## Code Quality

### Code Formatting and Linting

We use [Ruff](https://github.com/astral-sh/ruff) for both linting and formatting. Ruff is fast and combines the functionality of multiple tools (black, flake8, isort, etc.).

**Before committing, run:**

```bash
# Check for linting issues
make lint
# Or: ruff check .

# Auto-format code
make format
# Or: ruff format .
```

### Type Checking

We use mypy for optional type checking (currently permissive):

```bash
mypy the_flip
```

### Pre-commit Hooks

If you installed pre-commit hooks (`pre-commit install`), these checks run automatically before each commit. If checks fail, the commit is blocked until you fix the issues.

To manually run all pre-commit checks:
```bash
pre-commit run --all-files
```

### Configuration

Tool configurations are in `pyproject.toml`:
- Ruff linting rules
- Ruff formatting options
- Mypy type checking settings
- Coverage reporting settings

## Testing

**Before submitting a PR, ensure tests pass:**

```bash
# Run all tests
make test

# Run tests with coverage report
make coverage
```

**For detailed testing guidelines, see [docs/Testing.md](docs/Testing.md)**, which covers:
- Testing conventions and structure
- How to write effective tests
- Coverage requirements
- Test runner configuration

## Pull Request Process

1. **Ensure all tests pass** locally before pushing
2. **Update documentation** if you've changed APIs or added features
3. **Push your branch** to GitHub
4. **Create a Pull Request** against the `main` branch
5. **Fill out the PR template** with:
   - Clear description of what changed and why
   - Testing steps performed
   - Any related issues
6. **Address review feedback** by pushing new commits to your branch
7. **Wait for approval** - maintainers will review and may request changes
8. **Merge** - Once approved, your PR will be merged

### PR Environment Testing

When you create a PR, a temporary test environment is automatically created with a unique URL to click-test your changes before merging.

**For deployment details** (PR environments, production deployment, platform info), see [docs/Deployment.md](docs/Deployment.md).

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

## Code of Conduct

This project follows the Contributor Covenant Code of Conduct. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

## Questions or Issues?

- Review the [documentation](docs/README.md) first
- Check existing [GitHub Issues](https://github.com/deanmoses/the_flip/issues)
- Create a new issue if you're stuck or found a bug
