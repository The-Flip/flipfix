"""
Parts views, split by domain.

- part_requests.py: Part request CRUD and listing
- part_request_updates.py: Part request update CRUD
"""

from the_flip.apps.parts.views.part_request_updates import (  # noqa: F401
    PartRequestUpdateCreateView,
    PartRequestUpdateDetailView,
    PartRequestUpdateEditView,
)
from the_flip.apps.parts.views.part_requests import (  # noqa: F401
    PartRequestCreateView,
    PartRequestDetailView,
    PartRequestEditView,
    PartRequestListPartialView,
    PartRequestListView,
    PartRequestStatusUpdateView,
    PartRequestUpdatesPartialView,
)
