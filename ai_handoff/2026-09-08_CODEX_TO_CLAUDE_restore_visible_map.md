# Codex to Claude: user reports missing map, 2026-09-08

Anthony explicitly says 'map is gone' and supplies a Power BI Desktop screenshot. Network shows the coordinate scatter titled 'Where the margin sits: every site by coordinate', with ZA selected. He wants the geographic map restored; the scatter does not satisfy that requirement.

I checked current local HEAD a8def11: `scripts/generate_powerbi_report.py` now invokes map_visual for Network, and the generated `powerbi/DrakensEnergy360.Report/report.json` Network visual v0020 is type `map`. The screenshot therefore differs from the saved report. This suggests an older in-memory or alternate copy; it does not prove Desktop successfully renders the restored map. The adjacent PBIX file has an older timestamp than the PBIP/report artifacts, so please distinguish the entry points and prevent stale-copy confusion.

Please verify the current PBIP in Desktop, preserving any user edits before reloading. Show the geographic basemap with recognizable South African geography and site bubbles. Verify ZA selection, location type, and recommendation filters change the map and related counts consistently, including zero/single-site selections and sensible extent. Keep coordinate diagnostics on Geography, with clear naming. Inspect clipped KPI labels and recommendation colour distinctions visible in the user's screenshot as part of the same visual QA.

Capture the actual restored map and one filtered state for the PDF/ebook. Do not treat generated JSON as proof of a rendered map. If map rendering is blocked by the host's map settings or service access, report the specific observed blocker rather than silently substituting the scatter. Please remove the stale contradictory comment block above the restored map describing the scatter as the selected Network design.

I have not edited your report files or changed the user's running Desktop session. This reply records the explicit user requirement and the saved-artifact check.
