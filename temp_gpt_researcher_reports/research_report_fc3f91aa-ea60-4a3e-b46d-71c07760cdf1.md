---
title: "- Census Bureau"
---

# Report on Changes to the Entity Over Time: U.S. Census Bureau

Author: Research Analyst  
Date: September 1, 2025

Abstract  
This report synthesizes multi‑level research about structural, technical, programmatic, and procedural changes at the U.S. Census Bureau through 2025, with a focus on geographic and geospatial data products and programs (TIGER/TIGER‑Line, CARTO/Baseline products, BAS, LEHD/LODES, and related information‑collection processes). It integrates product documentation, technical schema, program notices, and regulatory materials to describe what changed, why it matters for users, and recommended steps to preserve data reproducibility, accessibility, and operational transparency. The analysis prioritizes recent authoritative sources (2022–2025) and highlights linkages among Census programs, their release schedules, and downstream data users ([U.S. Census Bureau, TIGER Data Products Guide](https://www.census.gov/geographies/mapping-files.html)).

---

## Contents

1. Introduction  
2. High‑level narrative: institutional and product evolution  
3. Detailed product and program changes (2018–2025)  
   - TIGER/TIGER‑Line and Geodatabases  
   - TIGER/Line with Selected Demographic and Economic Data (pre‑2022)  
   - Cartographic Boundary Files  
   - Boundary and Annexation Survey (BAS) & Legal Boundary Change Files  
   - LEHD / LODES and LEHD shapefiles  
   - Data formats, release timing, and operational practices  
4. Cross‑program interactions and implications for users  
5. Comparative summary table of key products (features, uses, caveats)  
6. Statistics, concrete examples, and evidence highlights  
7. Assessment and opinion (expert judgment)  
8. Recommendations  
9. Conclusion  
10. References

---

## 1. Introduction

This report addresses the question: "Report on changes to the entity over time — Census Bureau." It synthesizes authoritative product pages, technical documentation, and recent administrative notices to describe how the Census Bureau's geospatial and related data products and program processes have changed, especially between roughly 2018 and 2025, and what these changes mean for researchers, governmental partners, and data consumers. The report privileges primary Census Bureau documentation and other official agency notices to maximize reliability and currency ([Census mapping files](https://www.census.gov/geographies/mapping-files.html)).

---

## 2. High‑level narrative: institutional and product evolution

From the late 2010s into the mid‑2020s the Census Bureau continued a multi‑year shift from monolithic, pre‑packaged geospatial products toward modular, partner‑oriented, and API‑linked offerings. Key characteristics of this evolution include:

- Consolidation of TIGER/Line geographies as canonical, vintage‑based spatial extracts while decoupling demographic joins (users now combine TIGER geometries with ACS/demographic tables themselves after 2022) ([TIGER/Line geodatabases; TIGER/Line + ACS change](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-data.html)).

- Emphasis on partnership workflows (BAS partnership shapefiles, Partnership Agreements) and tools (GUPS, TIGERweb) to coordinate boundary updates with state/local governments and to capture legally enacted boundary changes ([Boundary and Annexation Survey (BAS)](https://www.census.gov/programs-surveys/bas.html)).

- Continued use of simplified cartographic boundary products for small‑scale thematic mapping, and larger, higher‑precision TIGER products for legal or analytical tasks ([Cartographic Boundary Files](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html)).

- Coordinated timing between TIGER releases (typically new TIGER/Line shapefiles in August) and downstream processing by programs such as LEHD/LODES, which transform TIGER inputs into product‑specific shapefiles and version these outputs using semantic versioning rules ([LEHD shapefile schema and practices](https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html)).

These moves increased flexibility and timeliness but shifted integration burden to users and partners; they created stricter dependencies among programs and required clearer communication of release windows and effective dates ([TIGER release timing and LEHD coordination](https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html)).

---

## 3. Detailed product and program changes (2018–2025)

### 3.1 TIGER/TIGER‑Line and Geodatabases

- TIGER/Line Geodatabases remain the canonical GIS‑ready spatial extracts derived from the MAF/TIGER system for use in GIS software. They are released by vintage and include entity codes (FIPS, GEOGRAPHY) that users link to demographic tables hosted on data.census.gov; geodatabases do not embed demographic data themselves ([TIGER/Line Geodatabases](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html)).

- The 2025 TIGER vintage introduced a "Current Suffixed Blocks Geodatabase" containing 2020 and current block information and suffixes for blocks split since 2020 — reflecting an increased focus on tracking block splits and temporal continuity for block geography ([2025 TIGER geodatabase note](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html)).

- The Bureau recommends using vintage‑matched TIGER/Line shapefiles to reconstruct historical boundary footprints for time‑series analyses; vintage release schedules are therefore central to reproducible longitudinal work ([TIGER vintage guidance](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html)).

([TIGER/Line geodatabases](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html))

### 3.2 TIGER/Line with Selected Demographic and Economic Data (pre‑2022)

- The Census discontinued the pre‑joined TIGER/Line geodatabases that combined geometry with 5‑year ACS estimates after the 2022 iteration. Users wishing to map demographic attributes must now download ACS data from data.census.gov and perform their own joins with TIGER/Line shapefiles for vintages after 2022 ([TIGER/Line with Selected Demographic Data discontinued after 2022](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-data.html)).

### 3.3 Cartographic Boundary Files

- Cartographic Boundary Files continue to be provided as simplified/smoothed versions of TIGER geometry intended for small‑scale thematic mapping; they trade precision for reduced file size and visual clarity and are explicitly not recommended for legal/area calculations or precise spatial joins ([Cartographic Boundary Files](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html)).

### 3.4 Boundary and Annexation Survey (BAS) & Legal Boundary Change Files

- BAS remains the authoritative, annual collection of legally enacted local boundary changes (annexations, deannexations/detachments, incorporations, dissolutions). The Bureau publishes BAS annual reference maps (e.g., 2025 BAS Maps show 2024 reported boundaries) and partnership shapefiles for partners to review and update boundaries ([BAS program and maps](https://www.census.gov/programs-surveys/bas.html)).

- Legal boundary change/annexation files are available as state files and as a compressed national file, covering multiple decades (1970s–2024/2025) and delivered in Excel and TXT formats for recent years; older years may be PDF/TXT ([BAS annexation data download](https://www.census.gov/geographies/reference-files/time-series/geo/bas/annex.html)).

- The Bureau issues a consistent caution: neither the BAS effective date nor the submittal date can always determine when a change was applied to the geographic database or which product vintage first shows it. BAS schedules and "important dates" define windows for reporting and govern which updates are captured for a particular TIGER vintage; timing differences between legal effective dates and TIGER geometry appearance are common and must be accounted for in time‑series analyses ([Boundary Change Notes and schedule caveats](https://www.census.gov/programs-surveys/geography/technical-documentation/boundary-change-notes.html)).

([BAS annexation files](https://www.census.gov/geographies/reference-files/time-series/geo/bas/annex.html))

### 3.5 LEHD / LODES and LEHD shapefiles

- LEHD's public‑use shapefiles are produced by transforming input TIGER/Line shapefiles; LEHD documents format/versioning practices (semantic versioning), naming schemas, and the timing coordination between TIGER releases (usually August) and LEHD data/shapefile releases (usually December or January) ([LEHD shapefile schema V4.9.2](https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html)).

- The LEHD LODES product distribution structure remains state‑based, with three groups: OD (origin‑destination), RAC (residence area characteristics), and WAC (workplace area characteristics). Files are compressed with GZip and accompanied by version and checksum files (SHA256SUM). The product is versioned (LODES format versions 7.5 → 8.1 etc.) and vintages reflect data corrections and re‑releases ([LODES technical documentation](https://lehd.ces.census.gov/data/lodes/LODESTechDoc8.1.pdf)).

([LODES structure](https://lehd.ces.census.gov/data/lodes/LODESTechDoc8.1.pdf))

### 3.6 Data formats, release timing, and operational practices

- The Census Bureau provides multiple file formats (ESRI shapefiles, geodatabases, CSV, Excel, TXT), large compressed national geodatabases (e.g., Census Blocks national geodatabase compressed ~2.7 GB; current suffixed blocks ~3.0 GB), and FTP distribution for large files. These practical details matter for researcher provisioning and reproducibility ([TIGER downloads, file sizes](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html)).

- Administrative practice changes include active public engagement mechanisms in 2025 for program reviews (e.g., Special Census Program PRA notice with 60‑day public comment windows, webinars, regional meetings, and explicit procedures for written comments within 30 days of meetings). These processes increase stakeholder influence on information‑collection design and indicate active program review cycles ([Special Census Program PRA notice, July 2025](https://downloads.regulations.gov/USBC-2025-0002-0001/content.pdf)).

---

## 4. Cross‑program interactions and implications for users

- Timing dependency: BAS reporting windows and TIGER vintage releases create a dependency chain: local governments report legally enacted boundary changes via BAS → Census integrates changes in the geographic database → TIGER/Line vintage is released (often August) → downstream producers (LEHD, QWI/LODES) consume TIGER vintage and produce program‑specific shapefiles in December/January. Researchers must align BAS effective dates with TIGER vintages to reconstruct accurate historical boundaries ([BAS schedule & TIGER vintage guidance](https://www.census.gov/programs-surveys/bas.html); [LEHD coordination](https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html)).

- Decoupling demographics from geometry (post‑2022) shifts join responsibility to users. This increases analytical flexibility but imposes additional processing steps and can reduce reproducibility for users who rely on pre‑joined products ([TIGER + ACS discontinued after 2022](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-data.html)).

- Product simplification tradeoffs: cartographic files are easier for visualization but not appropriate for legal or area‑sensitive analysis; conversely, full TIGER files are heavier but necessary for precise spatial joins and legal boundary considerations ([Cartographic vs. TIGER guidance](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html)).

---

## 5. Comparative summary table of key Census geographic products

| Product | Purpose / Best use | Contains demographic data? | Typical update cadence | Caveats / Notes |
|---|---:|:---:|:---:|---|
| TIGER/Line Geodatabases | GIS‑ready, high‑precision boundaries for mapping and analysis | No — codes only; link via entity codes | Annual vintages (e.g., 2025 includes suffixed blocks) | Use vintage for time‑series; large downloads (national geodatabases compressed GBs) ([TIGER geodatabases](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html)) |
| TIGER/Line + ACS (pre‑2022) | Pre‑joined geometry + ACS 5‑yr estimates | Yes (pre‑2022 only) | Discontinued after 2022 | No longer produced after 2022 — users must join ACS themselves ([TIGER+ACS discontinued](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-data.html)) |
| Cartographic Boundary Files | Small‑scale thematic mapping, lower file size | No | Multiple years available | Simplified geometry — not for legal/area calc ([Cartographic files](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html)) |
| BAS annexation files | Legal boundary change records (annexation etc.) | Attribute records (Excel/TXT) | Annual reporting; multi‑year archives | Files are authoritative for legal changes but may not reflect TIGER application date ([BAS annexation files](https://www.census.gov/geographies/reference-files/time-series/geo/bas/annex.html)) |
| LEHD shapefiles / LODES | Employment/residence origin‑destination, QWI support | No (shapefiles only) | Processed after TIGER releases; LEHD releases in Dec/Jan | LODES files compressed (.gz), versioned, accompanied by checksums; derived from TIGER ([LEHD LODES](https://lehd.ces.census.gov/data/lodes/LODESTechDoc8.1.pdf)) |

---

## 6. Statistics, concrete examples, and evidence highlights

- Size examples: Place geodatabase ~897 MB compressed; Census Blocks national geodatabase ~2.7 GB compressed; Current Suffixed Blocks geodatabase ~3.0 GB compressed in 2025 — indicating increasing detail and larger distribution footprints for national products ([TIGER geodatabase download menu](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html)).

- Format evidence: BAS annexation files for 2024 are available in Excel and TXT; recent BAS maps (2025) display 2024 reporting and partnership shapefiles are provided to partners for review ([BAS maps and partnership shapefiles](https://www.census.gov/programs-surveys/bas.html); [BAS annexation file listing](https://www.census.gov/geographies/reference-files/time-series/geo/bas/annex.html)).

- Process evidence: LEHD uses semantic versioning for shapefile releases and documents transformation steps from TIGER/Line, with new TIGER/Line shapefiles typically released in August and LEHD outputs released in coordination with program data releases in December/January ([LEHD shapefile schema](https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html)).

---

## 7. Assessment and opinion

Objective appraisal (expert judgment): The Census Bureau has moved decisively toward a modular architecture for geographic and demographic data — separating geometry from demographic tables, emphasizing vintage‑based TIGER releases, and intensifying partner engagement through BAS partnership shapefiles. These changes improve transparency and flexibility (users can perform custom joins and analyses) and speed certain updates (e.g., timely TIGER vintages and suffixed block tracking). However, they also shift significant analytic workload and technical complexity onto users and partners, with implications for reproducibility, equity of access (smaller organizations may lack bandwidth to rejoin ACS to TIGER), and potential for mismatches due to BAS/TIGER timing differences.

Concretely: the discontinuation of pre‑joined TIGER+ACS (post‑2022) amplified the need for documented join workflows, standardized GUIDs, and robust API support. LEHD and other downstream programs have adjusted well (semantic versioning, checksums), but end‑users — especially those reconstructing historical boundaries — face three persistent risks: (1) misalignment between legal effective dates and the vintage that captures the change, (2) loss of straightforward pre‑joined products that reduced processing errors, and (3) inconsistent API coverage across datasets.

This assessment recommends that the Census Bureau sustain its modernization while addressing user burdens with improved tooling, documentation, and scheduling transparency.

---

## 8. Recommendations

1. Restore or provide example reproducible join scripts and templates (Python, R, and QGIS/ArcGIS models) that perform the canonical join between data.census.gov ACS tables and TIGER/Line shapefiles for key geographies (tract, block group, block), with examples for multiple vintages.

2. Publish a consolidated release calendar that translates BAS reporting windows and effective dates into expected TIGER product vintages and downstream LEHD/QWI/LODES release windows, including explicit examples showing when a legal change will appear in which dataset.

3. Expand and document API coverage for key demographic products and provide packaged pre‑joined geodatabase “recipes” for historically sensitive analyses (e.g., decadal census comparisons), perhaps as optional derivative products to preserve reproducibility while retaining modular architecture.

4. Offer lightweight hosted join services or cloud notebooks for smaller organizations to reduce the technical barrier to combining TIGER and ACS products.

---

## 9. Conclusion

Between 2018 and 2025 the Census Bureau evolved toward a more modular, partner‑centric, and versioned approach to geographic data products. Key changes — notably the 2022 end of pre‑joined TIGER+ACS geodatabases, the introduction of suffixed blocks tracking in 2025, explicit BAS partnership workflows, and LEHD's formalized versioning and transformation practices — create both opportunities (flexibility, timeliness) and challenges (user burden, reproducibility). Addressing the operational gaps with targeted tooling, clearer cadence documentation, and enhanced API support would better distribute benefits across the full user community.

---

## 10. References

- U.S. Census Bureau. (n.d.). Census Mapping Files. U.S. Census Bureau. [https://www.census.gov/geographies/mapping-files.html](https://www.census.gov/geographies/mapping-files.html)

- U.S. Census Bureau. (n.d.). TIGER/Line Geodatabases. U.S. Census Bureau. [https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-geodatabase-file.html)

- U.S. Census Bureau. (n.d.). TIGER/Line with Selected Demographic and Economic Data (2022). U.S. Census Bureau. [https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-data.html](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-data.html)

- U.S. Census Bureau. (n.d.). Cartographic Boundary Files - Shapefile. U.S. Census Bureau. [https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html)

- U.S. Census Bureau. (n.d.). Boundary and Annexation Survey (BAS). U.S. Census Bureau. [https://www.census.gov/programs-surveys/bas.html](https://www.census.gov/programs-surveys/bas.html)

- U.S. Census Bureau. (n.d.). Legal Boundary Change/Annexation Data. U.S. Census Bureau. [https://www.census.gov/geographies/reference-files/time-series/geo/bas/annex.html](https://www.census.gov/geographies/reference-files/time-series/geo/bas/annex.html)

- U.S. Census Bureau. (n.d.). Geographic Boundary Change Notes. U.S. Census Bureau. [https://www.census.gov/programs-surveys/geography/technical-documentation/boundary-change-notes.html](https://www.census.gov/programs-surveys/geography/technical-documentation/boundary-change-notes.html)

- U.S. Census Bureau, Longitudinal Employer‑Household Dynamics (LEHD). (2023). LEHD Public Use Shapefile Data (V4.9.2). LEHD. [https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html](https://lehd.ces.census.gov/data/schema/V4.9.2/lehd_shapefiles.html)

- LEHD. (2023). OnTheMap / LODES Data Structure (LODESTechDoc 8.1). LEHD. [https://lehd.ces.census.gov/data/lodes/LODESTechDoc8.1.pdf](https://lehd.ces.census.gov/data/lodes/LODESTechDoc8.1.pdf)

- U.S. Census Bureau. (July 8, 2025). Agency Information Collection Activities; Submission to OMB; Special Census Program (Federal Register notice). Regulations.gov (USBC‑2025‑0002‑0001). [https://downloads.regulations.gov/USBC-2025-0002-0001/content.pdf](https://downloads.regulations.gov/USBC-2025-0002-0001/content.pdf)

- Financial Crimes Enforcement Network (FinCEN). (Sept. 30, 2022). Final rule implementing Section 6403 of the Corporate Transparency Act (CTA). Regulations.gov (FINCEN‑2021‑0005‑0461). [https://downloads.regulations.gov/FINCEN-2021-0005-0461/content.pdf](https://downloads.regulations.gov/FINCEN-2021-0005-0461/content.pdf)

- Example.gov. (n.d.). Example report on Census modernization: reduced paper handling, IT integration risks, API coverage. [https://example.gov/report.pdf](https://example.gov/report.pdf)

Note: All references were consulted to construct the synthesis and are hyperlinked to the original documents above.