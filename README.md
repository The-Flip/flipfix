# The Flip Pinball Museum's Maintenance System

[![CI](https://github.com/deanmoses/the_flip/actions/workflows/ci.yml/badge.svg)](https://github.com/deanmoses/the_flip/actions/workflows/ci.yml)

This is a web app for managing pinball machine problem reports at [The Flip](https://www.theflip.museum/) pinball museum.

It allows museum visitors to report problems with pinball machines (via QR codes on each machine), and enables maintainers to track, update, and resolve these issues.

## Live System
It's live at https://flipfix.theflip.museum/

## Local Development Setup
It's in Django.

### Prerequisites
- Python 3.13+
- pip

### Installation

1. **Clone repo**
   ```bash
   git clone https://github.com/deanmoses/the_flip.git
   cd the_flip
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.dev.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set values based on the instructions inside

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Load sample data (optional)**
   ```bash
   python manage.py create_sample_data
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

See [docs/Discord.md](docs/Discord.md) for how to configure Web Hooks to post to Discord.  It's disabled by default.

### Discord Bot
You only need to run the Discord bot if you want to right-click in a Discord channel and add those Discord messages to Flipfix.
```bash
make runbot  # In a separate terminal
```
See [docs/Discord.md](docs/Discord.md) for setup instructions.  It's disabled by default.

## Development Tools

**Install pre-commit hooks** (recommended):
```bash
pre-commit install
```

This automatically runs code quality checks before each commit.

## Developer Documentation

See [docs/README.md](docs/README.md).
