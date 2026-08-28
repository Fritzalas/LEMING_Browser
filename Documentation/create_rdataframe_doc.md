# ROOT RDataFrame Loading Functions

The following functions provide specialised and generic entry points for constructing ROOT `RDataFrame` objects from selected LOAF or TRAM ROOT files.

All four loaders delegate the actual dataframe construction to the same underlying `create_rdataframe` implementation. This common creation path validates the arguments, configures ROOT implicit multithreading, converts the selected Python `Path` objects into a `ROOT.std.vector("string")`, creates the `ROOT.RDataFrame`, validates requested branches, optionally adds run/subrun information, prints selected column types, and registers provenance for the resulting dataframe.

A key implementation detail is that these dataframes retain ROOT's normal lazy execution model. Constructing the `RDataFrame` establishes the computation graph and data source, but event processing occurs when an action such as `Count`, `Histo1D`, `AsNumpy`, or `Snapshot` is evaluated. The optional debug run/subrun preview is an exception because it explicitly invokes actions and therefore triggers event processing.

> **Important:** `required_columns` is currently a **validation option**, not a true column-projection mechanism. The implementation checks that all requested columns exist, but the underlying `ROOT.RDataFrame` is still constructed from the complete TTree and other branches remain accessible.

---

# Load LOAF T2 TRAM Data as a ROOT RDataFrame in Python

Build a ROOT `RDataFrame` from LOAF ROOT files targeting the `t2_tram` tree, with optional ROOT implicit multithreading, required-column validation, and run/subrun labelling.

`get_loaf_t2_tram_rdataframe` is the specialised LOAF loader for the standard `t2_tram` tree. It accepts a collection of resolved ROOT file paths and forwards them to the common RDataFrame creation routine with `tree_name="t2_tram"` by default.

Internally, the creation routine first configures ROOT implicit multithreading. If ROOT implicit multithreading is already enabled, it is disabled before the requested configuration is applied. When `number_of_threads=None`, implicit multithreading remains disabled. When an integer is supplied, the loader calls `ROOT.EnableImplicitMT(number_of_threads)` and reports the resulting ROOT thread-pool size.

The selected file paths are converted into a C++ `ROOT.std.vector("string")`, after which the dataframe is constructed approximately as:

```python
dataframe = ROOT.RDataFrame(tree_name, root_files)
```

If `required_columns` is supplied, the function compares those names against `dataframe.GetColumnNames()` and raises a `DataFrameError` when requested branches are absent. This validates the expected schema; it does **not** remove unlisted branches from the dataframe.

When `add_run_subrun_columns=True`, the loader makes `Runnumber` and `Subrunnumber` available using `DefinePerSample` and the current input sample filename. Existing columns with either name are preserved rather than overwritten.

## Function signature

```python
get_loaf_t2_tram_rdataframe(
    selected_files,
    tree_name="t2_tram",
    number_of_threads=None,
    required_columns=None,
    add_run_subrun_columns=False,
    debug_preview_dataframe=False,
)
```

## Parameters

### `selected_files`

**Type:** `list[Path]`  
**Required:** Yes

A list of resolved ROOT file `Path` objects to use as input. These are typically produced by `get_loaf_remote_directory_root_files_list` or `get_local_directory_root_files_list`.

The paths are converted to strings and inserted into a `ROOT.std.vector("string")` before `ROOT.RDataFrame` is constructed.

### `tree_name`

**Type:** `str`  
**Default:** `"t2_tram"`

Name of the ROOT TTree used as the dataframe data source.

The default targets the standard LOAF `t2_tram` tree. Override it only when the selected files use another tree name.

### `number_of_threads`

**Type:** `int | None`  
**Default:** `None`

Controls ROOT implicit multithreading for the process.

Before creating the dataframe, the common creation routine checks `ROOT.IsImplicitMTEnabled()`. If implicit multithreading is already active, it calls `ROOT.DisableImplicitMT()` first.

When `number_of_threads` is `None`, ROOT implicit multithreading is left disabled. Otherwise the function calls:

```python
ROOT.EnableImplicitMT(number_of_threads)
```

and reports `ROOT.GetThreadPoolSize()`.

Because ROOT implicit multithreading is process-global state, this configuration affects more than the individual dataframe being returned.

### `required_columns`

**Type:** `set[str] | None`  
**Default:** `None`

Optional set of branch or column names that must exist in the resulting dataframe.

When supplied, the implementation retrieves all available names with `GetColumnNames()` and checks that every requested name exists. Missing names cause a `DataFrameError`.

This parameter currently performs **schema validation rather than column projection**. Columns not listed in `required_columns` remain available in the RDataFrame.

### `add_run_subrun_columns`

**Type:** `bool`  
**Default:** `False`

