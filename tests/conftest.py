"""Keep operator-machine checks separate from the clean-runner suite."""


def pytest_addoption(parser):
    parser.addoption(
        "--run-live-system",
        action="store_true",
        default=False,
        help="Include checks of the deployed desktop, installed tools, and real accounts.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_system: checks deployed host state or real provider accounts (explicit opt-in)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live-system"):
        return
    selected = []
    live = []
    for item in items:
        if item.get_closest_marker("live_system") is not None:
            live.append(item)
        else:
            selected.append(item)
    items[:] = selected
    if live:
        config.hook.pytest_deselected(items=live)
