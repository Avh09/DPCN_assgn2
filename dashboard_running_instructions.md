# Running the dashboard

The dashboard is a static web page. It needs no server, no installation and no internet connection.

## Open it

1. Go to the `DPCN_Assignment2/dashboard/` folder.
2. Double-click `index.html`. It opens in your default browser.

You can also open it from a terminal, starting in the `DPCN_Assignment2` folder:

```bash
# Windows
start dashboard\index.html

# macOS
open dashboard/index.html

# Linux
xdg-open dashboard/index.html
```

Use a current version of Chrome, Edge, Firefox or Safari.

## Files it needs

Keep these together in the `dashboard/` folder. If you copy or zip the dashboard, copy the whole folder.

| File | What it is |
|---|---|
| `index.html` | The page |
| `app.js` | Charts, tables, networks and profile panels |
| `ui.js` | Search palette, chart tools and shortcuts |
| `theme.css` | Design |
| `data.js` | All the data (built from `data/out/`) |
| `vendor/` | Plotly, D3 and the fonts, so it works offline |

## Update the data after a pipeline rerun

Run these from the `DPCN_Assignment2` folder. `build_dashboard.py` needs only Python 3; `locality_reach.py` also needs `networkx`.

```bash
python locality_reach.py      # Reach & locality analysis, merges the partners.py results (needs: pip install networkx)
python build_dashboard.py     # rebuilds dashboard/data.js
```

Then refresh the page with **Ctrl+F5**.

## Using it

- **Pages:** use the menu at the top. You can also press `1` to `9`.
- **Institute filter:** use the "Lens" bar at the bottom: All three, MANIT, NITJ or NITS. Press `0` to show all three again.
- **Year range:** use the "Years" selectors in the same bar. Both years are included, so 2016 to 2020 means 2016, 2017, 2018, 2019 and 2020. Click ✕ to go back to all years. Panels marked "All years · not filtered" use numbers computed for the whole period.
- **Citation graph filters:** rank, impact factor, CORE rank, field, Indian links, team size, minimum citations, top-N by PageRank, and views for the largest component, small clusters or one paper's ego network.
- **Search:** press `Ctrl K` or `/`, or click Search. It finds faculty, papers, partner institutes and pages.
- **Details:** click any name, network node, bar or table row. The purple hint under each section title says what clicking does there.
- **Chart tools:** hover a chart title to see the buttons to expand it, download it as PNG, or download its data as CSV.
- **Tables:** the CSV button downloads the rows as currently filtered.
- **Theme:** press `T` or use the sun icon to switch between light and dark.
- **All shortcuts:** press `?`.
- **Link to a view:** add a tag after `#` in the address bar. For example, `index.html#collab?f=4` opens a faculty member in the network, and `index.html#reach?i=National Metallurgical Laboratory` opens that partner institute.

## If something looks wrong

| Problem | Fix |
|---|---|
| The page is blank or the charts are missing | Check that `data.js` and `vendor/` are next to `index.html`. |
| You still see old data or the old design | Refresh with Ctrl+F5. |
| The network graph is empty | Give it a second to lay out. Then, in the Lens bar, select "All three". |
| The Reach tab says to run a script | Run `python locality_reach.py`, then `python build_dashboard.py`. |
