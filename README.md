# FTV Diagnostics Filter

**by AnythingOT**

> Filter FactoryTalk Diagnostics XML exports with multiple contains / does-not-contain rules, save filter presets, and export results to CSV.

A desktop tool for filtering **FactoryTalk Diagnostics Viewer** XML exports. You can set as many *contains* / *does not contain* rules as you need, preview the matches in a sortable table, and export them to CSV for Excel.

Excel's AutoFilter only allows two text conditions per column. This tool removes that limit, and it reads the raw export directly, including UTF-16 files and files with protected or garbled sections.


<img width="1920" height="1020" alt="image" src="https://github.com/user-attachments/assets/35019213-075d-4c9d-947a-c07eb5130833" />


## Features

- **Unlimited filter rules.** Each rule picks a field (message, any field, location, provider, severity, username), *contains* or *does not contain*, and the text to match
- **All / Any** logic for *contains* rules. Any matching *does not contain* rule always drops the row
- **Case-sensitive** and **regex** matching
- **Sortable results table** (click a column header), with error and warning rows color-coded
- **Copy rows** straight into Excel (Ctrl+C or right-click), and double-click a row for full details
- **Export CSV** writes *all* matches (the table preview shows up to 5,000 rows)
- **Presets.** Save and load rule sets as JSON
- **Command-line mode** for scripts and scheduled jobs
- Uses only the Python standard library, so there's nothing to `pip install`

## Requirements

Python 3.8+ with Tkinter. The python.org Windows installer includes Tkinter by default. On Linux, install your distribution's `python3-tk` package.

## Usage

### GUI

```bash
python ftv_diagnostics_filter.py
python ftv_diagnostics_filter.py export.xml        # open with a file loaded
```

| Shortcut | Action |
|---|---|
| Ctrl+O | Open export |
| Ctrl+N | Add filter rule |
| Enter / F5 | Apply filters |
| Ctrl+C | Copy selected rows |
| Ctrl+E | Export CSV |

### Command line

```bash
# message contains "DataLog" but not "Off"
python ftv_diagnostics_filter.py export.xml -c DataLog -x Off

# message contains "Tank" OR "Pump", custom output file
python ftv_diagnostics_filter.py export.xml -c Tank -c Pump --any -o tanks_pumps.csv

# regex on any field
python ftv_diagnostics_filter.py export.xml -c "DataLog(On|Off)" --regex --field "any field"
```

Run `python ftv_diagnostics_filter.py --help` for all options.

## How matching works

1. Rules with empty text are ignored.
2. If **any** *does not contain* rule matches, the row is dropped.
3. Otherwise, the *contains* rules must **all** match (All) or **at least one** must match (Any).
4. If there are no *contains* rules, every row that wasn't dropped is kept.

## Download (Windows .exe)

Get `FTV_Diagnostics_Filter.exe` from the [Releases](../../releases) page. You don't need Python.

- The exe is **unsigned**, so Windows SmartScreen may warn on first launch (*More info → Run anyway*).
- Antivirus tools sometimes flag PyInstaller executables falsely. On managed plant PCs, check with IT before you distribute one.
- Check the download against `SHA256SUMS.txt`: `Get-FileHash FTV_Diagnostics_Filter.exe`

Releases are built automatically by GitHub Actions (`.github/workflows/release.yml`) when a version tag is pushed:

```bash
git tag v1.0.1 && git push origin v1.0.1
```

To build it yourself:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name FTV_Diagnostics_Filter ftv_diagnostics_filter.py
```

## Tests

```bash
python -m unittest discover tests
```

`samples/sample_export.xml` is a **synthetic** export made for testing. It contains no real plant data.

## Limitations

- It reads `<Item>` **attributes** only. If an export stores fields as child elements, it finds 0 items.
- It parses with regex for robustness, not a full XML parser, so it doesn't validate the XML.
- The table preview is capped at 5,000 rows to keep the UI fast. Export always includes every match.

## License

MIT. See [LICENSE](LICENSE).
