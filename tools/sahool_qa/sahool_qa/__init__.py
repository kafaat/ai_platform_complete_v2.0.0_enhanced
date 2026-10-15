"""SAHOOL Arabic QA generator.

Deterministic, rule-based Arabic question/answer generation over the SAHOOL
PostGIS schema (field_boundaries / soil_readings / field_indicators).
Every answer is computed from stored data, never written by a model.
"""

__version__ = "0.4.2"
GENERATOR_ID = f"sahool-qa/{__version__}"
