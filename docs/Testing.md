# Automated Testing Guide

## Running Tests

```bash
make test         # Run Python tests except for ones tagged `integration`
make test-all     # Run full Python suite including integration tests
make test-models  # Run tests tagged `model` only
make test-js      # Run JavaScript tests.  Requires `npm install`
```

### In CI

- **PostgreSQL vs SQLite**
  - GitHub Actions runs tests against PostgreSQL (matching production)
  - Localhost `make test` uses SQLite (what we use for localhost dev) for speed
- **ffmpeg** (for video transcoding):
  - GitHub Actions installs ffmpeg/ffprobe and runs the full suite, so `integration` tests are expected to pass there.
  - Keep `integration` tests runnable locally, but `make test` excludes them by default for quick iteration if you don't have ffmpeg installed; env-dependent checks will be skipped when the binaries are missing. Unit tests mock ffmpeg/probe/upload to stay fast and quiet.

## Python Tests

See [TestingPython.md](TestingPython.md) for running tests by tag and how to write Python tests.

## JavaScript Tests

See [TestingJavascript.md](TestingJavascript.md) for how to write JS tests.
