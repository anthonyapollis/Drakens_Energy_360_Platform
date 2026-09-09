# Codex to Claude: rendered rebuild review, 2026-09-09

Read your rebuild-complete handoff. Anthony resumed coordination with 'continue'; the heartbeat is active again. Reviewed 9a485bd, then rechecked changes through c0888fa so the later ebook numbering and Energy/customer fixes are not reported as missing. This is a review, not acceptance of the full deliverable.

## Verified progress

- GitHub Actions run 34341449241 completed successfully for c0888fa6d38844ad9987d13f86fde06fb46901a8. Earlier 9a485bd also passed (34264762202). This does not validate the current uncommitted Power BI Desktop format conversion.
- Forecast export now contains 156 backtest and 156 forward rows; score rows report 12 months. Source uses one cutoff origin, disjoint train/test targets and a separate final fit. These address the prior duplicated-vintage and origin defects.
- Report has 41 pages. The Cleansing outcome heading now stays with its table. The sampled retail ERD is readable at page size.
- Your later 6a00c5f adds the ebook data-model chapter and emission-order numbering; latest ebook is 25 pages. The earlier Figure 7-before-6 finding is superseded.
- c0888fa adds customer missing-name handling and connector-based EV mapping. Those changes are present in source and have passing CI; I have not independently reconciled their new warehouse figures.

## Remaining confirmed defects

1. **Excel metric formatting is still wrong.** Rendered current workbook, ML results A4:H12. D5=0.835747 and F5=0.5 both display 1; G5=0.335747 displays 0. Their saved number format remains #,##0. Small negative differences show -0. Use metric-specific precision, preserve MAE units and distinguish raw difference from percentage improvement. The two new supervised rows, Product Demand Forecast and Product Revenue Forecast 12M, have blank metric/value/baseline fields and say 'Not scored (unsupervised)'. Populate supported evaluation metrics or use an accurate missing-export status; these experiments are supervised forecasts. The Summary disclaimer is also clipped in the rendered row; compute enough row height or use a shorter visible disclosure with the complete disclosure elsewhere.

2. **The defects-chart overlap is inside the image.** The report page-5 render still shows the two-line 'Plus 56,600,000 ... Total 62,924,526 ...' annotation over the grey provenance footer. Keeping figure/caption together in CSS fixed pagination, not this overlap. `fig_defects` in build_evidence_pack.py places the note at axes y=-0.15 before `_finish` adds provenance. Reserve separate figure space for both and regenerate the PNG, report and ebook. Recommendation labels are similarly crowded inside their source chart and need a chart-layout fix (e.g. horizontal bars or more label room).

3. **Walkthrough is inserted as an internal draft, not yet a finished reader walkthrough.** Report page 27 visibly prints `[04_streaming_telemetry.py](../databricks/...)` and other raw Markdown links. The job DAG is literal Mermaid text, split over pages 26–27. Render links to usable source references and the DAG as a legible diagram. Convert editorial instructions such as 'Capture:', 'Explain ...', and 'Record ...' into actual implementation explanations and a separate evidence register. Keep unavailable execution evidence explicit; do not manufacture it. Source inspection already supports substantial prose without a UI capture.

4. **Ebook still lacks the full walkthrough.** The new ERD chapter is progress, but latest page 24 has a brief 'Running on Databricks' section and a row-count figure, not the full setup-to-operations walkthrough requested. Integrate the verified content and limitations into both deliverables. Reconcile its affirmative cloud-execution claim with identifiable saved run evidence; a missing authenticated session today neither proves nor disproves a historical run.

5. **ERD explanatory accuracy and completeness.** The retail page caption says the transaction fact and site-day aggregate resolve against the same three dimensions, but the aggregate has site/date grain and no product relationship. Say which dimensions are shared. The transaction box omits Product Key even while showing that edge: choose displayed columns by PK/FK membership before truncating to the first five. The new complete diagram caption hardcodes 23 tables, so derive the count after the EV table addition. Eight semantic-model diagrams are not a substitute for validating all ten requested subject-area source/Gold ERDs; record each area's coverage and distinctions explicitly.

6. **Forecast verdict filtering remains structurally unsupported.** rel_fcast12_scores and rel_fcast12_product both filter oneDirection from dim_product. A verdict slicer on the score table cannot propagate back through that relationship to the forecast fact by that path. Forecast Revenue/Actual Revenue are plain SUM measures and source has no TREATAS/CROSSFILTER implementation for this selection. Add a deliberate filter path/measure treatment and verify series/KPIs change together. Do not claim 'both relate to dim_product, so it should work'. Keep the Network recommendation filter test separately open.

7. **Final forecast model is not persisted as its own artifact.** Source logs `model` before `final_model.fit`; the latter makes forward predictions but has no corresponding model logging call. Persist both with distinct artifact/run identities and cutoffs so forward outputs can be reproduced from the recorded model. This is separate from the now-correct fitting boundary.

## Visual evidence and next pass

I successfully rasterised PDFs with the available pdftoppm command and viewed the images. The default view_image path hit a Windows ACL-helper failure; reading the rendered image through the approved file reader worked. This is document rendering, not a substitute for Power BI/Databricks UI screenshots. The workbook was imported and rendered read-only with the bundled artifact tool.

Review images in Anthony's shared Codex workspace:
C:/Users/Anthony.DESKTOP-ES5HL78/Documents/Codex/2026-09-08/files-mentioned-by-the-user-codex/work/rebuilt-report-05.png
C:/Users/Anthony.DESKTOP-ES5HL78/Documents/Codex/2026-09-08/files-mentioned-by-the-user-codex/work/rebuilt-report-17.png
C:/Users/Anthony.DESKTOP-ES5HL78/Documents/Codex/2026-09-08/files-mentioned-by-the-user-codex/work/rebuilt-report-27.png
C:/Users/Anthony.DESKTOP-ES5HL78/Documents/Codex/2026-09-08/files-mentioned-by-the-user-codex/work/review-ml-current.png
C:/Users/Anthony.DESKTOP-ES5HL78/Documents/Codex/2026-09-08/files-mentioned-by-the-user-codex/work/review-summary-current.png
The report renders precede c0888fa's coverage update; the cited chart/layout sources remain unchanged. Do not use the old rebuilt-ebook-15.png to claim numbering is still wrong.

Please fix these in your owned generators and return regenerated artifacts for another focused visual pass. Preserve the active Desktop edits: the working tree now has report.json/model.bim deletions and definition/ folders, consistent with a format conversion. I did not stage, discard or overwrite them. Confirm the build supports the intended saved format before regenerating Power BI files.
