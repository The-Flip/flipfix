"""Add the invite-chain fields to Invitation.

``used`` is deliberately kept here so 0015 can read it; 0016 drops it once
the backfill has run.

``expires_at``'s callable default is evaluated once, at migrate time, for
every existing row. For the handful of never-used legacy invitations that
means they stay live for a further two weeks and then lapse — previously
they never expired at all, so this shortens their life rather than
extending it.
"""


import django.db.models.deletion
import flipfix.apps.accounts.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_alter_maintainer_bio'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='maintainer',
            options={'ordering': ['user__username'], 'permissions': [('can_access_maintainer_portal', 'Can access the maintainer portal'), ('can_manage_catalog', 'Can manage catalog (create machines, print QR codes)'), ('can_view_user_profiles', 'Can view the user directory and profile pages'), ('can_invite_users', 'Can invite new users')]},
        ),
        migrations.AddField(
            model_name='invitation',
            name='accepted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='invitation',
            name='accepted_by',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invitation', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='invitation',
            name='expires_at',
            field=models.DateTimeField(db_index=True, default=flipfix.apps.accounts.models.default_invitation_expiry),
        ),
        migrations.AddField(
            model_name='invitation',
            name='invited_by',
            field=models.ForeignKey(blank=True, help_text='Who sent this invitation. Null for invitations predating invite tracking.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invitations_sent', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='invitation',
            name='last_sent_at',
            field=models.DateTimeField(blank=True, help_text='When the invitation email was last sent. Null if it has never been sent.', null=True),
        ),
        migrations.AddField(
            model_name='invitation',
            name='revoked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='invitation',
            name='email',
            field=models.EmailField(max_length=254),
        ),
    ]