When `True`, ensures that `Runnumber` and `Subrunnumber` columns are available.

If either column already exists in the input tree, that column is retained unchanged. Otherwise the loader uses `DefinePerSample` together with C++ helper functions to derive the value from the current input sample filename.

Conceptually, the definitions are equivalent to:

```python
dataframe = dataframe.DefinePerSample(
    "Runnumber",
    "ExtractRunNumberFromSample(rdfsampleinfo_.AsString())",
)

dataframe = dataframe.DefinePerSample(
    "Subrunnumber",
    "ExtractSubrunNumberFromSample(rdfsampleinfo_.AsString())",
)
```

### `debug_preview_dataframe`

**Type:** `bool`  
**Default:** `False`

Enables additional debugging output for the injected run/subrun information.

This option is relevant when `add_run_subrun_columns=True`. The implementation evaluates `Count()` and uses `AsNumpy()` to print the first and last rows containing `rdfentry_`, `Runnumber`, and `Subrunnumber`.

Unlike ordinary RDataFrame construction, these operations are actions and therefore trigger event processing. Avoid enabling this option when you want dataframe creation to remain purely lazy.

## Return value

```python
ROOT.RDataFrame
```

Returns the ROOT RDataFrame node produced from the selected files and tree. Standard ROOT RDataFrame transformations and actions can be chained from the returned object.

The creation operation is also registered in the provenance system, including the tree name, number of files, thread configuration, requested columns, run/subrun configuration, and the selected-file collection used as its parent.

## Examples

### Load the standard LOAF T2 TRAM tree with multithreading

```python
from leming_browser import (
    get_loaf_remote_directory_root_files_list,
    get_loaf_t2_tram_rdataframe,
)

root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3561"
)

rdataframe = get_loaf_t2_tram_rdataframe(
    selected_files=root_files,
    number_of_threads=8,
    add_run_subrun_columns=True,
    debug_preview_dataframe=False,
)
```

### Validate that required branches exist

```python
rdataframe = get_loaf_t2_tram_rdataframe(
    selected_files=root_files,
    number_of_threads=8,
    required_columns={"Runnumber", "Itime"},
)

h_itime = rdataframe.Histo1D("Itime")
h_itime.Draw()
```

`required_columns={"Runnumber", "Itime"}` ensures that these columns exist. It does not restrict the dataframe to only those two columns.

## Notes

- `ROOT.EnableImplicitMT()` configures ROOT globally for the current process.
- Existing implicit multithreading is disabled before each new configuration is applied.
- `number_of_threads=None` explicitly results in implicit multithreading being disabled by this creation routine.
- `required_columns` validates the dataframe schema but does not currently project branches.
- Added run/subrun columns are named `Runnumber` and `Subrunnumber`.
- Existing `Runnumber` or `Subrunnumber` branches are never overwritten.
- Ordinary RDataFrame construction remains lazy; the debug preview intentionally triggers actions.

---

# Load LOAF Diagnostics Data as a ROOT RDataFrame Object

Build a ROOT `RDataFrame` from LOAF ROOT files targeting the `diagnostics` tree, with optional ROOT implicit multithreading, required-column validation, and run/subrun labelling.

`get_loaf_diagnostics_rdataframe` is the specialised loader for the standard LOAF `diagnostics` tree. It uses the same common `create_rdataframe` implementation as the other loaders, so its multithreading, validation, run/subrun handling, debugging, and provenance behaviour are identical. Its main distinction is the default tree name.

The loader is useful for detector diagnostics, monitoring, calibration, or other auxiliary information stored in the LOAF diagnostics TTree.

## Function signature

```python
get_loaf_diagnostics_rdataframe(
    selected_files,
    tree_name="diagnostics",
    number_of_threads=None,
    required_columns=None,
    add_run_subrun_columns=False,
    debug_preview_dataframe=False,
)
```

## Parameters

### `selected_files`

**Type:** `list[Path]`  
**Required:** Yes

Resolved ROOT file paths to use as input, typically obtained from `get_loaf_remote_directory_root_files_list` or `get_local_directory_root_files_list`.

### `tree_name`

**Type:** `str`  
**Default:** `"diagnostics"`

Name of the TTree used to construct the ROOT RDataFrame.

The default selects the standard LOAF diagnostics tree.

### `number_of_threads`

**Type:** `int | None`  
**Default:** `None`

Controls ROOT implicit multithreading.

The common creation routine first disables an existing ROOT implicit-MT configuration, if present. If a thread count is then supplied, it calls `ROOT.EnableImplicitMT(number_of_threads)`. If the value is `None`, implicit multithreading remains disabled.

### `required_columns`

**Type:** `set[str] | None`  
**Default:** `None`

Set of column names that must be present in the diagnostics dataframe.

