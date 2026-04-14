"""AutoCAD COM connection manager.

Provides :class:`AutoCADConnection` – a thin wrapper around the
``AutoCAD.Application`` COM object with connection/retry logic, command
dispatch, and safe accessor methods.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# win32com is a Windows-only dependency; guard import so the module can be
# imported on non-Windows hosts (e.g. CI/CD, documentation builds).
try:
    import win32com.client
    import pywintypes
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False
    logger.warning(
        "pywin32 is not installed or this is not a Windows host – "
        "AutoCAD COM features will be unavailable."
    )


class AutoCADConnectionError(RuntimeError):
    """Raised when a COM operation fails or AutoCAD is not available."""


class AutoCADConnection:
    """Manages a COM connection to a running AutoCAD Electrical 2025 instance.

    Usage::

        conn = AutoCADConnection()
        conn.connect()
        conn.send_command("ZOOM A ")
        doc = conn.get_active_document()
        conn.disconnect()

    The class also supports use as a context manager::

        with AutoCADConnection() as conn:
            conn.send_command("ZOOM A ")
    """

    _MAX_RETRIES: int = 3
    _RETRY_DELAY: float = 2.0  # seconds

    def __init__(
        self,
        com_object: str = "AutoCAD.Application",
        timeout: int = 30,
    ) -> None:
        self._com_object = com_object
        self._timeout = timeout
        self._app: Optional[Any] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Attempt to attach to a running AutoCAD instance.

        Tries up to :attr:`_MAX_RETRIES` times with a :attr:`_RETRY_DELAY`
        second pause between attempts.

        Returns
        -------
        bool
            ``True`` on success.

        Raises
        ------
        AutoCADConnectionError
            If all retries are exhausted or win32com is unavailable.
        """
        if not _WIN32_AVAILABLE:
            raise AutoCADConnectionError(
                "pywin32 is not installed. "
                "Run: pip install pywin32"
            )

        last_error: Exception | None = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                logger.debug(
                    "Connecting to AutoCAD COM object '%s' (attempt %d/%d)…",
                    self._com_object,
                    attempt,
                    self._MAX_RETRIES,
                )
                self._app = win32com.client.GetActiveObject(self._com_object)
                self._app.Visible = True
                logger.info(
                    "Connected to AutoCAD %s",
                    self._get_version_string(),
                )
                return True
            except Exception as exc:  # pywintypes.com_error or similar
                last_error = exc
                logger.warning(
                    "Connection attempt %d failed: %s", attempt, exc
                )
                if attempt < self._MAX_RETRIES:
                    time.sleep(self._RETRY_DELAY)

        raise AutoCADConnectionError(
            f"Could not connect to AutoCAD after {self._MAX_RETRIES} attempts. "
            f"Last error: {last_error}. "
            "Make sure AutoCAD Electrical 2025 is running."
        )

    def disconnect(self) -> None:
        """Release the COM reference (does not close AutoCAD)."""
        self._app = None
        logger.info("Disconnected from AutoCAD COM object.")

    def is_connected(self) -> bool:
        """Return ``True`` if a live COM connection exists."""
        if self._app is None:
            return False
        try:
            # Touch a trivial property to verify the COM object is still alive
            _ = self._app.Name
            return True
        except Exception:
            self._app = None
            return False

    def ensure_connected(self) -> None:
        """Raise :class:`AutoCADConnectionError` if not connected."""
        if not self.is_connected():
            raise AutoCADConnectionError(
                "AutoCAD is not connected. Call connect() first, or ensure "
                "AutoCAD Electrical 2025 is running."
            )

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def send_command(self, cmd: str) -> None:
        """Send a command string to AutoCAD's command line.

        The command is forwarded via ``ActiveDocument.SendCommand``.  A
        trailing space or newline is appended automatically if not present, so
        callers can pass plain command names.

        Parameters
        ----------
        cmd:
            The command string, e.g. ``"ZOOM A "`` or ``"(command \\"WDLADDER\\")"``
        """
        self.ensure_connected()
        doc = self.get_active_document()
        if not cmd.endswith((" ", "\n", "\r")):
            cmd += " "
        try:
            doc.SendCommand(cmd)
            logger.debug("SendCommand: %r", cmd)
        except Exception as exc:
            raise AutoCADConnectionError(
                f"SendCommand failed for command {cmd!r}: {exc}"
            ) from exc

    def send_lisp(self, lisp_expr: str) -> Any:
        """Evaluate a LISP expression in AutoCAD and return the result.

        Parameters
        ----------
        lisp_expr:
            A valid AutoLISP expression, e.g. ``'(+ 1 2)'``.
        """
        self.ensure_connected()
        try:
            result = self._app.ActiveDocument.SendCommand(f"{lisp_expr}\n")
            return result
        except Exception as exc:
            raise AutoCADConnectionError(
                f"LISP evaluation failed for {lisp_expr!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Document / model-space accessors
    # ------------------------------------------------------------------

    def get_active_document(self) -> Any:
        """Return the COM object for the currently active AutoCAD document.

        Raises
        ------
        AutoCADConnectionError
            If AutoCAD is not connected or no document is open.
        """
        self.ensure_connected()
        try:
            doc = self._app.ActiveDocument
            if doc is None:
                raise AutoCADConnectionError("No document is currently open in AutoCAD.")
            return doc
        except AutoCADConnectionError:
            raise
        except Exception as exc:
            raise AutoCADConnectionError(f"Could not retrieve active document: {exc}") from exc

    def get_model_space(self) -> Any:
        """Return the ModelSpace collection of the active document."""
        doc = self.get_active_document()
        try:
            return doc.ModelSpace
        except Exception as exc:
            raise AutoCADConnectionError(f"Could not retrieve ModelSpace: {exc}") from exc

    def get_application(self) -> Any:
        """Return the raw AutoCAD Application COM object."""
        self.ensure_connected()
        return self._app

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def app(self) -> Any:
        """The raw AutoCAD Application COM object (may be ``None``)."""
        return self._app

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_version_string(self) -> str:
        try:
            return f"{self._app.Name} {self._app.Version}"
        except Exception:
            return "(unknown version)"

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "AutoCADConnection":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_connection_instance: AutoCADConnection | None = None


def get_connection(
    com_object: str = "AutoCAD.Application",
    timeout: int = 30,
    auto_connect: bool = True,
) -> AutoCADConnection:
    """Return the module-level :class:`AutoCADConnection` singleton.

    Parameters
    ----------
    com_object:
        The COM ProgID to use when creating the connection.
    timeout:
        Connection timeout in seconds.
    auto_connect:
        When ``True`` (default), call :meth:`~AutoCADConnection.connect` if
        the instance is not already connected.
    """
    global _connection_instance
    if _connection_instance is None:
        _connection_instance = AutoCADConnection(
            com_object=com_object, timeout=timeout
        )
    if auto_connect and not _connection_instance.is_connected():
        _connection_instance.connect()
    return _connection_instance


def reset_connection() -> None:
    """Discard the cached connection singleton (useful for testing)."""
    global _connection_instance
    _connection_instance = None
