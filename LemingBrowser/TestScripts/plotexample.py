from pathlib import Path
import asyncio
import sys

sys.path.append(str(Path.cwd().parent))

from mainfunctions import *
import ROOT

async def process_root_gui_events(interval=0.03):
    #We need this process to run until the user finishes with the canvas. If this doesn't apply
    # the ROOT Canvas would be frozen !!!
    try:
        ROOT.gROOT.SetBatch(False)
        while True:
            ROOT.gSystem.ProcessEvents()
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


async def main():

    root_list1 = get_local_directory_root_files_list(
        runspec="3500-3561",
        print_folder_summary=False,
        local_directory="/data0/kfritzalas/tram_new",
    )

    temperatures_rdf = get_general_rdataframe(
        root_list1,
        "temperatures",
        number_of_threads=8,
    )

    temperatures_histograms = get_tram_histograms(
        dataframe=[
            temperatures_rdf,
        ],
        dataframe_labels=[
            "rdf",
        ],
        quantities=[
            "temp_50K",
            "temp_4K",
            "temp_still",
            "temp_MXC",
            "temp_LN2Bucket",
            "temp_si_strips",
            "temp_chamber",
        ],
    )

    plot_tram_histograms(temperatures_histograms)

    # Start servicing ROOT GUI events
    gui_task = asyncio.create_task(
        process_root_gui_events()
    )

    try:
        await asyncio.to_thread(
            input,
            "Press Enter to continue..."
        )

    finally:
        gui_task.cancel()

        try:
            await gui_task
        except asyncio.CancelledError:
            pass

        await exit_leming_browser()


if __name__ == "__main__":
    asyncio.run(main())