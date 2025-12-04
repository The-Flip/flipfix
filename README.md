# The Flip Pinball Museum's Maintenance System

[![CI](https://github.com/deanmoses/the_flip/actions/workflows/ci.yml/badge.svg)](https://github.com/deanmoses/the_flip/actions/workflows/ci.yml)

This is a web app for managing pinball machine problem reports at The Flip pinball museum.

It allows museum visitors to report problems with pinball machines (via QR codes on each machine), and enables maintainers to track, update, and resolve these issues.

## Live System
It's live at https://the-flip-production.up.railway.app

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

8. **Run development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   - Main site: http://localhost:8000/
   - Admin panel: http://localhost:8000/admin/

## Development Tools

1. **Install pre-commit hooks** (recommended)
   ```bash
   pre-commit install
   ```

   This automatically runs code quality checks before each commit.

2. **Install FFmpeg** (for video transcoding features)
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `apt-get install ffmpeg`
   - Windows: Download from [ffmpeg.org](https://ffmpeg.org/)

3. **Run background worker** (for video transcoding and webhooks)
   ```bash
   # In a separate terminal
   make runq
   ```

   The background worker handles async tasks like video transcoding and webhook delivery.

## Developer Documentation

See [docs/README.md](docs/README.md) for detailed guides on:
- Project structure and architecture
- Django and Python conventions
- HTML/CSS patterns
- Data model documentation
- Testing strategies
- Deployment process

AI helpers like Claude and Codex **MUST** read and follow the docs linked at [docs/README.md](docs/README.md) before answering questions or generating assets. Those docs spell out how AI assistants must work with HTML, CSS, Django/Python, the project structure, data model, and testing.
