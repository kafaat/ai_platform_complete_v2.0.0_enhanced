-- SAHOOL migrations runner generated from migrations/MANIFEST.txt
-- Do not edit manually; MANIFEST.txt is the single source of truth.
-- Usage: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts_v9/run_migrations.sql
\set ON_ERROR_STOP on
\timing on

\echo '═══ 1. init_v8.sql ═══'
\i migrations/init_v8.sql

\echo '═══ 2. v9_foundation.sql ═══'
\i migrations/v9_foundation.sql

\echo '═══ 3. v9_auth_improvements.sql ═══'
\i migrations/v9_auth_improvements.sql

\echo '═══ 4. v9_new_tables.sql ═══'
\i migrations/v9_new_tables.sql

\echo '═══ 5. v9_onboarding.sql ═══'
\i migrations/v9_onboarding.sql

\echo '═══ 6. v9_market.sql ═══'
\i migrations/v9_market.sql

\echo '═══ 7. v9_automation.sql ═══'
\i migrations/v9_automation.sql

\echo '═══ 8. v9_automation_persistence.sql ═══'
\i migrations/v9_automation_persistence.sql

\echo '═══ 9. v9_odoo_bridge.sql ═══'
\i migrations/v9_odoo_bridge.sql

\echo '═══ 10. v9_edge_idempotency.sql ═══'
\i migrations/v9_edge_idempotency.sql

\echo '═══ 11. v9_edge_occurred_at.sql ═══'
\i migrations/v9_edge_occurred_at.sql

\echo '═══ 12. v9_rls_tenant_isolation.sql ═══'
\i migrations/v9_rls_tenant_isolation.sql

\echo '═══ 13. v10_command_store_lifecycle.sql ═══'
\i migrations/v10_command_store_lifecycle.sql

\echo '═══ 14. v9_lifecycle_occurred_at.sql ═══'
\i migrations/v9_lifecycle_occurred_at.sql

\echo '═══ 15. v11_events_bus.sql ═══'
\i migrations/v11_events_bus.sql

\echo '═══ 16. v12_trueup_sharing.sql ═══'
\i migrations/v12_trueup_sharing.sql

\echo '═══ 17. v13_geospatial_core.sql ═══'
\i migrations/v13_geospatial_core.sql

\echo '═══ 18. v14_imagery_storage.sql ═══'
\i migrations/v14_imagery_storage.sql

\echo '═══ 19. v9_rls_force_all.sql ═══'
\i migrations/v9_rls_force_all.sql

\echo '═══ 20. v15_offline_synced_operations.sql ═══'
\i migrations/v15_offline_synced_operations.sql

\echo '═══ 21. v16_workflow_state.sql ═══'
\i migrations/v16_workflow_state.sql

\echo '═══ 22. v17_workflow_state_full.sql ═══'
\i migrations/v17_workflow_state_full.sql

\echo '═══ 23. v18_entity_ids_text.sql ═══'
\i migrations/v18_entity_ids_text.sql

\echo '═══ 24. v19_farms.sql ═══'
\i migrations/v19_farms.sql

\echo '═══ 25. v20_automation_tables.sql ═══'
\i migrations/v20_automation_tables.sql

\echo '═══ 26. v21_mfa.sql ═══'
\i migrations/v21_mfa.sql

\echo '═══ 27. v22_inventory.sql ═══'
\i migrations/v22_inventory.sql

\echo '═══ 28. v23_equipment.sql ═══'
\i migrations/v23_equipment.sql

\echo '═══ 29. v24_iot_devices.sql ═══'
\i migrations/v24_iot_devices.sql

\echo '═══ 30. v25_irrigation.sql ═══'
\i migrations/v25_irrigation.sql

\echo '═══ 31. v26_master_data.sql ═══'
\i migrations/v26_master_data.sql

\echo '═══ 32. v27_gis_enforce.sql ═══'
\i migrations/v27_gis_enforce.sql

\echo '═══ 33. v28_settings.sql ═══'
\i migrations/v28_settings.sql

\echo '═══ 34. v29_documents.sql ═══'
\i migrations/v29_documents.sql

