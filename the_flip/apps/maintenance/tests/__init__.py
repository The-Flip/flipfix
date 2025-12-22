# Import all test classes so Django's test discovery finds them
from .test_api import *  # noqa: F401, F403
from .test_environment import *  # noqa: F401, F403
from .test_forms import *  # noqa: F401, F403
from .test_log_entries import *  # noqa: F401, F403
from .test_problem_report_autocomplete import *  # noqa: F401, F403
from .test_problem_report_create import *  # noqa: F401, F403
from .test_problem_report_detail import *  # noqa: F401, F403
from .test_problem_report_list import *  # noqa: F401, F403
from .test_problem_report_media import *  # noqa: F401, F403
from .test_tasks import *  # noqa: F401, F403
