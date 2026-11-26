"""Shared resource path for source and PyInstaller builds."""
from pathlib import Path
import sys

def resource_path(name):
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent)) / 'assets' / name

def set_window_icon(window):
    import tkinter as tk
    # iconphoto works on Windows and Linux; retain the Tk image reference.
    window._app_icon = tk.PhotoImage(master=window,file=str(resource_path('WallsEC2.png')))
    window.iconphoto(True,window._app_icon)
    return True