The function validates these names against `GetColumnNames()` and raises `DataFrameError` for missing branches.

This option does **not** currently project the tree down to only the specified branches.

### `add_run_subrun_columns`

**Type:** `bool`  
**Default:** `False`

When enabled, ensures that the dataframe contains `Runnumber` and `Subrunnumber`.

Missing columns are derived per input sample from the source filename using C++ extraction helpers and `DefinePerSample`. Existing columns are preserved.

### `debug_preview_dataframe`

**Type:** `bool`  
**Default:** `False`

When run/subrun injection is enabled, prints debugging information for the first and last rows of the dataframe.

The preview uses `Count()` and `AsNumpy()`, so enabling it triggers RDataFrame event processing.

## Return value

```python
ROOT.RDataFrame
```

Returns a ROOT RDataFrame backed by the requested diagnostics tree across the supplied ROOT files.

The dataframe can subsequently be filtered, extended with `Define`, histogrammed, converted with `AsNumpy`, or written with `Snapshot`.

## Examples

### Create a diagnostics dataframe with eight ROOT worker threads

```python
from leming_browser import (
    get_loaf_remote_directory_root_files_list,
    get_loaf_diagnostics_rdataframe,
)

root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3561"
)

rdataframe = get_loaf_diagnostics_rdataframe(
    selected_files=root_files,
    number_of_threads=8,
    add_run_subrun_columns=False,
    debug_preview_dataframe=False,
)
```

### Validate diagnostic columns and add run/subrun information

```python
rdataframe = get_loaf_diagnostics_rdataframe(
    selected_files=root_files,
    number_of_threads=8,
    required_columns={"Temperature", "Voltage", "Runnumber"},
    add_run_subrun_columns=True,
)

h_temp = rdataframe.Histo1D("Temperature")
h_temp.Draw()
```

## Notes

The diagnostics loader does not implement a separate dataframe engine. It is a convenience wrapper around the same common creation path used by the other loaders. Consequently, thread configuration, column checking, run/subrun definitions, and provenance are consistent across the API.

If diagnostics data needs to be compared with physics data from another tree, the trees should normally be loaded as separate RDataFrames and correlated using appropriate identifiers such as `Runnumber` and, where relevant, `Subrunnumber`.

---

# Load TRAM T2 Cluster Data as a ROOT RDataFrame Object

Build a ROOT `RDataFrame` from TRAM ROOT files targeting the `t2_clusters` tree, with optional ROOT implicit multithreading, required-column validation, and run/subrun labelling.

`get_tram_t2_clusters_rdataframe` is the specialised loader for TRAM T2 cluster data. By default it constructs the dataframe from the `t2_clusters` TTree and otherwise shares the same creation machinery as the LOAF loaders.

The selected files are converted into a ROOT C++ string vector and passed with the tree name to `ROOT.RDataFrame`. Optional implicit multithreading is configured before this construction occurs.

## Function signature

```python
get_tram_t2_clusters_rdataframe(
    selected_files,
    tree_name="t2_clusters",
    number_of_threads=None,
    required_columns=None,
    add_run_subrun_columns=False,
    debug_preview_dataframe=False,
)
```

## Parameters

### `selected_files`

**Type:** `list[Path]`  
**Required:** Yes

List of resolved TRAM ROOT file paths, normally produced by `get_tram_remote_directory_root_files_list` or `get_local_directory_root_files_list`.

### `tree_name`

**Type:** `str`  
**Default:** `"t2_clusters"`

Name of the TTree from which the RDataFrame is created.

Override this only when the selected TRAM files use a non-standard tree name.

### `number_of_threads`

**Type:** `int | None`  
**Default:** `None`

Number of threads requested for ROOT implicit multithreading.

The loader's common creation routine resets an existing implicit-MT state with `ROOT.DisableImplicitMT()` before applying the requested configuration. Supplying an integer enables implicit MT through `ROOT.EnableImplicitMT(number_of_threads)`; supplying `None` leaves it disabled.

### `required_columns`

**Type:** `set[str] | None`  
**Default:** `None`

Optional collection of columns that must exist in the `t2_clusters` dataframe.

Missing requested columns cause a `DataFrameError`. The parameter is a validation mechanism and does not remove other branches.

### `add_run_subrun_columns`

**Type:** `bool`  
**Default:** `False`

Ensures that `Runnumber` and `Subrunnumber` are present in the resulting dataframe.

For names not already supplied by the TTree, the implementation loads C++ helper functions and defines the columns per input sample based on `rdfsampleinfo_.AsString()`.

### `debug_preview_dataframe`

**Type:** `bool`  
**Default:** `False`

Prints a run/subrun debugging preview when run/subrun augmentation is enabled.

