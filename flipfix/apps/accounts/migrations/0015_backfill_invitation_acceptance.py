"""Backfill the new acceptance fields from the old ``used`` flag.

``used=True`` becomes ``accepted_at``. There is no record of *when* an old
invitation was accepted, so ``updated_at`` stands in — it was last written
by the registration view marking the invitation used, which makes it the
closest thing to the truth we have.

``accepted_by`` is filled in on a best-effort basis by matching the
invitation's email to a user's, and **only when exactly one user matches**.
A duplicate or missing match is left NULL: an invite tree that says
"Unknown" is honest, one that names the wrong person is not.

``invited_by`` stays NULL throughout. Nothing in the old schema recorded it
and it must not be guessed.
"""

from django.db import migrations


def pick_accepted_by(candidates):
    """Return the one unambiguous match, or None.

    Split out so it can be unit-tested without standing up a historical
    database: this one rule is the only place the backfill can get a person
    wrong, and "exactly one match or nobody" is the whole of it.
    """
    return candidates[0] if len(candidates) == 1 else None


def backfill_acceptance(apps, schema_editor):
    Invitation = apps.get_model("accounts", "Invitation")
    User = apps.get_model("auth", "User")

    for invitation in Invitation.objects.filter(used=True):
        invitation.accepted_at = invitation.updated_at
        candidate = pick_accepted_by(list(User.objects.filter(email__iexact=invitation.email)[:2]))
        # accepted_by is OneToOne: skip anyone already claimed by an earlier
        # invitation rather than tripping the unique constraint.
        if candidate is not None and not Invitation.objects.filter(accepted_by=candidate).exists():
            invitation.accepted_by = candidate
        invitation.save(update_fields=["accepted_at", "accepted_by"])


def restore_used_flag(apps, schema_editor):
    Invitation = apps.get_model("accounts", "Invitation")
    Invitation.objects.filter(accepted_at__isnull=False).update(used=True)
    Invitation.objects.filter(accepted_at__isnull=True).update(used=False)
    Invitation.objects.update(accepted_at=None, accepted_by=None)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_invitation_chain"),
    ]

    operations = [
        migrations.RunPython(backfill_acceptance, restore_used_flag),
    ]
