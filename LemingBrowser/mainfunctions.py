from pathlib import Path
from typing import Any, Iterable
from typing import Optional
from Helpers.mount_and_load_data.loading import (
    load_remote_resolved_root_files,
    load_local_resolved_root_files
)
from Helpers.RDataFrame.rdataframehelper import (
    create_rdataframe
)
from Helpers.Histograms.loafhisto import (
    create_loaf_histograms
)
from Helpers.Fit.gumbel import fit_gumbel
from Helpers.Plot.plotloaf import (
    plot_loaf_histo
)
from Helpers.Root_GUI_Events.root_events_helper import (
    start_root_gui_events,
    exit
)
from Helpers.Filter.general_apply_filter import (
    global_filter_cut_rdataframe
)
from Helpers.Filter.filter_per_detector import (
    detector_filter_cut_rdataframe
)
from Helpers.Filter.detector_event_filter_cut_rdataframe import (
    detector_event_filter_cut_rdataframe
)
from Helpers.Filter.column_filter_cut_rdataframe import (
    column_filter_cut_rdataframe
)
from Helpers.Histograms.tramhisto import (
    create_tram_histograms
)
from Helpers.Plot.plottram import (
    plot_tram_histo
)
from Helpers.RDataFrame.create_new_column import define_columns
from Helpers.Ranging.create_ranging_points import calculate_entries_per_muon_hit
from Helpers.Ranging.plot_ranging_points import plot_sfhe_comparison
from Helpers.Provenance.plot_provenance import (
    plot_histogram_provenance
)
from Helpers.Histograms.histogramoperations import (
    add_histograms,
    subtract_histograms,
    multiply_histograms,
    divide_histograms,
    Normalize,
    lifetime_correction_histo,
    background_subtraction,
    get_muSR
)
from Helpers.Coincidence.tram_straight_coincidence import (
    define_tram_straight_coincidence_columns
)
from Helpers.Coincidence.coincidence_loaf_old import (
    coincidence_loaf_old
)
from Helpers.doVolumeCuts.load_run_volume_cuts import (
    load_run_volume_cuts
)

def init_canvas_events():
    start_root_gui_events()

