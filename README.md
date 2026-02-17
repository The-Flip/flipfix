# The Flip Pinball Museum's Maintenance System

[![CI](https://github.com/The-Flip/flipfix/actions/workflows/ci.yml/badge.svg)](https://github.com/The-Flip/flipfix/actions/workflows/ci.yml)

This is a web app for managing pinball machine problem reports at [The Flip](https://www.theflip.museum/) pinball museum.

It allows museum visitors to report problems with pinball machines (via QR codes on each machine), and enables maintainers to track, update, and resolve these issues.

## Live System

It's live at https://flipfix.theflip.museum/

## Local Development Setup

It's in Django. You need Python 3.13+.

```bash
git clone https://github.com/The-Flip/flipfix.git
cd flipfix
make bootstrap
```

Bootstrap checks your Python version, installs system dependencies, creates a venv, installs packages, sets up `.env`, and runs migrations. It's idempotent — safe to run again.

Then create some data to work with:

```bash
make sample-data    # Rich sample data (look at output for usernames, password: test123)
# OR
make superuser      # Empty system, just your admin account
```

## Running the Application

### Web Server

This is the main thing you need to run.

```bash
make runserver  # or: python manage.py runserver
```

- Main site: http://localhost:8000/
- Admin panel: http://localhost:8000/admin/

### Background Worker

You only need to run the background task worker if you want to upload video and have the system post to Discord.

```bash
make runq  # In a separate terminal
```

Requires FFmpeg for video transcoding:

- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `apt-get install ffmpeg`
- Windows: Download from [ffmpeg.org](https://ffmpeg.org/)

See [docs/Discord.md](docs/Discord.md) for how to configure Web Hooks to post to Discord. It's disabled by default.

### Discord Bot

You only need to run the Discord bot if you want to right-click in a Discord channel and add those Discord messages to Flipfix.

```bash
make runbot  # In a separate terminal
```

See [docs/Discord.md](docs/Discord.md) for setup instructions. It's disabled by default.

## Developer Documentation

See [docs/README.md](docs/README.md).