\echo '═══ 35. v30_fields_geometry.sql ═══'
\i migrations/v30_fields_geometry.sql

\echo '═══ 36. v31_fields_manager.sql ═══'
\i migrations/v31_fields_manager.sql

\echo '═══ 37. v32_seasons.sql ═══'
\i migrations/v32_seasons.sql

\echo '═══ 38. v33_fields_extended.sql ═══'
\i migrations/v33_fields_extended.sql

\echo '═══ 39. v34_farms_org.sql ═══'
\i migrations/v34_farms_org.sql

\echo '═══ 40. v35_activities.sql ═══'
\i migrations/v35_activities.sql

\echo '═══ 41. v36_alerts.sql ═══'
\i migrations/v36_alerts.sql

\echo '═══ 42. v37_fields_advanced.sql ═══'
\i migrations/v37_fields_advanced.sql

\echo '═══ 43. v38_notif_channels.sql ═══'
\i migrations/v38_notif_channels.sql

\echo '═══ 44. v39_season_simulation.sql ═══'
\i migrations/v39_season_simulation.sql

\echo '═══ 45. v40_verification.sql ═══'
\i migrations/v40_verification.sql

\echo '═══ 46. v41_fields_irrigation.sql ═══'
\i migrations/v41_fields_irrigation.sql

\echo '═══ 47. v42_seasons_kpis.sql ═══'
\i migrations/v42_seasons_kpis.sql

\echo '═══ 48. v43_fields_geom_index.sql ═══'
\i migrations/v43_fields_geom_index.sql

\echo '═══ 49. v44_one_active_season.sql ═══'
\i migrations/v44_one_active_season.sql

\echo '═══ 50. v45_activity_season_fk.sql ═══'
\i migrations/v45_activity_season_fk.sql

\echo '═══ 51. v46_lifecycle_event_sync.sql ═══'
\i migrations/v46_lifecycle_event_sync.sql

\echo '═══ 52. v47_schema_integrity.sql ═══'
\i migrations/v47_schema_integrity.sql

\echo '═══ 53. v48_activity_season_fk_dlq.sql ═══'
\i migrations/v48_activity_season_fk_dlq.sql

\echo '═══ 54. v49_zone_key_recommendation_outcomes.sql ═══'
\i migrations/v49_zone_key_recommendation_outcomes.sql

\echo '═══ 55. v50_soil_lab_tests.sql ═══'
\i migrations/v50_soil_lab_tests.sql

\echo '═══ 56. v51_review_round2_fixes.sql ═══'
\i migrations/v51_review_round2_fixes.sql

\echo '═══ 57. v52_season_agronomy_fields.sql ═══'
\i migrations/v52_season_agronomy_fields.sql

\echo '═══ 58. v53_field_state_projection.sql ═══'
\i migrations/v53_field_state_projection.sql

\echo '═══ 59. v54_imagery_ndvi_value.sql ═══'
\i migrations/v54_imagery_ndvi_value.sql

\echo '═══ 60. v55_field_state_agronomic.sql ═══'
\i migrations/v55_field_state_agronomic.sql

\echo '═══ 61. v9_append_only_enforcement.sql ═══'
\i migrations/v9_append_only_enforcement.sql

\echo '═══ 62. v56_rls_dynamic_all.sql ═══'
\i migrations/v56_rls_dynamic_all.sql

\echo '═══ 63. v57_rls_dynamic_indexes.sql ═══'
\i migrations/v57_rls_dynamic_indexes.sql

\echo '═══ 64. v58_field_boundary_quality.sql ═══'
\i migrations/v58_field_boundary_quality.sql

\echo '═══ 65. v59_boundary_topology_fn.sql ═══'
\i migrations/v59_boundary_topology_fn.sql

\echo '═══ 66. v60_event_snapshots.sql ═══'
\i migrations/v60_event_snapshots.sql

\echo '═══ 67. v61_fields_row_version.sql ═══'
\i migrations/v61_fields_row_version.sql

\echo '═══ 68. v62_field_lifecycle_null_season_guard.sql ═══'
\i migrations/v62_field_lifecycle_null_season_guard.sql

\echo '═══ 69. v63_events_seq_deterministic_order.sql ═══'
\i migrations/v63_events_seq_deterministic_order.sql

