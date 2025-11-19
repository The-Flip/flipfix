# Prototype of The Flip Pinball Musuem's Maintenance System

This is a prototype web app for managing pinball machine problem reports at The Flip pinball museum.

It allows museum visitors to report problems with pinball machines (via QR codes on each machine), and enables maintainers to track, update, and resolve these issues. 

## Live System
Check out the prototype live at https://the-flip.onrender.com

## AI Assistant Instructions
AI helpers like Claude and Codex must read and follow `docs/dev_guide/README.md` before answering questions or generating assets. That guide spells out how AI assistants are to work with HTML, CSS, Django/Python, the project structure, data model, and tests.

## Local Development Setup
It's in Django.

### Prerequisites
- Python 3.13+
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd the_flip
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set all the values, see the examples.

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

## Creating Maintainer Accounts

Maintainers need both a Django user account and a Maintainer profile:

1. Create user via Django admin or `createsuperuser` command
2. In the admin panel (`/admin/`), create a Maintainer record linked to that user
3. Maintainer can now log in and manage reports

Alternatively, staff users (with `is_staff=True`) can also manage reports without a Maintainer profile.


## Deploying the Public Prototype

The prototype at https://the-flip.onrender.com is deployed every time this repo's main branch is pushed to Github.

Render runs `build.sh`, which installs dependencies, applies migrations, collects static files, and seeds the database by calling the same management commands listed above. That process imports maintainers, machines, and maintenance history on every deploy, so any data added through the site will be wiped the next time the build runs. 
