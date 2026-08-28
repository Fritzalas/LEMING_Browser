# LOAD DATA FUNCTIONS

# Scan a Remote LOAF Directory for ROOT Files by Run

`get_loaf_remote_directory_root_files_list` searches a LOAF data
directory on a remote virtual machine (via using gio mounting) and returns the ROOT files that match a
run specification.

The function connects over gio mounting, scans the requested directory
recursively, filters files by run and subrun number, and returns the
matching paths in natural sort order.

The returned list can be passed directly to the LOAF RDataFrame helper
functions.

## Function signature

``` python
get_loaf_remote_directory_root_files_list(
    runspec,
    host="lepp-c-3po",
    user="leming",
    remote_directory="data0/leming/BT2025/kosmas/loaf",
    print_folder_summary=False
)
```

## Parameters

### `runspec`

**Type:** `str`\
**Required:** Yes

Specifies the runs, or runs and subruns, to include.

Supported forms include:

``` text
3500-3561
3500-3510,3520-3530
3500_7-3510_11
```

For example, `"3500-3561"` selects a continuous run range, while
comma-separated ranges can be used when the requested runs are not
contiguous. Underscore notation can be used when selection needs to
include subrun numbers.

### `host`

**Type:** `str`\
**Default:** `"lepp-c-3po"`

Hostname or IP address of the machine containing the LOAF data.

The host must be reachable over SSH from the machine running the code.

### `user`

**Type:** `str`\
**Default:** `"leming"`

Username used for the SSH connection.

### `remote_directory`

**Type:** `str`\
**Default:** `"data0/leming/BT2025/kosmas/loaf"`

Directory containing the LOAF data on the remote machine.

The directory is scanned recursively, so matching ROOT files may be
located in subdirectories.

### `print_folder_summary`

**Type:** `bool`\
**Default:** `False`

Prints a short summary of the scanned folder structure and the files
that were matched.

This is useful when checking a new run range or remote directory before
loading the data.

## Return value

``` python
list[Path]
```

Returns the matching ROOT file paths as `Path` objects, ordered using
natural sorting.

These paths refer to files on the remote machine rather than files
copied to the local filesystem.

## Examples

### Load a continuous run range

``` python
from mainfunctions import get_loaf_remote_directory_root_files_list

root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3561"
)

print(f"Found {len(root_files)} ROOT files")

if root_files:
    print(root_files[0])
```

### Load separate run ranges

``` python
root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3510,3520-3530",
    print_folder_summary=True
)
```

### Select runs at subrun level

``` python
root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500_7-3510_11"
)
```

### Use another remote host or data directory

``` python
root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3561",
    host="myserver.example.com",
    user="analyst",
    remote_directory="data1/experiment/loaf",
    print_folder_summary=True
)
```

## Using the result

The returned paths can be passed directly to the LOAF RDataFrame
loaders:

``` python
root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3561"
)

df = get_loaf_t2_tram_rdataframe(root_files)
```

They can also be used with `get_loaf_diagnostics_rdataframe` when
working with diagnostics data.

There is no need to copy the ROOT files locally first; the loader
functions handle access to the remote files.

## Notes

-   For the first time, gio mounting must happen from the terminal, so the user accepts the machine certificate
-   Use `print_folder_summary=True` when checking an unfamiliar
    directory or run range (takes more time if you select this option).
-   An empty result usually means that no files matched the run
    specification, or that the remote directory does not point to the
    expected LOAF data.
-   The paths returned by this function describe files on the remote
    host.

# Scan a Remote TRAM Directory for ROOT Files by Run

`get_tram_remote_directory_root_files_list` searches a TRAM data
directory on a remote virtual machine (via GIO mounting) and returns the
ROOT files that match a run specification.

The function accesses the remote directory through the GIO mount, scans
the requested directory for matching files, filters them by run and
subrun number, and returns the matching paths in natural sort order.

The returned list can be passed directly to the TRAM RDataFrame helper
functions.

## Function signature

``` python
get_tram_remote_directory_root_files_list(
    runspec,
    host="lepp-c-3po",
    user="leming",
    remote_directory="data0/leming/BT2025/kosmas/tram",
    print_folder_summary=False
)
```

## Parameters

### `runspec`

**Type:** `str`\
**Required:** Yes

Specifies the runs, or runs and subruns, to include.

Supported forms include:

``` text
3500-3561
3500-3510,3520-3530
3500_7-3510_11
```

For example, `"3500-3561"` selects a continuous run range, while
comma-separated ranges can be used when the requested runs are not
contiguous. Underscore notation can be used when the selection needs to
include subrun numbers.

The following:

``` text
3500_7-3510_11
```

selects files from subrun 7 of run 3500 through subrun 11 of run 3510.

### `host`

**Type:** `str`\
**Default:** `"lepp-c-3po"`

Hostname or IP address of the remote machine containing the TRAM data.

The machine must be accessible from the system where the GIO mount is
created.

### `user`

**Type:** `str`\
**Default:** `"leming"`

Username used when mounting the remote machine through GIO.

### `remote_directory`

**Type:** `str`\
**Default:** `"data0/leming/BT2025/kosmas/tram"`

Directory containing the TRAM data on the remote machine.

The function searches this directory for ROOT files matching the
provided `runspec`.

### `print_folder_summary`

**Type:** `bool`\
**Default:** `False`

Prints a summary of the scanned folder structure and the files that were
matched.

This is useful when checking a new run range or remote directory before
loading the data. Enabling it can make the directory scan take longer.

## Return value

