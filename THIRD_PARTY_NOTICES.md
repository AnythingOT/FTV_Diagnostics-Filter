# Third-party notices

FTV Diagnostics Filter is licensed under the MIT licence (see `LICENSE`). It uses only the Python
standard library, so running it from source needs nothing from others besides Python itself.

## Runtime bundled in `FTV_Diagnostics_Filter.exe`

| Component | Used for | Licence | Source |
|---|---|---|---|
| Python, incl. tkinter | the program itself and its GUI | PSF License | https://www.python.org/ |
| Tcl/Tk | the toolkit behind tkinter | Tcl/Tk licence (BSD-style) | https://www.tcl-lang.org/ |
| PyInstaller bootloader | starts the exe | GPL-2.0-or-later with the bootloader exception | https://pyinstaller.org/ |

The exe contains a copy of Python and Tcl/Tk, so passing it on means passing their licences on
too. The release workflow writes their full texts to `THIRD_PARTY_LICENSES.txt` (made by
`tools/collect_licenses.py`) and attaches it to every release next to the exe. **Give it along
with the exe.** The PyInstaller bootloader exception lets the built exe be shared under any
licence; it does not make the exe GPL.

## Trademarks

Rockwell Automation, FactoryTalk and FactoryTalk View are trademarks of Rockwell Automation, Inc.
They are used here only to say which software this tool reads exports from. FTV Diagnostics
Filter is not affiliated with or endorsed by Rockwell Automation.