Because the implementation evaluates `Count()` and `AsNumpy()`, this mode causes ROOT to process entries and should generally be reserved for interactive checks.

## Return value

```python
ROOT.RDataFrame
```

Returns a ROOT RDataFrame for the `t2_clusters` tree across all selected TRAM files.

## Examples

### Build the TRAM cluster dataframe

```python
from leming_browser import (
    get_tram_remote_directory_root_files_list,
    get_tram_t2_clusters_rdataframe,
)

tram_files = get_tram_remote_directory_root_files_list(
    runspec="3500_7-3510_11"
)

rdataframe = get_tram_t2_clusters_rdataframe(
    selected_files=tram_files,
    number_of_threads=8,
    add_run_subrun_columns=False,
)
```

### Validate cluster branches and add run/subrun labels

```python
rdataframe = get_tram_t2_clusters_rdataframe(
    selected_files=tram_files,
    number_of_threads=8,
    required_columns={"ClusterTime", "ClusterSize", "Runnumber"},
    add_run_subrun_columns=True,
    debug_preview_dataframe=False,
)

h_size = rdataframe.Histo1D("ClusterSize")
h_size.Draw()
```

## Notes

- The default TTree is `t2_clusters`.
- ROOT implicit multithreading is configured before `ROOT.RDataFrame` is instantiated.
- The thread setting is process-global ROOT state rather than a property isolated to this dataframe.
- `required_columns` checks the schema; it is not a branch-selection mechanism in the current implementation.
- `Runnumber` and `Subrunnumber` are defined only when they do not already exist.

---

# Load Any ROOT TTree as a Generic RDataFrame in Python

Build a ROOT `RDataFrame` from a collection of ROOT files and an explicitly specified TTree name, with optional ROOT implicit multithreading, required-column validation, and run/subrun labelling.

`get_general_rdataframe` exposes the common dataframe creation machinery without assuming a particular experiment tree. Unlike the specialised LOAF and TRAM wrappers, `tree_name` has no default and must be supplied by the caller.

This makes the function suitable for custom or auxiliary TTrees such as slow-control, temperature, pressure, monitoring, or analysis-specific trees.

The underlying creation sequence is:

1. Validate the supplied arguments.
2. Reset any existing ROOT implicit-multithreading state.
3. Enable ROOT implicit multithreading when `number_of_threads` is provided.
4. Convert the selected Python paths into a `ROOT.std.vector("string")`.
5. Construct `ROOT.RDataFrame(tree_name, root_files)`.
6. Validate any names supplied through `required_columns`.
7. Optionally define missing `Runnumber` and `Subrunnumber` columns per sample.
8. Print relevant column types and loading information.
9. Register dataframe provenance, including the original selected-file collection.
10. Return the resulting dataframe node.

## Function signature

```python
get_general_rdataframe(
    selected_files,
    tree_name,
    number_of_threads=None,
    required_columns=None,
    add_run_subrun_columns=False,
    debug_preview_dataframe=False,
)
```

## Parameters

### `selected_files`

**Type:** `list[Path]`  
**Required:** Yes

Resolved ROOT file paths used to construct the dataframe.

These can originate from the LOAF, TRAM, or local file-selection helpers, provided the requested `tree_name` exists in the files.

### `tree_name`

**Type:** `str`  
**Required:** Yes

Exact name of the ROOT TTree that should become the RDataFrame data source.

Unlike the specialised loaders, this parameter has no built-in default and must be supplied explicitly.

Examples include:

```text
temperatures
t2_tracks
slow_control
myCustomTree
```

### `number_of_threads`

**Type:** `int | None`  
**Default:** `None`

Controls ROOT implicit multithreading before the dataframe is created.

The implementation first performs:

```python
if ROOT.IsImplicitMTEnabled():
    ROOT.DisableImplicitMT()
```

When a thread count is supplied, it subsequently performs:

```python
ROOT.EnableImplicitMT(number_of_threads)
```

When `None` is supplied, no new implicit-MT pool is enabled.

### `required_columns`

**Type:** `set[str] | None`  
**Default:** `None`

Optional set of columns that the selected tree is required to contain.

The implementation obtains the available column names from the newly created RDataFrame and computes the difference between the requested and available names. A non-empty set of missing columns raises `DataFrameError`.

Despite the name, this argument does not currently instruct ROOT to load only those branches. It should therefore be understood as a **required-schema check**.

### `add_run_subrun_columns`

**Type:** `bool`  
**Default:** `False`

When enabled, makes `Runnumber` and `Subrunnumber` available if they are not already present in the selected tree.

The values are extracted from the current sample filename with C++ helper functions and attached using `DefinePerSample`.

