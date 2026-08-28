import os
import sys
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)
from mainfunctions import (
    get_local_directory_root_files_list,
    get_loaf_remote_directory_root_files_list,
    get_tram_remote_directory_root_files_list,
    get_tram_t2_clusters_rdataframe,
    get_loaf_diagnostics_rdataframe,
    get_loaf_t2_tram_rdataframe
)

root_list1 = get_loaf_remote_directory_root_files_list(runspec="3500-3561",print_folder_summary=False)
rdataframe1 = get_loaf_t2_tram_rdataframe(
    selected_files = root_list1,
    number_of_threads = 8,
    add_run_subrun_columns = True,
    debug_preview_dataframe = False
)
rdataframe2 = get_loaf_t2_tram_rdataframe(
    selected_files = root_list1,
    number_of_threads = 8,
    add_run_subrun_columns = False,
    debug_preview_dataframe = False
)
rdataframe3 = get_loaf_diagnostics_rdataframe(
    selected_files = root_list1,
    number_of_threads = 16,
    add_run_subrun_columns = True,
    debug_preview_dataframe = True
)
rdataframe4 = get_loaf_t2_tram_rdataframe(
    selected_files = root_list1,
    number_of_threads = 8,
    required_columns = {"Runnumber","Itime"},
    add_run_subrun_columns = False,
    debug_preview_dataframe = False
)
get_loaf_remote_directory_root_files_list(runspec="3500_7-3500_11",print_folder_summary=False)
tram_root_list1 = get_tram_remote_directory_root_files_list(runspec="3500_7-3510_11",print_folder_summary=False)
rdataframe5 = get_tram_t2_clusters_rdataframe(
    selected_files = tram_root_list1,
    number_of_threads = 8,
    add_run_subrun_columns = True,
    debug_preview_dataframe = False
)
######## No Multi-threading ###################
rdataframe6 = get_tram_t2_clusters_rdataframe(
    selected_files = tram_root_list1,
    add_run_subrun_columns = True,
    debug_preview_dataframe = False
)
get_tram_remote_directory_root_files_list(runspec="3500-3501,3503-3504",print_folder_summary=False)
get_loaf_remote_directory_root_files_list(runspec="3500_7-3500_8,3503",print_folder_summary=False)
get_loaf_remote_directory_root_files_list(runspec="3500_7-3500_8,3503_1",print_folder_summary=True)

get_local_directory_root_files_list(local_directory="/data0/kfritzalas/",runspec="3500-3561",print_folder_summary=False)
get_local_directory_root_files_list(local_directory="/data0/kfritzalas/",runspec="3500_7-3500_11",print_folder_summary=False)
get_local_directory_root_files_list(local_directory="/data0/kfritzalas/",runspec="3500_7-3510_11",print_folder_summary=False)
get_local_directory_root_files_list(local_directory="/data0/kfritzalas/",runspec="3500-3501,3503-3504",print_folder_summary=False)
get_local_directory_root_files_list(local_directory="/data0/kfritzalas/",runspec="3500_7-3500_8,3503",print_folder_summary=False)
get_local_directory_root_files_list(local_directory="/data0/kfritzalas/",runspec="3500_7-3500_8,3503_1",print_folder_summary=True)