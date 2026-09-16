"""Builds main.py into a single executable (cx_Freeze), so the bot can be copied
to a VM and run without setting up a venv there.

Run with (from the project root, using the project's own venv):
    .venv\\Scripts\\python.exe setup.py build

Output lands in build\\exe.win-amd64-<pyver>\\ (or the Linux equivalent when built
there) -- alpha_bot.exe plus every DLL/dependency it needs, all in one folder. Copy
that whole folder to the VM (config.yaml and .env travel with it via include_files
below, except real credentials -- .env itself is deliberately NOT bundled; copy your
own .env next to the built .exe on the target machine).

NOTE (see paths.py): __file__-based path resolution breaks inside a frozen build --
sys.executable's own directory is used instead once frozen. That fix is already in
place; nothing else needs to change for this to work.
"""
from cx_Freeze import Executable, setup

script_name = "main.py"
app_name = "alpha_bot.exe"

build_exe_options = {
    "packages": [
        "SmartApi",       # smartapi-python
        "logzero",
        "pyotp",
        "pandas",
        "numpy",
        "requests",
        "websocket",      # websocket-client
        "colorama",
        "dotenv",         # python-dotenv
        "yaml",           # PyYAML
        "openpyxl",
    ],
    "include_files": [
        "config.yaml",
        ".env.example",
    ],
}

setup(
    name="Alpha Trading Bot",
    version="1.0.0",
    description="NIFTY intraday options trading bot -- EMA(9)/EMA(21) crossover, Angel One (SmartAPI)",
    options={"build_exe": build_exe_options},
    executables=[Executable(script_name, target_name=app_name)],
)
