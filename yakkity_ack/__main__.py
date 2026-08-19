"""Allow ``python -m yakkity_ack``."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
