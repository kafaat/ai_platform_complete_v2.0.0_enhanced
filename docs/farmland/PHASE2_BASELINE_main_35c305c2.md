# SAHOOL Farmland Phase 2 — inventory against main 35c305c2 (2026-11-25)

Read-only inventory by three search agents; paths relative to the repo root (SP = services/sahool-platform, SS = services/soil-service, fms = services/field-management-service).

## 01 Standards & compliance
Exists: SP/core/engines/ky_registry.py:26 (versioned cited table, FAO-33); SP/core/thresholds.py:1; SP/core/policy_registry.py:1; SP/core/salinity_policy.py:73 (rule + reasons/signals); services/ai_agronomist/compliance_validator.py (6-line PHI stub); services/knowledge-graph/kg_store.py:565; services/rag-retrieval/main.py:307,406; shared/knowledge/source_registry.py:81.
Missing: standards/clauses tables or registry, versions/supersession, compliance engine with evidence, country/region/project profiles, KG/RAG standard types.

## 02 Land quality & soil
Exists: SS/p2_products.py:284 salinity/sodicity; SS/p3_products.py:210 drainage, :352 reclamation (gypsum/leaching blocked without lab evidence), :473 economics; SS/p1_products.py:22 sampling plan; SS/p4_governance.py:95,146; SS/soil_science.py:88 suitability; SP/core/engines/suitability.py:96 (S1-S3/N); SP/api/crop_suitability.py; SP/core/variety_suitability.py; SP/api/salinity_management.py:81 (FAO-56 LR); SP/core/irrigation_water_analysis.py:160; fertility engines + nutrient_4r; soil_sampling routes; SP/core/soil_feedback_trend.py.
Missing: land capability classification; gypsum requirement; ESP from CEC; measured compaction engine; land-quality index; suitability implemented 4 times.

## 03 Water, irrigation & drainage
Exists: SP/api/canonical_well_capability.py:187 (v170 tables); SP/api/canonical_hydraulic_capability.py:55,117 (v171); SP/api/irrigation_engineering_workspace.py (v185, routes); SP/api/irrigation_network.py:72; capability graph v175; capacity reservation v195/v205; water ledger v98/v279-v285; pivot geometry; SS drainage assessment.
Missing: EPANET/WNTR; DU/CU uniformity; drainage design (Hooghoudt); aquifer/safe yield; time-stepped tank/pump simulation; pumping-test ingest API; farm-level budget (unverified).

## 04 Energy & economics
Exists: SP/api/canonical_energy_microgrid_capability.py:92 hourly PV (no runtime caller; v174 tables); pump curves (v171, no caller); SP/api/hourly_energy_aware_irrigation_mpc.py:151 (routed, v179); SP/core/engines/water_cost.py (no route); SP/api/farm_economics.py feasibility/break-even (routed); SP/core/farm_costing.py + ledger routes (v100/v101); SS NPV pattern; v276 task cost links; inventory items only.
Missing: BOQ; capex/opex/ROI for PV/pumps; diesel/grid/solar lifecycle comparison; PV↔pump-curve coupling; procurement/unit prices.

## 05 GIS, levelling & remote sensing
Exists: raster-service terrain_analysis.py (slope/aspect, field terrain, route), contours/hillshade, DEM registry/quality; SP/core/engines/dem_enrichment.py; SS terrain derivatives (v162); band_math indices (NDVI/NDRE/NDMI…); change_detection; management_zones; salinity_calibration; vegetation-analysis ground verification; zones/prescriptions tables (v115).
Missing: cut/fill, levelling design, topsoil strip/reuse; RTK point ingest; composite land-quality map; general ground-truth accuracy metrics.

## 06 Advisor, GeoRAG & decision
Exists: SP/core/rag/production_qdrant.py:1617 hybrid retriever (scope keys crop/region/field_id); rag-retrieval /v1/search; ai_agronomist routes + tool_executor; engine proposals behind SAHOOL_ADVISOR_ENGINE_PROPOSALS (off); SP/api/unified_decision.py:338; decision_record/outcome/lineage (v77-v82); decision-service (interim mirror); recommendations hub; work_order_from_recommendation; outcome measurement.
Missing: spatial GeoRAG; engines not wired into advisor/unified_decision; no zone/geometry on recommendations/decisions; no recommendation→inventory/cost link except via work orders and v276.

## 07 Inspection, assets & maintenance
Exists: inspection chain v246/v274/v275/v277 + fms/fm_task_inspection.py + web/mobile; task cost trace v276; equipment v23 + routes + equipment_intelligence + web/mobile; irrigation commissioning v177/v186; work orders v75; field forms v204.
Missing: non-conformance/corrective actions; clause-based inspection plans and acceptance forms; as-built; generic asset registry/hierarchy/geometry; preventive plans; predictive maintenance; asset map layer.

## 08 Integration & acceptance
Exists: 76 live-PG test files (`git ls-tree -r --name-only 35c305c2 | grep -cE '(^|/)test_[^/]*live_pg[^/]*\.py$'`; counting by a live-PG marker gives more); tenant isolation tests; chain segments (anomaly→task; recommendation→work order→task→outcome; task→inspection→close→cost); docker-compose.evidence-lab.yml.
Missing: single end-to-end chain test; 180 ha / two 50 ha pivots fixture; farm acceptance scenario folder.

## P2 infrastructure
Exists: windbreaks (engine + UI); water harvesting + upstream flood; erosion risk indicator. Missing: farm roads; flood protection structures; erosion-control design; environmental impact assessment.
