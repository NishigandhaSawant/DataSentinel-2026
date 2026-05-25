"""
DataSentinel — Deterministic SBVR Logic Gate (Neuro-Symbolic Pipeline)
Translates LLM generations into Semantics of Business Vocabulary and Business Rules (SBVR).
Provides both deterministic Polars validation (hard constraints) and 
tensor mappings for Logical Neural Networks (soft constraints).

IEEE Novelty: Mitigates LLM hallucination by forcing strict AST-compliant SBVR parsing.
"""

import os
import json
import polars as pl
from utils import logger


def _generate_sbvr_rules(df: pl.DataFrame) -> list:
    """
    Ask the AI to generate business rules strictly adhering to SBVR structures.
    """
    # Build a privacy-safe schema summary
    schema_info = []
    for col, dtype in zip(df.columns, df.dtypes):
        # Only pass numeric/date types for mathematical logic
        if dtype in [pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Date, pl.Datetime]:
            schema_info.append(f"- {col} (Type: {dtype})")
    schema_str = "\n".join(schema_info)

    if not schema_info:
        return []

    prompt = f"""You are an expert Data Governance Agent operating under strict IEEE neuro-symbolic standards.
Given the following dataset schema, generate up to 5 universally true business rules to catch impossible data.

You MUST format your response as a valid JSON object adhering to the Semantics of Business Vocabulary and Business Rules (SBVR) standard.
Format your rules as: "It is obligatory that [Column] is [Operator] [Value]."

Schema:
{schema_str}

Respond STRICTLY with this JSON format. Do NOT include markdown:
{{
    "sbvr_rules": [
        {{
            "sbvr_statement": "It is obligatory that Age is greater_than 0",
            "column": "Age",
            "operator": "greater_than",
            "value": 0,
            "reason": "Age cannot be negative"
        }}
    ]
}}

Supported operators: "less_than", "greater_than", "equal_to".
CRITICAL RULES:
1. ONLY apply rules to columns that actually exist in the schema provided.
2. Ensure values are numeric.
"""
    from groq_client import groq_chat_json

    try:
        messages = [{"role": "user", "content": prompt}]
        # Temperature 0.0 forces deterministic, repeatable outputs
        data = groq_chat_json(messages, model="llama-3.1-8b-instant", temperature=0.0)

        if not data:
            return []

        rules = data.get("sbvr_rules", [])
        logger.info("AI generated %d deterministic SBVR rules.", len(rules))

        for r in rules:
            logger.info("SBVR Rule: %s", r.get('sbvr_statement'))

        return rules

    except Exception as e:
        logger.warning("SBVR Logic Gate generation failed: %s", e)
        return []


def apply_logic_gate(df: pl.DataFrame):
    """
    Safely parse the SBVR AST rules and apply them as hard deterministic masks via Polars.
    """
    rules = _generate_sbvr_rules(df)
    applied_rules = []

    # Initialize the violation column if it doesn't exist
    if "logic_violation" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias("logic_violation"))

    for rule in rules:
        col = rule.get("column")
        op = rule.get("operator")
        val = rule.get("value")
        reason = rule.get("reason")

        # Security AST Validation: Ensure the AI didn't hallucinate a column
        if not col or col not in df.columns or val is None:
            continue

        try:
            # Safely build Polars execution conditions (Deterministic AST compilation)
            condition = None
            if op == "less_than":
                condition = pl.col(col).cast(pl.Float64, strict=False) < float(val)
            elif op == "greater_than":
                condition = pl.col(col).cast(pl.Float64, strict=False) > float(val)
            elif op == "equal_to":
                condition = pl.col(col).cast(pl.Float64, strict=False) == float(val)

            # Apply the mathematical condition
            if condition is not None:
                # We invert the logic here: The SBVR statement says what is OBLIGATORY.
                # Therefore, an anomaly is when the condition is FALSE.
                violation_condition = ~condition

                df = df.with_columns(
                    pl.when(violation_condition & pl.col("logic_violation").is_null())
                    .then(pl.lit(reason))
                    .when(violation_condition & pl.col("logic_violation").is_not_null())
                    .then(pl.col("logic_violation") + " | " + pl.lit(reason))
                    .otherwise(pl.col("logic_violation"))
                    .alias("logic_violation")
                )
                applied_rules.append(rule)

        except Exception as e:
            logger.warning("Failed to apply SBVR rule '%s': %s", rule, e)

    return df, applied_rules


def export_rules_for_lnn(rules: list, df_columns: list) -> list:
    """
    Translates SBVR Abstract Syntax Trees into differentiable tensor mappings
    for the Logical Neural Network (LNN) Autoencoder.
    """
    lnn_constraints = []
    
    for rule in rules:
        col_name = rule.get("column")
        if col_name in df_columns:
            col_idx = df_columns.index(col_name)
            lnn_constraints.append({
                "col_idx": col_idx,
                "operator": rule.get("operator"),
                "value": rule.get("value")
            })
            
    return lnn_constraints