\echo '═══ 70. v64_seasons_row_version.sql ═══'
\i migrations/v64_seasons_row_version.sql

\echo '═══ 71. v65_harvest_traceability.sql ═══'
\i migrations/v65_harvest_traceability.sql

\echo '═══ 72. v66_dispatch_decisions.sql ═══'
\i migrations/v66_dispatch_decisions.sql

\echo '═══ 73. v67_dispatch_hardening.sql ═══'
\i migrations/v67_dispatch_hardening.sql

\echo '═══ 74. v68_execution_ledger.sql ═══'
\i migrations/v68_execution_ledger.sql

\echo '═══ 75. v69_decision_policies.sql ═══'
\i migrations/v69_decision_policies.sql

\echo '═══ 76. v70_rls_with_check_propagate.sql ═══'
\i migrations/v70_rls_with_check_propagate.sql

\echo '═══ 77. v71_rls_missing_tables.sql ═══'
\i migrations/v71_rls_missing_tables.sql

\echo '═══ 78. v72_event_outbox_rls.sql ═══'
\i migrations/v72_event_outbox_rls.sql

\echo '═══ 79. v73_weather_automation_rls.sql ═══'
\i migrations/v73_weather_automation_rls.sql

\echo '═══ 80. v74_weather_intelligence.sql ═══'
\i migrations/v74_weather_intelligence.sql

\echo '═══ 81. v75_work_orders.sql ═══'
\i migrations/v75_work_orders.sql

\echo '═══ 82. v76_crop_kc_timeseries.sql ═══'
\i migrations/v76_crop_kc_timeseries.sql

\echo '═══ 83. v77_recommendations.sql ═══'
\i migrations/v77_recommendations.sql

\echo '═══ 84. v78_decision_record.sql ═══'
\i migrations/v78_decision_record.sql

\echo '═══ 85. v79_outcome_record.sql ═══'
\i migrations/v79_outcome_record.sql

\echo '═══ 86. v80_calibration_override.sql ═══'
\i migrations/v80_calibration_override.sql

\echo '═══ 87. v81_actuator_command_dedup.sql ═══'
\i migrations/v81_actuator_command_dedup.sql

\echo '═══ 88. v82_lineage_link.sql ═══'
\i migrations/v82_lineage_link.sql

\echo '═══ 89. v83_notification_delivery.sql ═══'
\i migrations/v83_notification_delivery.sql

\echo '═══ 90. v84_calibration_audit.sql ═══'
\i migrations/v84_calibration_audit.sql

\echo '═══ 91. v85_nl_gis_audit.sql ═══'
\i migrations/v85_nl_gis_audit.sql

\echo '═══ 92. v86_calibration_evidence_trigger.sql ═══'
\i migrations/v86_calibration_evidence_trigger.sql

\echo '═══ 93. v87_audit_log_tenant.sql ═══'
\i migrations/v87_audit_log_tenant.sql

\echo '═══ 94. v88_field_owner_function.sql ═══'
\i migrations/v88_field_owner_function.sql

\echo '═══ 95. v89_invitations.sql ═══'
\i migrations/v89_invitations.sql

\echo '═══ 96. v90_break_glass.sql ═══'
\i migrations/v90_break_glass.sql

\echo '═══ 97. v91_workflow_compensation_failures.sql ═══'
\i migrations/v91_workflow_compensation_failures.sql

\echo '═══ 98. v92_offline_pending_ops.sql ═══'
\i migrations/v92_offline_pending_ops.sql

\echo '═══ 99. v93_processed_events.sql ═══'
\i migrations/v93_processed_events.sql

\echo '═══ 100. v94_scouting_pins.sql ═══'
\i migrations/v94_scouting_pins.sql

\echo '═══ 101. v95_prescriptions.sql ═══'
\i migrations/v95_prescriptions.sql

\echo '═══ 102. v96_spatial_geometry_integrity.sql ═══'
\i migrations/v96_spatial_geometry_integrity.sql

\echo '═══ 103. v97_user_self_with_check.sql ═══'
\i migrations/v97_user_self_with_check.sql

