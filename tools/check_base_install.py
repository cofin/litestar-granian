from importlib.util import find_spec

_OPTIONAL_LOOPS = ("rloop", "uvloop", "winloop")


def main() -> None:
    installed = [name for name in _OPTIONAL_LOOPS if find_spec(name) is not None]
    if installed:
        message = f"base installation unexpectedly contains optional event loops: {', '.join(installed)}"
        raise SystemExit(message)


if __name__ == "__main__":
    main()
