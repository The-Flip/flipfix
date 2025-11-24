# Contributing

This guide covers how to contribute to the project and submit a PR.


## Getting Started

1. **Developer setup** - Follow [README.md](README.md) to get the app running locally
2. **Read the docs** - Review [docs/README.md](docs/README.md) to understand technical conventions

## Workflow

1. **Create a feature branch** with a descriptive name
2. **Make your changes** following the code quality guidelines
3. **Write tests** for new functionality
4. **Run tests** to ensure nothing breaks
5. **Commit your changes** with clear commit messages
6. **Push your branch** to GitHub
7. **Create a Pull Request**

## Code Quality

Before pushing:

```bash
make quality     # Format, lint, check Python types
make test        # Run the suite
```

If you have pre-commit installed, it will run on commit; otherwise rely on the commands above.

## Pull Request Process

- **Push your branch** to GitHub
- **Create a Pull Request** against `main`
- **Write a description** of what changed and why. Link to related issues if applicable.
- **Wait for CI checks** - GitHub Actions will automatically run tests, linting, and type checking
- **Test in hosted env** - A temporary environment is automatically created for testing. See [docs/Deployment.md](docs/Deployment.md).
- **Merge when ready** - PRs can be self-merged once CI passes