\echo '═══ 104. v98_water_ledger.sql ═══'
\i migrations/v98_water_ledger.sql

\echo '═══ 105. v99_imagery_spectral_indices.sql ═══'
\i migrations/v99_imagery_spectral_indices.sql

\echo '═══ 106. v100_farm_operations_ledger.sql ═══'
\i migrations/v100_farm_operations_ledger.sql

\echo '═══ 107. v101_farm_budget_costing.sql ═══'
\i migrations/v101_farm_budget_costing.sql

\echo '═══ 108. v102_farm_closed_loop.sql ═══'
\i migrations/v102_farm_closed_loop.sql

\echo '═══ 109. v103_fields_planting_date.sql ═══'
\i migrations/v103_fields_planting_date.sql

\echo '═══ 110. v104_fields_create_contract.sql ═══'
\i migrations/v104_fields_create_contract.sql

\echo '═══ 111. v_ai_recommendation_runtime.sql ═══'
\i migrations/v_ai_recommendation_runtime.sql

\echo '═══ 112. v105_enterprise_imagery_best_practices.sql ═══'
\i migrations/v105_enterprise_imagery_best_practices.sql

\echo '═══ 113. v114_cloud_native_gis_best_practices.sql ═══'
\i migrations/v114_cloud_native_gis_best_practices.sql

\echo '═══ 114. v115_precision_agriculture_phase6.sql ═══'
\i migrations/v115_precision_agriculture_phase6.sql

\echo '═══ 115. v116_enterprise_gis_phase7.sql ═══'
\i migrations/v116_enterprise_gis_phase7.sql

\echo '═══ 116. v117_global_scale_phase8.sql ═══'
\i migrations/v117_global_scale_phase8.sql

\echo '═══ 117. v118_phase9_autonomous_farm_os.sql ═══'
\i migrations/v118_phase9_autonomous_farm_os.sql

\echo '═══ 118. v119_phase10_continuous_learning.sql ═══'
\i migrations/v119_phase10_continuous_learning.sql

\echo '═══ 119. v120_phase11_federated_agents.sql ═══'
\i migrations/v120_phase11_federated_agents.sql

\echo '═══ 120. v121_marketplace_ecosystem.sql ═══'
\i migrations/v121_marketplace_ecosystem.sql

\echo '═══ 121. v106_phase9_10_runtime_strengthening.sql ═══'
\i migrations/v106_phase9_10_runtime_strengthening.sql

\echo '═══ 122. v107_phase9_10_event_drift_hardening.sql ═══'
\i migrations/v107_phase9_10_event_drift_hardening.sql

\echo '═══ 123. v108_phase10_feature_store_model_registry_runtime.sql ═══'
\i migrations/v108_phase10_feature_store_model_registry_runtime.sql

\echo '═══ 124. v109_phase9_iot_execution_adapters.sql ═══'
\i migrations/v109_phase9_iot_execution_adapters.sql

\echo '═══ 125. v110_phase12_plugin_sandbox_runtime.sql ═══'
\i migrations/v110_phase12_plugin_sandbox_runtime.sql

\echo '═══ 126. v111_phase11_federated_agent_runtime.sql ═══'
\i migrations/v111_phase11_federated_agent_runtime.sql

\echo '═══ 127. v112_mobile_offline_sync_runtime.sql ═══'
\i migrations/v112_mobile_offline_sync_runtime.sql

\echo '═══ 128. v113_phase_runtime_workers_jobs.sql ═══'
\i migrations/v113_phase_runtime_workers_jobs.sql

\echo '═══ 129. v122_rls_with_check_session_unification.sql ═══'
\i migrations/v122_rls_with_check_session_unification.sql

\echo '═══ 130. v123_rls_with_check_preserve_using.sql ═══'
\i migrations/v123_rls_with_check_preserve_using.sql

\echo '═══ 131. v124_tenant_ai_policies.sql ═══'
\i migrations/v124_tenant_ai_policies.sql

\echo '═══ 132. v125_tenant_ai_capabilities.sql ═══'
\i migrations/v125_tenant_ai_capabilities.sql

\echo '═══ 133. v126_agent_tool_audit.sql ═══'
\i migrations/v126_agent_tool_audit.sql