This per-sample definition is significant when a dataframe spans many ROOT files: ROOT can associate the synthetic values with the input sample being processed instead of treating the run/subrun identifiers as one constant for the entire dataframe.

### `debug_preview_dataframe`

**Type:** `bool`  
**Default:** `False`

Enables a diagnostic preview of run/subrun values when those columns are being added.

The preview first obtains the total number of entries with:

```python
dataframe.Count().GetValue()
```

and then materialises selected first and last rows with `AsNumpy()`.

Consequently, this option deliberately breaks the otherwise lazy creation-only workflow and can perform substantial I/O for a large dataset.

## Return value

```python
ROOT.RDataFrame
```

Returns the ROOT RDataFrame node associated with the requested TTree and selected files.

The dataframe supports the normal ROOT RDataFrame interface, including operations such as:

```python
df.Filter(...)
df.Define(...)
df.Histo1D(...)
df.Count()
df.Snapshot(...)
df.AsNumpy(...)
```

## Examples

### Load an arbitrary tree

```python
from leming_browser import (
    get_loaf_remote_directory_root_files_list,
    get_general_rdataframe,
)

root_files = get_loaf_remote_directory_root_files_list(
    runspec="3500-3561"
)

temperature_df = get_general_rdataframe(
    selected_files=root_files,
    tree_name="temperatures",
    number_of_threads=8,
)
```

### Validate a custom tree schema and add run information

```python
pressure_df = get_general_rdataframe(
    selected_files=root_files,
    tree_name="slow_control",
    number_of_threads=4,
    required_columns={"Pressure", "Timestamp", "Runnumber"},
    add_run_subrun_columns=True,
)

h_pressure = pressure_df.Histo1D("Pressure")
h_pressure.Draw()
```

## Implementation notes

### ROOT implicit multithreading is configured globally

`number_of_threads` does not merely configure the returned dataframe. The common creation routine manipulates ROOT's process-wide implicit multithreading state.

Each call first checks whether implicit MT is active and disables it if necessary. A supplied thread count then creates a new ROOT thread pool with `ROOT.EnableImplicitMT()`.

This makes the behaviour deterministic for each loader call, but code using other ROOT dataframes in the same Python process should be aware that creating another dataframe through these helpers can change the global ROOT MT configuration.

### RDataFrame construction is separate from event processing

The central construction call is:

```python
dataframe = ROOT.RDataFrame(
    tree_name,
    root_files,
)
```

ROOT RDataFrame follows a lazy execution model. Creating this object and chaining transformations primarily constructs a computation graph. Actions such as `Count`, histogram evaluation, `Snapshot`, and `AsNumpy` cause the event loop to run.

The loader therefore does not normally read and materialise the complete dataset at creation time.

### `required_columns` validates rather than projects

After dataframe construction, requested columns are checked using `GetColumnNames()`. The implementation raises an error if any required names are absent.

There is currently no branch-selection operation in `create_rdataframe`, so documentation should not describe this parameter as reducing memory usage by loading only selected branches.

### Run and subrun values are sample-aware

Missing `Runnumber` and `Subrunnumber` columns are created with `DefinePerSample`, using the current sample information supplied by ROOT. This allows filenames to be inspected as ROOT transitions between input files.

The loader intentionally preserves real branches with these names when they already exist.

### Debug preview performs real actions

When the debug preview is requested together with run/subrun augmentation, the implementation calls `Count().GetValue()` and `AsNumpy()` for selected rows. These are actions and cause the dataframe graph to execute.

For large or remotely mounted datasets, this can involve meaningful I/O and should be enabled only when the diagnostic information is useful.

### Provenance is registered automatically

Every successfully constructed dataframe is passed to `register_provenance` with operation `"ROOT RDataFrame creation"`.

Recorded parameters include:

- the tree name;
- number of selected files;
- requested number of threads;
- whether implicit multithreading was requested;
- requested columns;
- whether run/subrun augmentation was requested; and
- which run/subrun columns were actually added.

The original selected-file collection is registered as the parent, allowing downstream dataframe history to be traced back to the file/run selection that produced it.

---

# Apply 3D Volume Cuts and Load a Filtered ROOT RDataFrame

`get_rdataframe_volume_cuts` prepares TRAM track data for analysis by running the TRAM volume-cut executable over a selected run range and then opening the generated ROOT output as a `ROOT.RDataFrame`.

The function supports local and remote project layouts. Depending on the configuration, the volume-cut executable is built and executed either locally or on the remote TRAM machine. Input ROOT files may come from a local directory or from a remotely mounted TRAM directory. After the external volume-cut program successfully produces an output ROOT file, that file is validated and used as the backing source of a new ROOT RDataFrame.

