"""Wiki selectors: read-only query composition and data assembly."""

from .models import WikiPageTag, WikiTagOrder


def build_nav_tree() -> dict:
    """Build the navigation tree from WikiPageTag records.

    Returns a nested dict structure representing the tag hierarchy with pages.

    Structure:
        {
            'pages': [...],  # Untagged pages (tag='')
            'children': {
                'machines': {
                    'pages': [...],  # Pages directly in 'machines'
                    'children': {
                        'blackout': {
                            'pages': [...],  # Pages in 'machines/blackout'
                            'children': {...}
                        }
                    }
                }
            }
        }
    """
    # Query 1: All page-tag relationships with page data
    page_tags = WikiPageTag.objects.select_related("page").all()

    # Query 2: Tag ordering
    tag_orders = {o.tag: o.order for o in WikiTagOrder.objects.all()}

    # Build tree structure
    tree: dict = {"pages": [], "children": {}}

    for pt in page_tags:
        if not pt.tag:
            # Untagged page - goes at root level
            tree["pages"].append(
                {
                    "page": pt.page,
                    "order": pt.order,
                    "path": pt.slug,
                }
            )
        else:
            # Navigate/create path through tree
            segments = pt.tag.split("/")
            node = tree
            current_path = ""

            for segment in segments:
                current_path = f"{current_path}/{segment}" if current_path else segment
                if segment not in node["children"]:
                    node["children"][segment] = {
                        "pages": [],
                        "children": {},
                        "tag_path": current_path,
                        "order": tag_orders.get(current_path),
                    }
                node = node["children"][segment]

            # Add page to the final node
            node["pages"].append(
                {
                    "page": pt.page,
                    "order": pt.order,
                    "path": f"{pt.tag}/{pt.slug}",
                }
            )

    _sort_nav_tree(tree)

    return tree


def _sort_nav_tree(node: dict) -> None:
    """Sort pages and children within each nav tree node recursively.

    Ordered items sort first (by order value), then alphabetically.
    """
    node["pages"] = sorted(
        node["pages"],
        key=lambda p: (p["order"] is None, p["order"] or 0, p["page"].title.lower()),
    )
    node["children"] = dict(
        sorted(
            node["children"].items(),
            key=lambda item: (
                item[1]["order"] is None,
                item[1]["order"] or 0,
                item[0].lower(),
            ),
        )
    )
    for child in node["children"].values():
        _sort_nav_tree(child)