\echo '═══ 134. v127_evidence_context_hardening.sql ═══'
\i migrations/v127_evidence_context_hardening.sql

\echo '═══ 135. v128_mfa_hardening.sql ═══'
\i migrations/v128_mfa_hardening.sql

\echo '═══ 136. v129_mfa_hardening_followup.sql ═══'
\i migrations/v129_mfa_hardening_followup.sql

\echo '═══ 137. v130_soil_lab_evidence_hardening.sql ═══'
\i migrations/v130_soil_lab_evidence_hardening.sql

\echo '═══ 138. v131_imagery_quality_metadata.sql ═══'
\i migrations/v131_imagery_quality_metadata.sql

\echo '═══ 139. v132_field_state_recompute_provenance.sql ═══'
\i migrations/v132_field_state_recompute_provenance.sql

\echo '═══ 140. v133_actuation_killswitch.sql ═══'
\i migrations/v133_actuation_killswitch.sql
\echo '═══ 141. v134_fields_geometry_integrity.sql ═══'
\i migrations/v134_fields_geometry_integrity.sql
\echo '═══ 142. v135_workflow_state_lease.sql ═══'
\i migrations/v135_workflow_state_lease.sql
\echo '═══ 143. v136_irrigation_runs.sql ═══'
\i migrations/v136_irrigation_runs.sql
\echo '═══ 144. v138_offline_pending_ops_terminal.sql ═══'
\i migrations/v138_offline_pending_ops_terminal.sql
\echo '═══ 145. v139_field_geometry_history_append_only.sql ═══'
\i migrations/v139_field_geometry_history_append_only.sql
\echo '═══ 146. v140_outbox_delivery_attempts.sql ═══'
\i migrations/v140_outbox_delivery_attempts.sql
\echo '═══ 147. v141_mfa_totp_antireplay.sql ═══'
\i migrations/v141_mfa_totp_antireplay.sql
\echo '═══ 148. v142_raster_assets_dedup_traceability.sql ═══'
\i migrations/v142_raster_assets_dedup_traceability.sql
\echo '═══ 149. v143_raster_assets_lifecycle_lineage.sql ═══'
\i migrations/v143_raster_assets_lifecycle_lineage.sql
\echo '═══ 150. v144_backfill_runs.sql ═══'
\i migrations/v144_backfill_runs.sql
\echo '═══ 151. v145_raster_assets_product_dedup.sql ═══'
\i migrations/v145_raster_assets_product_dedup.sql
\echo '═══ 152. v146_backfill_runs_outcome_counters.sql ═══'
\i migrations/v146_backfill_runs_outcome_counters.sql
\echo '═══ 153. v147_backfill_runs_source_landsat_thermal.sql ═══'
\i migrations/v147_backfill_runs_source_landsat_thermal.sql
\echo '═══ 154. v148_field_evidence_snapshots.sql ═══'
\i migrations/v148_field_evidence_snapshots.sql
\echo '═══ 155. v149_evidence_graph_nodes_edges.sql ═══'
\i migrations/v149_evidence_graph_nodes_edges.sql
\echo '═══ 156. v150_seasons_yield_nonnegative_check.sql ═══'
\i migrations/v150_seasons_yield_nonnegative_check.sql
\echo '═══ 157. v151_learning_source_lineage.sql ═══'
\i migrations/v151_learning_source_lineage.sql
\echo '═══ 158. v152_deprecate_recommendation_feedback.sql ═══'
\i migrations/v152_deprecate_recommendation_feedback.sql
\echo '═══ 159. v153_crop_stress_memory_store.sql ═══'
\i migrations/v153_crop_stress_memory_store.sql
\echo '═══ 160. v154_raster_product_identity_batch_leases.sql ═══'
\i migrations/v154_raster_product_identity_batch_leases.sql
\echo '═══ 161. v155_soil_observations_profiles.sql ═══'
\i migrations/v155_soil_observations_profiles.sql
\echo '═══ 162. v156_durable_soil_lab_workflow.sql ═══'
\i migrations/v156_durable_soil_lab_workflow.sql
\echo '═══ 163. v157_soil_projection_jobs_reconciliation.sql ═══'
\i migrations/v157_soil_projection_jobs_reconciliation.sql
\echo '═══ 164. v158_soil_projection_observability.sql ═══'
\i migrations/v158_soil_projection_observability.sql
\echo '═══ 165. v159_soil_observation_supersession_current_pointer.sql ═══'
\i migrations/v159_soil_observation_supersession_current_pointer.sql
\echo '═══ 166. v160_soil_lab_publication_lineage.sql ═══'
\i migrations/v160_soil_lab_publication_lineage.sql
\echo '═══ 167. v161_soil_p1_products.sql ═══'
\i migrations/v161_soil_p1_products.sql
\echo '═══ 168. v162_soil_p2_spatial_products.sql ═══'
\i migrations/v162_soil_p2_spatial_products.sql
\echo '═══ 169. v163_soil_p3_assessment_products.sql ═══'
\i migrations/v163_soil_p3_assessment_products.sql
\echo '═══ 170. v164_soil_p4_closed_loop.sql ═══'
\i migrations/v164_soil_p4_closed_loop.sql
\echo '═══ 171. v165_soil_p5_validation_calibration_certification.sql ═══'
\i migrations/v165_soil_p5_validation_calibration_certification.sql
\echo '═══ 172. v166_soil_p6_runtime_certification.sql ═══'
\i migrations/v166_soil_p6_runtime_certification.sql
\echo '═══ 173. v167_mpc_content_digest_lineage.sql ═══'
\i migrations/v167_mpc_content_digest_lineage.sql
\echo '═══ 174. v168_irrigation_engineering_foundation.sql ═══'
\i migrations/v168_irrigation_engineering_foundation.sql
\echo '═══ 175. v169_canonical_root_zone_hydraulic_profile.sql ═══'
\i migrations/v169_canonical_root_zone_hydraulic_profile.sql
\echo '═══ 176. v170_water_source_well_digital_twin.sql ═══'
\i migrations/v170_water_source_well_digital_twin.sql
\echo '═══ 177. v171_pump_hydraulic_network_capability.sql ═══'
\i migrations/v171_pump_hydraulic_network_capability.sql
\echo '═══ 178. v172_irrigation_machine_capability.sql ═══'
\i migrations/v172_irrigation_machine_capability.sql
\echo '═══ 179. v173_sprinkler_runoff_capability.sql ═══'
\i migrations/v173_sprinkler_runoff_capability.sql
\echo '═══ 180. v174_energy_agricultural_microgrid_capability.sql ═══'
\i migrations/v174_energy_agricultural_microgrid_capability.sql
\echo '═══ 181. v175_unified_irrigation_capability_graph.sql ═══'
\i migrations/v175_unified_irrigation_capability_graph.sql
\echo '═══ 182. v176_controller_edge_adapter_framework.sql ═══'
\i migrations/v176_controller_edge_adapter_framework.sql
\echo '═══ 183. v177_irrigation_commissioning_certification.sql ═══'
\i migrations/v177_irrigation_commissioning_certification.sql
\echo '═══ 184. v178_canonical_as_applied_irrigation_truth.sql ═══'
\i migrations/v178_canonical_as_applied_irrigation_truth.sql
\echo '═══ 185. v179_hourly_energy_aware_irrigation_mpc.sql ═══'
\i migrations/v179_hourly_energy_aware_irrigation_mpc.sql
\echo '═══ 186. v180_governed_vri_prescription.sql ═══'
\i migrations/v180_governed_vri_prescription.sql
\echo '═══ 187. v181_irrigation_closed_loop_learning_production_certification.sql ═══'
\i migrations/v181_irrigation_closed_loop_learning_production_certification.sql
\echo '═══ 188. v182_decision_content_lineage_and_secret_hardening.sql ═══'
\i migrations/v182_decision_content_lineage_and_secret_hardening.sql
\echo '═══ 189. v183_decision_lineage_integrity_hardening.sql ═══'
\i migrations/v183_decision_lineage_integrity_hardening.sql
\echo '═══ 190. v184_irrigation_closed_loop_runtime_reconciliation.sql ═══'
\i migrations/v184_irrigation_closed_loop_runtime_reconciliation.sql
\echo '═══ 191. v185_vendor_neutral_irrigation_engineering_workspace.sql ═══'
\i migrations/v185_vendor_neutral_irrigation_engineering_workspace.sql
\echo '═══ 192. v186_irrx1_digital_commissioning_runtime.sql ═══'
\i migrations/v186_irrx1_digital_commissioning_runtime.sql
\echo '═══ 193. v187_irrx1_manual_execution_lifecycle.sql ═══'
\i migrations/v187_irrx1_manual_execution_lifecycle.sql
\echo '═══ 194. v188_irrx1_verified_manual_as_applied_ledger_bridge.sql ═══'
\i migrations/v188_irrx1_verified_manual_as_applied_ledger_bridge.sql
\echo '═══ 195. v189_irrx1_pcert_manual_execution_db_invariants.sql ═══'
\i migrations/v189_irrx1_pcert_manual_execution_db_invariants.sql
\echo '═══ 196. v190_irrx1_authoritative_recommendation_provenance_lock.sql ═══'
\i migrations/v190_irrx1_authoritative_recommendation_provenance_lock.sql
\echo '═══ 197. v191_rs_signal_anomalies_store.sql ═══'
\i migrations/v191_rs_signal_anomalies_store.sql