Unlike the general RDataFrame loaders, this function does more than attach an RDataFrame directly to the original ROOT files. It first performs a preprocessing stage that applies the requested spatial and optional time cuts and writes the surviving data into a new ROOT file. The returned RDataFrame therefore reads the **already-filtered output ROOT file**, rather than dynamically applying the spatial cuts through `RDataFrame.Filter`.

## Function signature

```python
get_rdataframe_volume_cuts(
    runspec,
    project_directory,
    isRemoteProjectDirectory=False,
    number_of_threads=None,
    tree_name="t2_tracks",
    host="lepp-c-3po",
    user="leming",
    root_files_local_directory=None,
    root_files_remote_directory="data0/leming/BT2025/kosmas/tram",
    output_file="output_dovolumecuts.root",
    xmin=-6.0,
    xmax=6.0,
    ymin=17.0,
    ymax=29.0,
    zmin=10.0,
    zmax=15.0,
    tmin=None,
    tmax=None,
    rebuild=False,
    print_folder_summary=False,
    conda_base="/home/leming/packages/miniforge3",
    conda_environment="leming"
)
```

## Parameters

### `runspec`

**Type:** `str`  
**Required:** Yes

Run specification passed to the TRAM volume-cut executable.

For example:

```text
3499-3541
```

or a specification containing multiple supported run segments.

The value is stripped of surrounding whitespace and must be a non-empty string before any expensive processing begins.

### `project_directory`

**Type:** `str | Path`  
**Required:** Yes

Project directory containing the TRAM volume-cut software and used as the location in which the volume-cut executable is prepared.

Its interpretation depends on `isRemoteProjectDirectory`.

When:

```python
isRemoteProjectDirectory=False
```

`project_directory` is treated as a local project directory.

When:

```python
isRemoteProjectDirectory=True
```

it identifies the corresponding project directory on the remote host. The remote directory is also mounted locally through the project's remote mounting helper so that the output ROOT file created remotely can subsequently be accessed by the local Python/ROOT process.

### `isRemoteProjectDirectory`

**Type:** `bool`  
**Default:** `False`

Selects whether the TRAM project itself is local or remote.

This choice changes where the external volume-cut executable is built and executed.

For a local project, the executable is prepared and run on the current machine.

For a remote project, the executable is prepared and executed on the remote host over SSH. In this mode, `root_files_local_directory` cannot be used because the remotely executed process cannot access a directory that exists only on the local machine.

### `number_of_threads`

**Type:** `int | None`  
**Default:** `None`

Number of threads requested for the volume-cut processing and for ROOT implicit multithreading on the local Python side.

If `None` is supplied, the implementation converts it to:

```python
number_of_threads = 1
```

The value must be an integer greater than or equal to `1` and cannot exceed the number of CPUs available to the current process.

After validation, the function calls:

```python
ROOT.EnableImplicitMT(number_of_threads)
```

and prints the selected thread count.

The same thread count is also forwarded to the external TRAM volume-cut command.

### `tree_name`

**Type:** `str`  
**Default:** `"t2_tracks"`

Name of the ROOT TTree processed by the volume-cut workflow and subsequently opened from the generated ROOT file.

The standard TRAM track tree is:

```text
t2_tracks
```

After the external processing stage succeeds, the returned dataframe is constructed with the equivalent of:

```python
dataframe = ROOT.RDataFrame(
    tree_name,
    str(temporary_output_path),
)
```

### `host`

**Type:** `str`  
**Default:** `"lepp-c-3po"`

Hostname of the remote TRAM machine.

It is used when mounting remote directories and when the project itself is remote and processing must be performed through SSH.

### `user`

**Type:** `str`  
**Default:** `"leming"`

Username used for access to the remote host.

For a fully remote project, the same user is used when mounting the project/input directories and when executing the volume-cut command remotely.

### `root_files_local_directory`

**Type:** `str | Path | None`  
**Default:** `None`

Optional local directory containing the TRAM ROOT input files.

When supplied for a local project, this directory is resolved through the local directory helper and the volume-cut executable reads the ROOT files directly from the local filesystem.

When `None`, the loader obtains the input directory from `root_files_remote_directory` through the remote mounting machinery.

A local input directory is not permitted when:

```python
isRemoteProjectDirectory=True
```

because the volume-cut executable is then running on the remote machine.

### `root_files_remote_directory`

**Type:** `str`  
**Default:** `"data0/leming/BT2025/kosmas/tram"`

Remote directory containing the TRAM ROOT files.

For a local project with remote data, this directory is mounted and the locally executed volume-cut program reads from the mounted path.

For a remote project, the directory is both mounted locally for visibility and converted into its native remote absolute path for use by the remotely executed program.

### `output_file`

**Type:** `str | Path`  
**Default:** `"output_dovolumecuts.root"`

Base output filename used when creating the ROOT file containing the volume-cut result.

