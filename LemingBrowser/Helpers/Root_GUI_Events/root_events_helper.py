import asyncio
import contextlib
import ROOT
import gc
from IPython import get_ipython
import os
import sys

current = os.path.dirname(
    os.path.realpath(__file__)
)
parent = os.path.dirname(
    current
)
sys.path.append(
    parent
)
from doVolumeCuts.temporaryfiles import (
    delete_registered_volume_cut_files,
)

_ROOT_GUI_TASK = None

def start_root_gui_events():
    global _ROOT_GUI_TASK

    ip = get_ipython()

    for cb in list(ip.events.callbacks.get("post_execute", [])):
        owner = getattr(cb, "__self__", None)

        if owner is not None and owner.__class__.__name__ == "CaptureDrawnPrimitives":
            ip.events.unregister("post_execute", cb)
            print("Disabled JupyROOT inline canvas rendering")

    if _ROOT_GUI_TASK is None or _ROOT_GUI_TASK.done():
        _ROOT_GUI_TASK = asyncio.create_task(
            _process_root_gui_events()
        )

async def exit() -> None:
    if ROOT.IsImplicitMTEnabled():
        ROOT.DisableImplicitMT()

    _close_root_canvases()

    await _stop_root_gui_events()

    # ------------------------------------------------------------
    # Delete ONLY files explicitly registered as doVolumeCuts
    # temporary outputs.
    # ------------------------------------------------------------
    delete_registered_volume_cut_files()

    gc.collect()

    print("All ROOT canvases closed and ROOT objects released.")

async def _process_root_gui_events(interval=0.03):
    while True:
        ROOT.gSystem.ProcessEvents()
        await asyncio.sleep(interval)

async def _stop_root_gui_events():
    global _ROOT_GUI_TASK

    if _ROOT_GUI_TASK is None:
        return

    _ROOT_GUI_TASK.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await _ROOT_GUI_TASK

    _ROOT_GUI_TASK = None


def _close_root_canvases():
    """Close all currently registered ROOT canvases."""
    canvases = ROOT.gROOT.GetListOfCanvases()

    # Copy first because Close() modifies GetListOfCanvases().
    for canvas in list(canvases):
        canvas.Close()

    ROOT.gSystem.ProcessEvents()