"""Populate the SiteSettings singleton with the default front page content.

This converts the previously hard-coded home.html welcome message and
support links into editable markdown stored in the database.
"""

from django.db import migrations

DEFAULT_CONTENT = """\
## Welcome to The Flip's pinball machine maintenance system.

---

### Bugs & ideas

Found a bug or have an idea?

[Post to Discord](https://discord.com/channels/1408179768033149132/1408180474853064798) or \
[Open a GitHub Issue](https://github.com/The-Flip/flipfix/issues) *(GitHub requires an account)*\
"""


def populate(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.get_or_create(pk=1, defaults={"front_page_content": DEFAULT_CONTENT})


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_sitesettings"),
    ]

    operations = [
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
