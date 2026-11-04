"""Ярлык «Ichigo» (на рабочем столе или в указанной папке): запуск окна программы без консоли.

Запуск: .venv\\Scripts\\python.exe app\\shortcut.py [папка]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def make(folder=None):
    env = dict(os.environ,
               ICHIGO_LNK=os.path.join(folder or "", "Ichigo.lnk"),
               ICHIGO_TARGET=os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe"),
               ICHIGO_ARGS=f'"{os.path.join(HERE, "gui.py")}"',
               ICHIGO_ROOT=ROOT,
               ICHIGO_ICON=os.path.join(HERE, "ichigo.ico"))
    # пути передаём через переменные окружения — так не нужно экранировать кавычки для PowerShell
    script = ("$lnk = $env:ICHIGO_LNK; if (-not [IO.Path]::IsPathRooted($lnk)) "
              "{ $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) $lnk }; "
              "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); "
              "$s.TargetPath = $env:ICHIGO_TARGET; $s.Arguments = $env:ICHIGO_ARGS; "
              "$s.WorkingDirectory = $env:ICHIGO_ROOT; $s.IconLocation = $env:ICHIGO_ICON; "
              "$s.Description = 'Ichigo - live Japanese subtitles'; $s.Save(); $lnk")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         env=env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


if __name__ == "__main__":
    print(make(sys.argv[1] if len(sys.argv) > 1 else None))
