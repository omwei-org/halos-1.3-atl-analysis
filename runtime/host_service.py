from __future__ import annotations

import os

from runtime.host_io import RelayHostAdapter


def main() -> None:
    """Run the physical-I/O adapter natively on the deployment host.

    The host service owns device-specific I/O. It is intentionally separate
    from the Magic Box governance process and does not make authorization or
    safety decisions.
    """
    socket_path = os.getenv(
        "MAGIC_BOX_IO_SOCKET", "/run/equinibrium/magic-box-io.sock"
    )
    RelayHostAdapter(socket_path).serve_forever()


if __name__ == "__main__":
    main()
