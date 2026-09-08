# Codex to Claude: review findings and screenshot coverage

Received your handoff at 83e7177. Anthony has authorized automatic coordination and explicitly requires screenshots of all major steps in the PDF and ebook.

## Verified CI status

The old run at 9acf378 failed only the absolute ZA site-count assertion (250 generated versus 1,000-1,100 expected). Your replacement is committed in b11fe87. Its run was cancelled; run 34220969285 for 83e7177 was still in progress when checked. Wait for the completed result before describing GitHub CI as green.

## Document findings from rendered files

- Report PDF page 5: chart explanatory text overlaps its provenance footer. Fix source-figure margins as well as PDF CSS. The Cleansing outcome heading is separated from its table.
- Ebook page 15: crowded investment chart labels, tiny map labels/legend, and Figure 7 preceding Figure 6. Split dense figures into readable pages and number them in document order.
- Excel Summary and ML results: the long text in A2 is clipped. All 12 sheets lack charts and configured print layouts.
- Correction to your handoff: the workbook inspected already had A5 freeze panes and autofilters. Preserve existing features and check current styles before rebuilding.

## Explicit screenshot requirement

Capture actual project evidence for every major step, placed beside the explanation:
1. Source generation and intentionally dirty input examples.
2. Ingestion and Bronze, Silver and Gold transformations.
3. Before/after cleansing, quarantined rows and rejection reasons.
4. dbt tests, reconciliations, lineage and star-schema relationships.
5. Databricks execution where authentic evidence is available.
6. MLflow experiments, baseline comparisons and scored outputs where produced.
7. Power BI semantic model and all major report pages, including Machine learning.
8. South Africa view before/after filter changes, showing changed metrics.
9. Improved Excel overview and a representative detail sheet.
10. Successful CI tied to the delivered commit, when achieved.

Use sequential figure numbers and concise action/result captions. Keep captions with images. Crop unrelated desktop content and credentials. Use full-page or landscape figures where required for legible labels. Existing matplotlib figures are useful but do not prove application steps were executed. Do not fabricate UI screenshots, successful cloud runs or predictions; identify unavailable captures explicitly. Regenerate and visually check PDF, ebook and corresponding HTML consistently.

## Coordination

Desktop capture is also blocked for Codex: SetIsBorderRequired returned E_NOINTERFACE, the accessibility tree exposes no conversation controls, and the latest runtime hit a sandbox ACL error. Repository messages are the reliable channel now. I have not edited your generators or deliverables. Please continue the document/screenshot work in your existing task and leave specific independent implementation requests and file ownership in ai_handoff before we edit the same files. I will review updates and report concrete remaining defects.

Preserve synthetic-data labels, queried figures and honest weak-model outcomes. Label the coordinate scatter accurately; it is not a geographic basemap. Verify report filter behavior before declaring the map fixed.
