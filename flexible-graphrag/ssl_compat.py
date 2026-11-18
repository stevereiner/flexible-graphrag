"""HTTPS trust fixes for machines running TLS-inspecting software.

Why this module exists
----------------------
Two things break outbound HTTPS (OpenAI, Anthropic, any LLM or cloud API) on a
machine whose traffic is intercepted and re-signed — antivirus with "HTTPS
scanning", or a corporate proxy:

1. **``ssl.VERIFY_X509_STRICT``** is on by default from Python 3.12.  It rejects
   CA certificates whose Basic Constraints extension is missing or not marked
   critical, which is exactly what SSL-inspection roots tend to look like.  The
   handshake fails with::

       SSLCertVerificationError: certificate verify failed:
       Basic Constraints of CA cert not marked critical

2. **httpx passes ``cafile=certifi.where()``**, so only certifi's ~118 roots are
   loaded and any locally-installed CA — including the inspection root sitting
   in the Windows certificate store — is invisible::

       SSLCertVerificationError: unable to get local issuer certificate

Either way the OpenAI client reports the generic
``APIConnectionError: Connection error.``, which says nothing about certificates
and sends you looking for a network or API-key problem instead.

:func:`patch_ssl_context` clears the strict flag and additionally loads the OS
certificate store, so certifi's roots are supplemented rather than replaced.

requests / urllib3 (the Box SDK, Google clients ...) don't use
``ssl.create_default_context``: they build their own context with
``urllib3.util.ssl_.create_urllib3_context``, then load certifi. That one is
patched the same way.

Who calls this
--------------
Anything that makes outbound HTTPS calls and is NOT started through the backend:

* ``main.py`` (the FastAPI app) — on import
* ``langflow_components/flexible_graphrag/_fg_shared.py`` — for flow mode
* ``examples/`` scripts — they deliberately do not import the backend's main.py

The failure mode without it is confusing precisely because it is *partial*: the
app works (it patched on startup) while a standalone script against the same
API on the same machine fails, so it looks like the script is at fault.

Idempotent — calling it more than once is harmless.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Set once the patch is installed, so repeated calls are cheap no-ops.
_PATCHED = False


def patch_ssl_context() -> bool:
    """Make ``ssl.create_default_context`` tolerant of re-signed certificates.

    Returns True if the patch is in place (including when already applied).
    Never raises: failing to patch must not stop a program from starting — it
    will simply hit the original TLS error later, with its real message.
    """
    global _PATCHED
    if _PATCHED:
        return True

    try:
        import ssl as _ssl

        _original = _ssl.create_default_context

        def _create_default_context(*args: Any, **kwargs: Any):
            ctx = _original(*args, **kwargs)
            if hasattr(_ssl, "VERIFY_X509_STRICT"):
                ctx.verify_flags &= ~_ssl.VERIFY_X509_STRICT
            try:
                # Supplement certifi with the OS store, where an inspection root
                # or corporate CA actually lives.
                ctx.load_default_certs(_ssl.Purpose.SERVER_AUTH)
            except Exception:  # noqa: BLE001 - keep the usable context
                pass
            return ctx

        _ssl.create_default_context = _create_default_context  # type: ignore[assignment]
        _patch_urllib3(_ssl)
        _PATCHED = True
        logger.debug(
            "SSL patch applied: cleared VERIFY_X509_STRICT, added OS cert store"
        )
        return True
    except Exception as exc:  # noqa: BLE001 - never block startup over this
        logger.debug("SSL patch not applied (%s) — continuing unpatched", exc)
        return False


def _patch_urllib3(_ssl) -> None:
    """The same fix for urllib3's own contexts (requests then adds certifi on top)."""
    try:
        import urllib3.connection as _connection
        import urllib3.util.ssl_ as _ssl_util
    except ImportError:
        return
    _original = _ssl_util.create_urllib3_context

    def _create_urllib3_context(*args: Any, **kwargs: Any):
        ctx = _original(*args, **kwargs)
        if hasattr(_ssl, "VERIFY_X509_STRICT"):
            ctx.verify_flags &= ~_ssl.VERIFY_X509_STRICT
        try:
            ctx.load_default_certs(_ssl.Purpose.SERVER_AUTH)
        except Exception:  # noqa: BLE001 - keep the usable context
            pass
        return ctx

    # connection.py imported the function by name: patch both
    _ssl_util.create_urllib3_context = _create_urllib3_context
    if getattr(_connection, "create_urllib3_context", None) is _original:
        _connection.create_urllib3_context = _create_urllib3_context


__all__ = ["patch_ssl_context"]
