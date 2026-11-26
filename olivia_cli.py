# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Console entry points for the ``olivia-tarot`` distribution.

The application modules in ``agent/`` use bare imports (``import knowledge``,
``import tools``, ...) and resolve their data files relative to ``agent/``
(``BASE_DIR`` / ``REPO_DIR``).  Adding ``agent/`` to ``sys.path`` before
importing preserves both behaviours for a wheel install, without modifying
any application module.
"""

import os
import sys

_AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent")


def _prepare():
    if _AGENT_DIR not in sys.path:
        sys.path.insert(0, _AGENT_DIR)


def main():
    """Start the local web server (``olivia`` command)."""
    _prepare()
    import server
    return server.main()


def mcp_main():
    """Start the MCP stdio server (``olivia-mcp`` command)."""
    _prepare()
    import mcp_server
    if "--selftest" in sys.argv:
        return mcp_server._selftest()
    return mcp_server.serve()


if __name__ == "__main__":
    main()