``` python
list[Path]
```

Returns the matching TRAM ROOT file paths as `Path` objects, ordered
using natural sorting.

These paths refer to files on the remote machine through the mounted
filesystem rather than files copied to the local machine.

## Examples

### Load a continuous run range

``` python
from mainfunctions import get_tram_remote_directory_root_files_list

tram_files = get_tram_remote_directory_root_files_list(
    runspec="3500-3561"
)

print(f"Found {len(tram_files)} TRAM ROOT files")

if tram_files:
    print(tram_files[0])
```

### Select runs at subrun level

``` python
tram_files = get_tram_remote_directory_root_files_list(
    runspec="3500_7-3510_11"
)
```

### Load separate run ranges

``` python
tram_files = get_tram_remote_directory_root_files_list(
    runspec="3500-3510,3520-3530",
    print_folder_summary=True
)
```

### Use another remote host or data directory

``` python
tram_files = get_tram_remote_directory_root_files_list(
    runspec="3500-3561",
    host="myserver.example.com",
    user="analyst",
    remote_directory="data1/experiment/tram_alt",
    print_folder_summary=True
)
```

## Using the result

The returned paths can be passed directly to the TRAM RDataFrame
loaders:

``` python
tram_files = get_tram_remote_directory_root_files_list(
    runspec="3500-3561"
)

df = get_tram_t2_clusters_rdataframe(tram_files)
```

There is no need to copy the ROOT files locally first. The files are
accessed through the mounted remote filesystem.

## Notes

-   The first GIO mount should be done manually from the terminal so
    that the user can accept the remote machine certificate.
-   Use `print_folder_summary=True` when checking an unfamiliar
    directory or run range. This option can make the scan take longer.
-   An empty result usually means that no files matched the run
    specification, or that the remote directory does not point to the
    expected TRAM data.
-   The paths returned by this function describe files on the remote
    host through the GIO mount.

  # List Local Directory ROOT Files by Run Specification

`get_local_directory_root_files_list` searches a local directory and
returns the ROOT files that match a run specification.

The function scans the requested directory, filters files by run and
subrun number, and returns the matching paths in natural sort order.

The returned list can be passed directly to the LEMING Browser
RDataFrame helper functions.

## Function signature

``` python
get_local_directory_root_files_list(
    runspec,
    local_directory,
    print_folder_summary=False
)
```

## Parameters

### `runspec`

**Type:** `str`\
**Required:** Yes

Specifies the runs, or runs and subruns, to include.

Supported forms include:

``` text
3500-3561
3500-3501,3503-3504
3500_7-3510_11
```

For example, `"3500-3561"` selects a continuous run range, while
comma-separated ranges can be used when the requested runs are not
contiguous. Underscore notation can be used when the selection needs to
include subrun numbers.

A specification such as:

``` text
3500-3501,3503-3504
```

selects runs 3500, 3501, 3503, and 3504, while skipping run 3502.

### `local_directory`

**Type:** `str`\
**Required:** Yes

Path to the local directory containing the ROOT files.

The function searches this directory for files matching the supplied
`runspec`.

For example:

``` text
/path/to/local/data
```

### `print_folder_summary`

**Type:** `bool`\
**Default:** `False`

Prints a summary of the scanned folder structure and the files that were
matched.

This is useful when checking a new directory or run range before loading
the data. Enabling it can make the directory scan take longer.

## Return value

``` python
list[Path]
```

Returns the matching ROOT file paths as `Path` objects, ordered using
natural sorting.

The returned paths point directly to files on the local filesystem.

## Examples

### Load a continuous run range

``` python
from mainfunctions import get_local_directory_root_files_list

root_files = get_local_directory_root_files_list(
    runspec="3500-3561",
    local_directory="/path/to/local/data"
)

print(f"Found {len(root_files)} ROOT files")

if root_files:
    print(root_files[0])
```

### Load separate run ranges

``` python
root_files = get_local_directory_root_files_list(
    runspec="3500-3501,3503-3504",
    local_directory="/path/to/local/data",
    print_folder_summary=True
)
```

### Select runs at subrun level

``` python
root_files = get_local_directory_root_files_list(
    runspec="3500_7-3510_11",
    local_directory="/path/to/local/data"
)
```

### Pass the result to an RDataFrame loader

``` python
from mainfunctions import (
    get_local_directory_root_files_list,
    get_loaf_t2_tram_rdataframe,
)

root_files = get_local_directory_root_files_list(
    runspec="3500-3561,3570-3580",
    local_directory="/path/to/local/data"
)

rdataframe = get_loaf_t2_tram_rdataframe(
    selected_files=root_files,
    number_of_threads=4
)
```

## Using the result

The returned paths can be passed directly to the appropriate RDataFrame
loader:

``` python
root_files = get_local_directory_root_files_list(
    runspec="3500-3561",
    local_directory="/path/to/local/data"
)

df = get_loaf_t2_tram_rdataframe(
    selected_files=root_files
)
```

Since the files are already available locally, no remote mount or file
transfer is involved.

## Notes

-   The directory must be available on the local filesystem.
-   The same `runspec` syntax can be used for local, LOAF, and TRAM file
    selection.
-   Use `print_folder_summary=True` when checking an unfamiliar
    directory or run range. This option can make the scan take longer.
-   Comma-separated ranges can be used to select discontinuous groups of
    runs without additional filtering.
-   An empty result usually means that no ROOT files matched the run
    specification, or that `local_directory` does not point to the
    expected data.
-   The returned paths describe files on the local machine.