The current implementation does **not** simply write repeatedly to this exact filename. Instead, it calls the output helper to generate a unique output filename using the supplied name as the base and appending a unique identifier.

The produced file becomes the backing ROOT file of the returned RDataFrame and is registered with the temporary volume-cut-file manager.

### `xmin`, `xmax`

**Type:** `float`  
**Defaults:** `-6.0`, `6.0`

Minimum and maximum x-coordinate passed to the TRAM volume-cut executable.

The minimum cannot be greater than the maximum.

### `ymin`, `ymax`

**Type:** `float`  
**Defaults:** `17.0`, `29.0`

Minimum and maximum y-coordinate passed to the volume-cut executable.

The minimum cannot be greater than the maximum.

### `zmin`, `zmax`

**Type:** `float`  
**Defaults:** `10.0`, `15.0`

Minimum and maximum z-coordinate passed to the volume-cut executable.

The minimum cannot be greater than the maximum.

### `tmin`, `tmax`

**Type:** `float | None`  
**Defaults:** `None`, `None`

Optional lower and upper time limits passed to the external volume-cut command.

Either value may be omitted. If both are supplied, `tmin` cannot be greater than `tmax`.

When neither value is provided, provenance records the time range as `None`.

### `rebuild`

**Type:** `bool`  
**Default:** `False`

Controls whether the TRAM volume-cut executable/build should be rebuilt when it is prepared.

For a local project this value is passed to:

```python
prepare_volume_cuts_executable(..., rebuild=rebuild)
```

For a remote project it is passed to:

```python
prepare_remote_volume_cuts_executable(..., rebuild=rebuild)
```

**Important:** in the current implementation, `rebuild` controls executable/build preparation. It is **not** implemented as a cache invalidation flag for reusing an existing filtered ROOT output file. A new uniquely named output file is generated for each processing call.

### `print_folder_summary`

**Type:** `bool`  
**Default:** `False`

Passed to the local/remote directory resolution and mounting helpers.

When enabled, those helpers may print information about the directories being accessed before processing begins.

This is useful when checking that the intended project and ROOT input locations are being resolved correctly.

### `conda_base`

**Type:** `str | Path`  
**Default:** `"/home/leming/packages/miniforge3"`

Path to the Conda installation on the remote host.

This is used only by the remote-project workflow when preparing and executing the TRAM volume-cut program remotely.

### `conda_environment`

**Type:** `str`  
**Default:** `"leming"`

Name of the Conda environment activated for remote build and execution operations.

## Return value

```python
ROOT.RDataFrame
```

Returns a ROOT RDataFrame backed by the ROOT file generated by the TRAM volume-cut executable.

The important distinction from the ordinary RDataFrame loaders is that the returned dataframe does **not** directly read the original collection of TRAM ROOT files.

Instead, the processing chain is approximately:

```text
selected TRAM input directory
        |
        v
validate runspec / cuts / thread count
        |
        v
prepare volume-cut executable
        |
        v
construct tram_dovolumecuts command
        |
        v
execute volume cuts
        |
        v
write unique output ROOT file
        |
        v
validate output ROOT file
        |
        v
ROOT.RDataFrame(
    tree_name,
    output_root_file
)
        |
        v
register provenance
        |
        v
return RDataFrame
```

The spatial and temporal filtering is therefore materialised in the generated ROOT file before the RDataFrame is returned.

## Execution modes

The function supports three useful deployment patterns.

### Pattern 1 — Local project and local ROOT files

Both the TRAM project and its input data are available locally.

```python
from leming_browser import get_rdataframe_volume_cuts

rdataframe_vol1 = get_rdataframe_volume_cuts(
    runspec="3499-3541",
    project_directory="/home/kfritzalas/tram",
    isRemoteProjectDirectory=False,
    root_files_local_directory="/data0/kfritzalas/tram",
    xmin=-6,
    xmax=6,
    ymin=17,
    ymax=29,
    zmin=10,
    zmax=15,
    tmin=0,
    tmax=1000,
    number_of_threads=16,
)
```

In this mode the project is prepared locally, the ROOT input directory is resolved locally, and the volume-cut executable runs on the current machine.

### Pattern 2 — Local project and remote ROOT files

The TRAM software project is local but the input files remain on the remote machine.

```python
rdataframe_vol2 = get_rdataframe_volume_cuts(
    runspec="3499-3541",
    project_directory="/home/kfritzalas/tram",
    isRemoteProjectDirectory=False,
    xmin=-6,
    xmax=6,
    ymin=17,
    ymax=29,
    zmin=10,
    zmax=15,
    tmin=0,
    tmax=1000,
    number_of_threads=16,
)
```

