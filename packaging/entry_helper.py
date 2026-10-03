"""sidekick-helper.exe: the app's hidden `scout` commands, such as the data refresh.

The installed app starts it in the background (scout/app/update.py, `scout_command`); it has
no window of its own. A PyInstaller entry point (packaging/sidekick.spec).
"""

from scout.cli import app

if __name__ == "__main__":
    app(prog_name="sidekick-helper")
