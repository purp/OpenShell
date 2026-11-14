#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Constrain classifier responses and validate them before live preview."""

from label_issue_policy import IDENTITY, validate_result

CONFIDENCE = ["high", "medium", "low"]


def object_schema(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def array_schema(items):
    return {"type": "array", "items": items}


def response_schema(bundle):
    text = {"type": "string"}
    strings = array_schema(text)
    confidence = {"type": "string", "enum": CONFIDENCE}
    choice = object_schema({"labels": strings, "confidence": confidence})
    reason = object_schema({"labels": strings, "evidence": strings, "reason": text})
    ambiguity = object_schema(
        {"boundary": text, "chosen": choice, "alternative": choice, "evidence": strings}
    )
    packet = bundle.get("packet")
    classification = {"type": "null"}
    if packet and bundle["preparation"]["status"] == "ready":
        properties = {key: {"enum": [packet[key]]} for key in IDENTITY}
        properties.update(
            {
                "area": {"type": "string", "enum": list(packet["scopes"]["areas"])},
                "topics": array_schema(
                    {"type": "string", "enum": list(packet["scopes"]["topics"])}
                ),
                "reasons": array_schema(reason),
                "ambiguity": {"anyOf": [{"type": "null"}, ambiguity]},
                "removals": array_schema(
                    object_schema({"label": text, "evidence": strings, "reason": text})
                ),
            }
        )
        classification = {"anyOf": [{"type": "null"}, object_schema(properties)]}
    return object_schema(
        {
            "outcome": {
                "type": "string",
                "enum": ["classified", "skipped", "held", "error"],
            },
            "classification": classification,
            "confidence": {"type": "string", "enum": [*CONFIDENCE, "not_applicable"]},
            "label_confidence": array_schema(
                object_schema({"label": text, "confidence": confidence, "reason": text})
            ),
            "summary": text,
            "missing_context": strings,
        }
    )


def schema_errors(value, schema, path="$"):
    """Validate the small schema vocabulary constructed above, without dependencies."""
    if "anyOf" in schema:
        branches = [
            (option, schema_errors(value, option, path)) for option in schema["anyOf"]
        ]
        if any(not errors for _, errors in branches):
            return []
        kind = (
            "object" if isinstance(value, dict) else "null" if value is None else None
        )
        return next(
            (errors for option, errors in branches if option.get("type") == kind),
            [f"{path}: no permitted shape matches"],
        )
    if "enum" in schema and not any(
        type(value) is type(option) and value == option for option in schema["enum"]
    ):
        return [f"{path}: value is outside the permitted enum"]
    kind = schema.get("type")
    expected = {"object": dict, "array": list, "string": str, "null": type(None)}
    if kind and not isinstance(value, expected[kind]):
        return [f"{path}: expected {kind}"]
    errors = []
    if kind == "object":
        errors += [
            f"{path}: missing field {key}"
            for key in schema["required"]
            if key not in value
        ]
        errors += [
            f"{path}: unexpected field {key}"
            for key in value
            if key not in schema["properties"]
        ]
        for key in value.keys() & schema["properties"].keys():
            errors += schema_errors(
                value[key], schema["properties"][key], f"{path}.{key}"
            )
    if kind == "array":
        for index, entry in enumerate(value):
            errors += schema_errors(entry, schema["items"], f"{path}[{index}]")
    return errors


def validate_answer(answer, bundle, snapshot):
    errors = schema_errors(answer, response_schema(bundle))
    if errors:
        return {"valid": False, "errors": errors, "missing_prerequisites": []}
    ready = bundle["preparation"]["status"] == "ready"
    result = answer["classification"]
    if not ready:
        if result is not None or answer["outcome"] == "classified":
            errors.append("Preparation gate prohibits classification")
        elif answer["outcome"] != bundle["preparation"]["status"]:
            errors.append("Outcome must preserve the preparation gate")
    elif answer["outcome"] == "classified":
        if result is None:
            errors.append("Classified outcome requires a classification")
        else:
            validation = validate_result(snapshot, result)
            errors += validation["errors"]
            return {**validation, "valid": not errors, "errors": errors}
    elif result is not None:
        errors.append("A non-classified outcome must not contain a classification")
    elif answer["outcome"] == "skipped":
        errors.append(
            "Ready preparation cannot be silently skipped; report a contextual hold instead"
        )
    return {"valid": not errors, "errors": errors, "missing_prerequisites": []}
