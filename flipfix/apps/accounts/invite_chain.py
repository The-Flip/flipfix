"""Who invited whom.

The chain is two foreign keys on :class:`~flipfix.apps.accounts.models.Invitation`
— ``invited_by`` (a user) and ``accepted_by`` (the user that invitation
created). Walking it is pure Python over two queries rather than a recursive
CTE: the museum has dozens of accounts, not millions, and keeping this
backend-agnostic matters more than the query count when dev is SQLite and
production is Postgres.

Kept out of the view modules so the traversal can be tested directly.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from django.contrib.auth import get_user_model

from .models import Invitation

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

User = cast("type[UserType]", get_user_model())

logger = logging.getLogger(__name__)

#: Depth at which we stop descending and log instead. The edges cannot
#: actually cycle — an inviter must exist before anyone can accept their
#: invitation — but an unbounded recursion over user-shaped data is the kind
#: of thing that should fail loudly rather than hang a page.
MAX_CHAIN_DEPTH = 20


@dataclass
class ChainNode:
    """One account in the invite tree, plus everyone below it."""

    user: UserType
    #: The invitation this account was created from. ``None`` for accounts
    #: that were not created by an invitation — superusers, shared terminals,
    #: and everyone who joined before invite tracking existed.
    invitation: Invitation | None
    children: list[ChainNode] = field(default_factory=list)

    @property
    def inviter(self) -> UserType | None:
        """Who invited this account, or ``None`` if we have no record.

        ``None`` means *unknown*, not *self-registered*. Historical rows
        carry no inviter and the UI must not claim otherwise.
        """
        return self.invitation.invited_by if self.invitation else None

    @property
    def descendant_count(self) -> int:
        return sum(1 + child.descendant_count for child in self.children)


def _accepted_invitations() -> dict[int, Invitation]:
    """Map ``user_id`` -> the invitation that created that user."""
    return {
        invitation.accepted_by_id: invitation
        for invitation in Invitation.objects.accepted()
        .exclude(accepted_by__isnull=True)
        .select_related("invited_by", "accepted_by")
    }


def build_chain() -> list[ChainNode]:
    """Return the invite forest, roots ordered by username.

    Roots are accounts with no recorded inviter. That is every account
    predating invite tracking, plus superusers and shared terminals, which
    are provisioned directly.
    """
    users = list(User.objects.order_by("username"))
    invitations = _accepted_invitations()
    known_ids = {user.pk for user in users}

    children: dict[int, list[UserType]] = defaultdict(list)
    roots: list[UserType] = []
    for user in users:
        invitation = invitations.get(user.pk)
        parent_id = invitation.invited_by_id if invitation else None
        # An inviter who no longer exists leaves their invitees as roots
        # rather than dropping them off the page entirely.
        if parent_id is None or parent_id not in known_ids:
            roots.append(user)
        else:
            children[parent_id].append(user)

    return [_build_node(user, invitations, children, depth=0) for user in roots]


def _build_node(
    user: UserType,
    invitations: dict[int, Invitation],
    children: dict[int, list[UserType]],
    depth: int,
) -> ChainNode:
    node = ChainNode(user=user, invitation=invitations.get(user.pk))
    if depth >= MAX_CHAIN_DEPTH:
        logger.warning(
            "Invite chain deeper than %s levels; truncating at %s",
            MAX_CHAIN_DEPTH,
            user.get_username(),
        )
        return node
    node.children = [
        _build_node(child, invitations, children, depth + 1) for child in children.get(user.pk, ())
    ]
    return node


def descendant_users(user: UserType) -> list[UserType]:
    """Everyone ``user`` brought in, transitively, breadth-first.

    Breadth-first so the confirmation page reads outward from the person
    being pruned — direct invitees first, then theirs.
    """
    children: dict[int, list[UserType]] = defaultdict(list)
    for invitation in _accepted_invitations().values():
        # accepted_by is nullable on the model and excluded by
        # _accepted_invitations(). Binding it locally states that invariant
        # once, for the reader and the type checker alike.
        invitee = invitation.accepted_by
        if invitation.invited_by_id is not None and invitee is not None:
            children[invitation.invited_by_id].append(invitee)

    found: list[UserType] = []
    seen = {user.pk}
    queue = deque(children.get(user.pk, ()))
    while queue:
        candidate = queue.popleft()
        if candidate.pk in seen:
            continue
        seen.add(candidate.pk)
        found.append(candidate)
        queue.extend(children.get(candidate.pk, ()))
    return found