Because `root_files_local_directory` is not supplied, the remote TRAM directory is mounted and used as the input directory by the locally executed program.

### Pattern 3 — Remote project and remote ROOT files

Both the software project and TRAM input data reside on the remote host.

```python
rdataframe_vol3 = get_rdataframe_volume_cuts(
    runspec="3499-3541",
    project_directory=(
        "data0/leming/BT2025/kosmas/tram_software/tram"
    ),
    isRemoteProjectDirectory=True,
    xmin=-6,
    xmax=6,
    ymin=17,
    ymax=29,
    zmin=10,
    zmax=15,
    tmin=0,
    tmax=1000,
    number_of_threads=16,
)
```

In this mode the project path is mounted locally for access, converted to the corresponding native remote path, and built remotely. The volume-cut command is then executed on the remote machine over SSH.

The generated ROOT output remains remotely located but is visible to the local Python process through its mounted path. ROOT then opens that mounted output file when constructing the returned RDataFrame.

### Rebuild the volume-cut executable

```python
rdataframe_vol4 = get_rdataframe_volume_cuts(
    runspec="3499-3541",
    project_directory="/home/kfritzalas/tram",
    xmin=-4,
    xmax=4,
    ymin=18,
    ymax=28,
    zmin=11,
    zmax=14,
    rebuild=True,
    number_of_threads=16,
)
```

Here `rebuild=True` requests rebuilding/re-preparing the external volume-cut program before executing it.

It should not be interpreted as "ignore an existing filtered-data cache", because the current implementation creates a new uniquely named output ROOT file for each processing invocation.

## Internal ROOT behavior

### ROOT implicit multithreading is enabled

At the beginning of the operation, `number_of_threads=None` is converted to `1`.

The function then calls:

```python
ROOT.EnableImplicitMT(number_of_threads)
```

before selecting the local or remote execution branch.

Unlike `create_rdataframe`, this implementation does not first call `ROOT.DisableImplicitMT()` when implicit multithreading is already active.

The thread count is also passed to the external volume-cut executable, meaning the parameter participates in both the Python ROOT environment and the preprocessing command.

### Thread counts are validated against the process CPU allocation

The function determines the number of CPUs available to the current process using `os.sched_getaffinity(0)` when available, with `os.cpu_count()` as a fallback.

A requested thread count greater than that available allocation raises `doVolumeCutsError`.

This matters on systems using schedulers, containers, CPU affinity, or `taskset`, where the process may intentionally have access to fewer CPUs than the physical machine contains.

### The RDataFrame is created after preprocessing

The volume cut itself is not implemented as a chain such as:

```python
df.Filter("x > xmin && x < xmax ...")
```

Instead, an external executable receives the run specification and cut boundaries and writes an output ROOT file.

Only after that output has been validated does Python execute:

```python
dataframe = ROOT.RDataFrame(
    tree_name,
    str(temporary_output_path),
)
```

Consequently, construction of the final RDataFrame is lightweight compared with the preprocessing stage: the expensive volume selection has already been materialised into the backing ROOT file.

## Provenance

The returned dataframe is registered with the provenance system using:

```text
operation = "TRAM volume cuts"
```

Recorded information includes:

- cleaned run specification;
- tree name;
- x, y, and z ranges;
- optional time range;
- number of threads;
- local or remote project type;
- project directory;
- input directory;
- generated backing ROOT file;
- `rebuild` state; and
- for remote projects, the host, user, and remote input directory.

This makes it possible to inspect how a volume-cut dataframe was produced and which generated ROOT file backs it.

## Failure handling

The workflow validates the output ROOT file before creating the dataframe.

If processing fails before successful completion, the `finally` block attempts to delete the temporary output file and prints an error notice.

This prevents an incomplete output file from being silently treated as a valid processed dataset.

## Notes

- The default tree is `t2_tracks`.
- The spatial bounds are validated before expensive processing starts.
- If both limits of a spatial or time range are supplied, the minimum cannot exceed the maximum.
- `number_of_threads=None` becomes `1`; it does not leave implicit multithreading disabled.
- `ROOT.EnableImplicitMT(number_of_threads)` is called before the volume-cut execution branch is selected.
- The same thread count is forwarded to the external volume-cut executable.
- Local input files can be used only when the project itself is local.
- Remote projects require remote input data because the external executable runs on the remote host.
- The filtered data is materialised into a generated ROOT file before `ROOT.RDataFrame` is constructed.
- The current implementation creates a uniquely named output file for each invocation rather than loading a persistent result cache based on matching cut parameters.
- `rebuild=True` controls rebuilding/preparation of the external executable, not invalidation of a filtered-data cache.
- The generated backing ROOT file is registered with the volume-cut temporary-file manager.
- Provenance is attached automatically to the returned dataframe.