\echo '═══ 198. v192_fii_rls_write_fail_closed.sql ═══'
\i migrations/v192_fii_rls_write_fail_closed.sql
\echo '═══ 199. v193_prescriptions_season_context_expand.sql ═══'
\i migrations/v193_prescriptions_season_context_expand.sql
\echo '═══ 200. v194_fii_chemical_chain_rls_fail_closed.sql ═══'
\i migrations/v194_fii_chemical_chain_rls_fail_closed.sql
\echo '═══ 201. v195_irrigation_capacity_reservation_core.sql ═══'
\i migrations/v195_irrigation_capacity_reservation_core.sql
\echo '═══ 202. v196_irrigation_target_binding.sql ═══'
\i migrations/v196_irrigation_target_binding.sql
\echo '═══ 203. v197_external_submissions_ingest.sql ═══'
\i migrations/v197_external_submissions_ingest.sql
\echo '═══ 204. v198_external_ingest_sources.sql ═══'
\i migrations/v198_external_ingest_sources.sql
\echo '═══ 205. v199_external_field_observations.sql ═══'
\i migrations/v199_external_field_observations.sql
\echo '═══ 206. v200_admin_boundaries.sql ═══'
\i migrations/v200_admin_boundaries.sql
\echo '═══ 207. v201_season_records.sql ═══'
\i migrations/v201_season_records.sql
\echo '═══ 208. v202_season_draft_key.sql ═══'
\i migrations/v202_season_draft_key.sql
\echo '═══ 209. v203_season_sowing_in_observed_range.sql ═══'
\i migrations/v203_season_sowing_in_observed_range.sql
\echo '═══ 210. v204_field_forms.sql ═══'
\i migrations/v204_field_forms.sql

\echo '═══ 211. v205_irrigation_reservation_runtime_hardening.sql ═══'
\i migrations/v205_irrigation_reservation_runtime_hardening.sql
\echo '═══ 212. v207_historical_season_simulation_bridge.sql ═══'
\i migrations/v207_historical_season_simulation_bridge.sql
\echo '═══ 213. v208_seasons_sim_run_lineage.sql ═══'
\i migrations/v208_seasons_sim_run_lineage.sql
\echo '═══ 214. v209_historical_weather_sor.sql ═══'
\i migrations/v209_historical_weather_sor.sql
\echo '═══ 215. v210_erp_reconciliation_ledger.sql ═══'
\i migrations/v210_erp_reconciliation_ledger.sql
\echo '═══ 216. v211_simple_farm_book.sql ═══'
\i migrations/v211_simple_farm_book.sql
\echo '═══ 217. v212_farm_book_one_reversal_index.sql ═══'
\i migrations/v212_farm_book_one_reversal_index.sql
\echo '═══ 218. v206_rls_final_hardening.sql ═══'
\i migrations/v206_rls_final_hardening.sql