def addHistograms(
    histograms: list[Any],
    saveHistograms: bool = False,
    outputFileName: str | None = None   
):
    added_histo = add_histograms(
        histograms=histograms,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return added_histo

def subtractHistograms(
    histograms: list[Any],
    saveHistograms: bool = False,
    outputFileName: str | None = None   
):
    subtracted_histo = subtract_histograms(
        histograms=histograms,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return subtracted_histo

def multiplyHistograms(
    histograms: list[Any],
    saveHistograms: bool = False,
    outputFileName: str | None = None   
):
    multiplied_histo = multiply_histograms(
        histograms=histograms,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return multiplied_histo

def devideHistograms(
    histograms: list[Any],
    saveHistograms: bool = False,
    outputFileName: str | None = None   
):
    devided_histo = divide_histograms(
        histograms=histograms,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return devided_histo

def Normalize_Histograms(
    histograms: Any | list[Any],
    saveHistograms: bool = False,
    outputFileName: str | None = None   
):
    normalized_histo = Normalize(
        histograms=histograms,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return normalized_histo

def lifetime_correction_histograms(
    histograms: Any | list[Any],
    lifetime: float = 2193.0,
    saveHistograms: bool = False,
    outputFileName: str | None = None
):
    lifetime_corrected_histo = lifetime_correction_histo(
        histograms=histograms,
        lifetime=lifetime,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return lifetime_corrected_histo

def background_subtraction_histograms(
    histograms: Any | list[Any],
    bkg_min: float = 0.0, 
    bkg_max: float = 1000.0,
    saveHistograms: bool = False,
    outputFileName: str | None = None
):
    background_fixed_histo = background_subtraction(
        histograms=histograms,
        bkg_min=bkg_min,
        bkg_max=bkg_max,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return background_fixed_histo

def calculate_muSR(
    hist1_or_groups: Any | list[tuple[Any, Any]],
    hist2: Any | None = None,
    saveHistograms: bool = False,
    outputFileName: str | None = None      
):
    muSR_histo = get_muSR(
        hist1_or_groups=hist1_or_groups,
        hist2=hist2,
        saveHistograms=saveHistograms,
        outputFileName=outputFileName
    )
    return muSR_histo

def plot_tram_histograms(
    histograms: Any,
    quantity: str | None = None,
    dataframe_label: str = "DataFrame1",
    title: str | None = None,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    saveCanvas: bool = False,
    outputFileName: str | Path | None = None,
    outputFormats: str | Iterable[str] = None,
    show_3d: bool = False,
    show_provenance: bool = False,
) -> dict[str, Any]:
    canvas_info = plot_tram_histo(
        histograms=histograms,
        quantity=quantity,
        dataframe_label=dataframe_label,
        title = title,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        saveCanvas=saveCanvas,
        outputFileName=outputFileName,
        outputFormats=outputFormats,
        show_3d = show_3d,
        show_provenance=show_provenance
    )
    return canvas_info

def get_tram_histograms(
    dataframe: Any | list[Any],
    dataframe_labels: list[str],
    quantities: str | list[str],
    bins: int | list[int | None] | None = None,
    ranges: (
        tuple[float, float]
        | list[float]
        | list[tuple[float, float] | list[float] | None]
        | None
    ) = None,
    histogram_config_filename: str | Path = (
        "tram_histogram_defaults.json"
    ),
    saveHistograms: bool = False,
    outputFileName: str = None
):
    all_histograms = create_tram_histograms(
        dataframe=dataframe,
        dataframe_labels=dataframe_labels,
        quantities=quantities,
        bins=bins,
        ranges=ranges,
        histogram_config_filename=histogram_config_filename,
        saveHistograms=saveHistograms,
        outputFileName = outputFileName
    )
    return all_histograms

def plot_loaf_histograms(
    histograms: Any,
    quantity: str | None = None,
    dataframe_label: str = "DataFrame1",
    title: str | None = None,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    saveCanvas: bool = False,
    outputFileName: str | Path | None = None,
    outputFormats: str | Iterable[str] = None,
    show_3d: bool = False,
    show_provenance: bool = False
) -> dict[str, Any]:
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    canvas_info = plot_loaf_histo(
        histograms=histograms,
        quantity=quantity,
        dataframe_label=dataframe_label,
        title = title,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        saveCanvas=saveCanvas,
        outputFileName=outputFileName,
        outputFormats=outputFormats,
        show_3d=show_3d,
        show_provenance=show_provenance
    )
    return canvas_info

def get_loaf_histograms(
    dataframe: Any | list[Any],
    dataframe_labels: list[str],
    quantities: str | list[str],
    bins: int | list[int | None] | None = None,
    ranges: (
        tuple[float, float]
        | list[float]
        | list[tuple[float, float] | list[float] | None]
        | None
    ) = None,
    histogram_config_filename: str | Path = (
        "loaf_histogram_defaults_general.json"
    ),
    saveHistograms: bool = False,
    outputFileName: str = None
):
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    all_histograms = create_loaf_histograms(
        dataframe=dataframe,
        dataframe_labels=dataframe_labels,
        quantities=quantities,
        bins=bins,
        ranges=ranges,
        histogram_config_filename=histogram_config_filename,
        saveHistograms=saveHistograms,
        outputFileName = outputFileName
    )
    return all_histograms

def apply_tram_straight_coincidence(
    dataframes: Any | list[Any],
    settings: dict[str, float | None] | None,
) -> Any | list[Any]:
    coincidence_dataframes = define_tram_straight_coincidence_columns(
        dataframes=dataframes,
        settings=settings
    )
    return coincidence_dataframes

def apply_loaf_coincidence_old(
   dataframes: Any | list[Any],
   detectors: list[str],
   detector_column: str = "Idetname",
   event_column: str = "IEventNb",
   run_column: str = "Runnumber",
   subrun_column: str = "Subrunnumber",
   time_column: str = "Itime",
) -> Any | list[Any]:
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    #****** Deprecated with the new loaf format ***********
    coincidence_dataframes = coincidence_loaf_old(
        dataframes=dataframes,
        detectors=detectors,
        detector_column=detector_column,
        event_column=event_column,
        run_column=run_column,
        subrun_column=subrun_column,
        time_column=time_column
    )    
    print("Detectors Coincidence Applied")
    return coincidence_dataframes 

def apply_per_detector_filter(
    dataframes: Any | list[Any],
    detectors: str | list[str],
    cut_filters: str | list[str],
    detector_column: str = "Idetname",
) -> Any | list[Any]:
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    #****** Deprecated with the new loaf format ***********
    filtered_dataframes = detector_filter_cut_rdataframe(
        dataframes=dataframes,
        detectors=detectors,
        cut_filters=cut_filters,
        detector_column=detector_column
    )
    print("Per Detector Filtering Applied")
    return filtered_dataframes

def apply_detector_event_filter_cut_rdataframe(
    dataframes: Any | list[Any],
    detectors: str | list[str],
    cut_filters: str | list[str],
    detector_column: str = "Idetname",
    event_column: str = "IEventNb",
    run_column: str = "Runnumber",
    subrun_column: str = "Subrunnumber",
) -> Any | list[Any]:   
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    #****** Deprecated with the new loaf format ***********
    filtered_dataframes = detector_event_filter_cut_rdataframe(
        dataframes=dataframes,
        detectors=detectors,
        cut_filters=cut_filters,
        detector_column=detector_column,
        event_column=event_column,
        run_column=run_column,
        subrun_column=subrun_column
    )
    print("Detector Event filtering executed")
    return filtered_dataframes

def apply_global_filter(
    dataframes: list[Any],
    cut_filter: str | list[str] | None,
) -> list[Any]:
    
    filtered_dataframes = global_filter_cut_rdataframe(
        dataframes=dataframes,
        cut_filter=cut_filter
    )
    print("Filters Applied")
    return filtered_dataframes

def apply_column_filter(
    dataframes: list[Any],
    cut_filter: str | list[str] | None,
) -> list[Any]:

    filtered_dataframes = column_filter_cut_rdataframe(
        dataframes=dataframes,
        cut_filter=cut_filter,
    )

    print("Column Filters Applied")

    return filtered_dataframes

def create_rdataframe_new_column(
    dataframes: Any | list[Any],
    definitions: dict[str, str],
):
    applied_rdataframes = define_columns(
        dataframes=dataframes,
        definitions=definitions
    )
    return applied_rdataframes

def get_tram_t2_clusters_rdataframe(
    selected_files: list[Path],
    tree_name: str = "t2_clusters",
    number_of_threads: Optional[int] = None,
    required_columns: Optional[set[str]] = None,
    add_run_subrun_columns: bool = False,
    debug_preview_dataframe: bool = False,
):
    rdataframe = create_rdataframe(
        selected_files = selected_files,
        tree_name = tree_name,
        number_of_threads = number_of_threads,
        required_columns = required_columns,
        add_run_subrun_columns = add_run_subrun_columns,
        debug_preview_dataframe = debug_preview_dataframe
    )
    return rdataframe

def get_loaf_t2_tram_rdataframe(
    selected_files: list[Path],
    tree_name: str = "t2_tram",
    number_of_threads: Optional[int] = None,
    required_columns: Optional[set[str]] = None,
    add_run_subrun_columns: bool = False,
    debug_preview_dataframe: bool = False,
):
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    rdataframe = create_rdataframe(
        selected_files = selected_files,
        tree_name = tree_name,
        number_of_threads = number_of_threads,
        required_columns = required_columns,
        add_run_subrun_columns = add_run_subrun_columns,
        debug_preview_dataframe = debug_preview_dataframe
    )
    return rdataframe

def get_loaf_diagnostics_rdataframe(
    selected_files: list[Path],
    tree_name: str = "diagnostics",
    number_of_threads: Optional[int] = None,
    required_columns: Optional[set[str]] = None,
    add_run_subrun_columns: bool = False,
    debug_preview_dataframe: bool = False,
):
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    rdataframe = create_rdataframe(
        selected_files = selected_files,
        tree_name = tree_name,
        number_of_threads = number_of_threads,
        required_columns = required_columns,
        add_run_subrun_columns = add_run_subrun_columns,
        debug_preview_dataframe = debug_preview_dataframe
    )
    return rdataframe

def get_general_rdataframe(
    selected_files: list[Path],
    tree_name: str,
    number_of_threads: Optional[int] = None,
    required_columns: Optional[set[str]] = None,
    add_run_subrun_columns: bool = False,
    debug_preview_dataframe: bool = False,
):
    rdataframe = create_rdataframe(
        selected_files = selected_files,
        tree_name = tree_name,
        number_of_threads = number_of_threads,
        required_columns = required_columns,
        add_run_subrun_columns = add_run_subrun_columns,
        debug_preview_dataframe = debug_preview_dataframe
    )
    return rdataframe

def get_loaf_remote_directory_root_files_list(
    runspec: str,
    host: str = "lepp-c-3po",
    user: str = "leming",
    remote_directory: str = "data0/leming/BT2025/kosmas/loaf",
    print_folder_summary: bool = False
):
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    root_files = load_remote_resolved_root_files(
        runspec=runspec,
        host=host,
        user=user,
        remote_directory=remote_directory,
        print_folder_summary=print_folder_summary
    )
    return root_files

def get_tram_remote_directory_root_files_list(
    runspec: str,
    host: str = "lepp-c-3po",
    user: str = "leming",
    remote_directory: str = "data0/leming/BT2025/kosmas/tram",
    print_folder_summary: bool = False
):
    root_files = load_remote_resolved_root_files(
        runspec=runspec,
        host=host,
        user=user,
        remote_directory=remote_directory,
        print_folder_summary=print_folder_summary
    )
    return root_files

def get_local_directory_root_files_list(
    runspec: str,
    local_directory: str,
    print_folder_summary: bool = False
):
    root_files = load_local_resolved_root_files(
        runspec=runspec,
        local_directory=local_directory,
        print_folder_summary=print_folder_summary
    )
    return root_files

def get_rdataframe_volume_cuts(
    runspec: str,
    project_directory: str | Path,
    isRemoteProjectDirectory: bool = False,
    number_of_threads: int | None = None,
    tree_name: str = "t2_tracks",
    host: str = "lepp-c-3po",
    user: str = "leming",
    root_files_local_directory: str | Path | None = None,
    root_files_remote_directory: str = "data0/leming/BT2025/kosmas/tram",
    output_file: str | Path = "output_dovolumecuts.root",
    xmin: float = -6.0,
    xmax: float = 6.0,
    ymin: float = 17.0,
    ymax: float = 29.0,
    zmin: float = 10.0,
    zmax: float = 15.0,
    tmin: Optional[float] = None,
    tmax: Optional[float] = None,
    rebuild: bool = False,
    print_folder_summary: bool = False,
    conda_base: str | Path = (
        "/home/leming/packages/miniforge3"
    ),
    conda_environment: str = "leming",
):
    rdataframe = load_run_volume_cuts(
        runspec=runspec,
        project_directory=project_directory,
        isRemoteProjectDirectory=isRemoteProjectDirectory,
        tree_name=tree_name,
        host=host,
        user=user,
        local_directory=root_files_local_directory,
        remote_directory=root_files_remote_directory,
        output_file=output_file,
        xmin=xmin,
        xmax=xmax,
        ymin=ymin,
        ymax=ymax,
        zmin=zmin,
        zmax=zmax,
        tmin=tmin,
        tmax=tmax,
        rebuild=rebuild,
        print_folder_summary=print_folder_summary,
        number_of_threads=number_of_threads,
        conda_base=conda_base,
        conda_environment=conda_environment
    )
    return rdataframe

def log_histograms(
    histograms: Any | list[Any],
    save: bool = False,
    output_filename: str | Path = "histogram_provenance",
    output_format: str = "png",
    view: bool = True,
)-> Path :
    plot_histogram_provenance(
        histograms=histograms,
        save=save,
        output_filename=output_filename,
        output_format=output_format,
        view=view
    )

async def exit_leming_browser() -> None:
    await exit()


############################# Ranging Plots #################################################

def get_ranging_points(
    muon_dataframes: list,
    muon_number_dataframes: list,
    energies: list[float],
) -> list[tuple[float, float]]:
    ranging_points = calculate_entries_per_muon_hit(
        muon_dataframes=muon_dataframes,
        muon_number_dataframes=muon_number_dataframes,
        energies=energies
    )
    return ranging_points

def plot_ranging_points(
    with_sfhe: list[tuple[float, float]],
    without_sfhe: list[tuple[float, float]],
    title: str = "Cooldown",
    xlabel: str = "Beam momentum [MeV]",
    ylabel: str = "#Coincidences / #Entries in the muon detector",
    save_path: str | None = None,
):
    fig, ax = plot_sfhe_comparison(
        with_sfhe=with_sfhe,
        without_sfhe=without_sfhe,
        title=title,
        xlabel=xlabel,
        ylabel=ylabel,
        save_path=save_path
    )
    return fig, ax

def fit_gumbel_histo(
    histograms,
    fit_range=(0, 10000),
    gauss_range=None,
    scale_limits=(500, 5000),
    amplitude_limits=(1000, 1e7),
    mu_limits=(0.1, 100000),
    line_color=None,
):
    fitted_histo = fit_gumbel(
        histograms=histograms,
        fit_range=fit_range,
        gauss_range=gauss_range,
        scale_limits=scale_limits,
        amplitude_limits=amplitude_limits,
        mu_limits=mu_limits,
        line_color=line_color
    )
    return fitted_histo