# The Flip Pinball Musuem's Maintenance System

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
   pip install -r requirements.txt
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
   python manage.py import_maintainers
   python manage.py import_machines
   python manage.py import_maintenance_records
   ```

8. **Run development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   - Main site: http://localhost:8000/
   - Admin panel: http://localhost:8000/admin/

## Developing, Testing, Deploying

See [docs/README.md](docs/README.md). 

AI helpers like Claude and Codex **MUST** read and follow the docs linked at [docs/README.md](docs/README.md) before answering questions or generating assets. Those docs spell out how AI assistants must work with HTML, CSS, Django/Python, the project structure, data model, and testing.
