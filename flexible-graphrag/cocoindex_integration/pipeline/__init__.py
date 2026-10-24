"""CocoIndex pipeline app for flexible-graphrag.

A single ``coco.App`` entry point (``flexible_app_main``) handles every source.
``build_app_for_config`` resolves a datasource config and returns that app; when
``source_backend=cocoindex`` and the source is one of localfs / s3 / azure_blob /
google_drive it lists via the matching native CocoIndex connector (see
``native_apps.NATIVE_READERS``), otherwise it lists via ``FlexibleDataSource``.

Helpers:

- ``build_flexible_source_app()``         — build the .env-configured app
- ``build_app_for_config(source_config)`` — build one app from a datasource_config row
- ``build_apps_for_all_sources(db_url)``  — async: build all active apps from DB (no-sync-button)

Running ``python -m cocoindex_integration.pipeline`` starts the app implied by
``DATA_SOURCE`` / ``SOURCE_BACKEND`` in ``.env``.
"""

from cocoindex_integration.pipeline.env_config import load_config_from_env  # noqa: F401
from cocoindex_integration.pipeline.run import (  # noqa: F401
    set_progress_hook,
    set_runtime_skip_graph,
    set_runtime_graphs,
)
from cocoindex_integration.pipeline.flexible_app import (  # noqa: F401
    flexible_app_main,
    build_flexible_source_app,
    build_app_for_config,
    build_apps_for_all_sources,
    _build_default_app,
)
# WARNING — this line rebinds the package attribute ``app`` from the *submodule*
# ``cocoindex_integration.pipeline.app`` to the module-level ``app`` variable
# inside it (a ``coco.App`` instance, or None when no primary source is
# configured).  Consequence:
#
#     from cocoindex_integration.pipeline import app   # -> coco.App, NOT the module
#     from cocoindex_integration.pipeline.app import x # -> fine, real submodule
#
# So never reach for pipeline functions through the first form.  Import them
# from the submodule that defines them (``pipeline.run``, ``pipeline.state``),
# or use ``sys.modules["cocoindex_integration.pipeline.app"]`` the way
# ``bridge._get_pipeline_module()`` does.
from cocoindex_integration.pipeline.app import app  # noqa: F401

__all__ = [
    "app",
    "load_config_from_env",
    "set_progress_hook",
    "set_runtime_skip_graph",
    "set_runtime_graphs",
    "flexible_app_main",
    "build_flexible_source_app",
    "build_app_for_config",
    "build_apps_for_all_sources",
    "_build_default_app",
]
