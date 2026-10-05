"""Build the plugin dialog outside KiCad and check its controls (KiCad Python).

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests/ui_smoke.py

No screenshot: grabbing the screen would capture whatever else is displayed.
Checks: dialog builds, colour controls exist, options round-trip through
onGenerateButtonClick (the processing thread is stubbed).
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pcbnew  # type: ignore  # noqa: E402
import wx  # noqa: E402

board = pcbnew.LoadBoard(os.path.join(ROOT, "tests", "boards", "T2.kicad_pcb"))
pcbnew.GetBoard = lambda: board  # the dialog reads the board opened in pcbnew

# Skip plugins/__init__.py: with pcbnew loaded it would register the action
# plugin, which asserts outside the KiCad application.
package = types.ModuleType("plugins")
package.__path__ = [os.path.join(ROOT, "plugins")]
sys.modules["plugins"] = package

import plugins.plugin as plugin_module  # noqa: E402
from plugins.options import COLOR_FIT_OPT, TOP_IMAGE_OPT, BOTTOM_IMAGE_OPT  # noqa: E402


def main():
    app = wx.App(False)
    plugin_module.Plugin()
    captured = {}
    plugin_module.ProcessThread = lambda wxobj, options, openBrowser=True: captured.update(options)
    plugin_module.save_user_options = lambda options: None  # don't write next to the test board
    form = plugin_module.KiCadToJLCForm()
    top = os.path.join(ROOT, "tests", "img", "logo.png")
    form.mTopImagePicker.SetPath(top)
    form.mColorFitCheckbox.SetValue(True)
    form.Layout()
    size = form.GetSize()
    form.onGenerateButtonClick(None)
    ok = (captured.get(TOP_IMAGE_OPT) == top and captured.get(BOTTOM_IMAGE_OPT) == ""
          and captured.get(COLOR_FIT_OPT) == "contain")
    print("dialog size:", tuple(size), "options:", {k: captured.get(k) for k in (TOP_IMAGE_OPT, BOTTOM_IMAGE_OPT, COLOR_FIT_OPT)})
    print("UI SMOKE", "OK" if ok else "FAILED")
    form.Destroy()
    app.Destroy()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
