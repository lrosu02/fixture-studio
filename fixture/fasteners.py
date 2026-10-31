"""Pinned ISO 273 metric clearance sizes; explicit overrides always take priority."""

import re
from .contracts import FastenerClearance
from .intake import selected_interface

STANDARD = "ISO 273"
SOURCE = "https://www.albanycountyfasteners.com/media/6b/b8/g0/1764944339/clearance-hole-chart.pdf?ts=1764944339"
VERIFIED = "2026-10-30"
# Nominal, fine, medium, coarse diameters (mm). Published metric table, page 2.
SIZES = {
    1.6: (1.7, 1.8, 2.0),
    2: (2.2, 2.4, 2.6),
    2.5: (2.7, 2.9, 3.1),
    3: (3.2, 3.4, 3.6),
    4: (4.3, 4.5, 4.8),
    5: (5.3, 5.5, 5.8),
    6: (6.4, 6.6, 7.0),
    8: (8.4, 9.0, 10.0),
    10: (10.5, 11.0, 12.0),
    12: (13.0, 13.5, 14.5),
    14: (15.0, 15.5, 16.5),
    16: (17.0, 17.5, 18.5),
    20: (21.0, 22.0, 24.0),
    24: (25.0, 26.0, 28.0),
    30: (31.0, 33.0, 35.0),
}
FITS = ("fine", "medium", "coarse")
# ACF inch series, page 1: nominal major diameter, close/normal/loose holes.
# Supplier reference chart, not a claim that these rows are certified by ISO 273.
INCH_SIZES = {
    "#0": (0.060, 0.0635, 0.0700, 0.0810),
    "#1": (0.073, 0.0760, 0.0810, 0.0890),
    "#2": (0.086, 0.0890, 0.0960, 0.1040),
    "#3": (0.099, 0.1015, 0.1065, 0.1160),
    "#4": (0.112, 0.1160, 0.1285, 0.1440),
    "#5": (0.125, 0.1285, 0.1360, 0.1540),
    "#6": (0.138, 0.1440, 0.1495, 0.1695),
    "#8": (0.164, 0.1695, 0.1800, 0.1935),
    "#10": (0.190, 0.1960, 0.2055, 0.2210),
    "#12": (0.216, 0.2210, 0.2344, 0.2500),
}


def fastener_size(text):
    match = re.fullmatch(r"\s*(#\d+)(?:-\d+)?\s*", text or "")
    if match and match[1] in INCH_SIZES:
        return match[1]
    return nominal_size(text)


def major_diameter(nominal):
    return INCH_SIZES[nominal][0] * 25.4 if isinstance(nominal, str) else nominal


def nominal_label(nominal):
    return nominal if isinstance(nominal, str) else f"M{nominal:g}"


def standard_size(nominal, fit):
    if isinstance(nominal, str):
        return round(
            INCH_SIZES[nominal][1 + FITS.index(fit)] * 25.4, 6
        ), "ACF inch-series chart"
    return SIZES[nominal][FITS.index(fit)], STANDARD


def proposed_screw_sizes(measured):
    metric = [n for n in SIZES if n <= measured + 0.05]
    inch = [n for n in INCH_SIZES if major_diameter(n) <= measured + 0.05]
    return ([nominal_label(max(metric))] if metric else []) + (
        [max(inch, key=major_diameter)] if inch else []
    )


def nominal_size(text):
    if not text or text.strip().lower() in ("unknown", "not specified"):
        return None
    match = re.fullmatch(
        r"\s*[mM]\s*(\d+(?:\.\d+)?)(?:\s*[x×]\s*\d+(?:\.\d+)?)?\s*", text
    )
    if not match or float(match[1]) not in SIZES:
        raise ValueError(
            "Fastener is outside the built-in ISO 273 metric table (M1.6–M30 listed sizes). Use a supported metric size or a custom clearance override."
        )
    return float(match[1])


def resolve_clearances(analysis, requirements):
    r = requirements
    interface = selected_interface(analysis, r)
    result = []
    assumed_sizes = []
    chosen = {}
    for choice in r.hole_fasteners:
        for hid in choice.hole_ids:
            if hid not in interface.hole_ids or hid in chosen:
                raise ValueError(
                    "Screw-size choices must reference unique selected mounting holes."
                )
            chosen[hid] = choice
    for feature, measured in zip(interface.hole_ids, interface.diameters):
        choice = chosen.get(feature)
        nominal_text = choice.nominal if choice else r.nominal_fastener
        override = (
            choice.clearance_diameter
            if choice and choice.clearance_diameter is not None
            else r.clearance_diameter
        )
        if override is not None:
            result.append(
                FastenerClearance(
                    feature_id=feature,
                    diameter=override,
                    nominal=nominal_text,
                    basis="Explicit clearance override",
                    origin="user",
                )
            )
            continue
        nominal = fastener_size(nominal_text)
        supplied = nominal is not None
        if nominal is None:
            candidates = [n for n in SIZES if n <= measured + 0.05]
            if not candidates:
                raise ValueError(
                    f"Measured hole {feature} is below the supported metric range; a custom clearance is needed."
                )
            nominal = max(candidates)
        assumed_sizes.append(nominal)
        diameter, standard = standard_size(nominal, r.clearance_fit)
        result.append(
            FastenerClearance(
                feature_id=feature,
                diameter=diameter,
                nominal=nominal_label(nominal),
                fit=r.clearance_fit,
                standard=standard,
                source_url=SOURCE,
                source_verified=VERIFIED,
                origin="derived",
                basis="User-specified nominal fastener"
                if supplied
                else "Assumed metric nominal from measured opening; thread and engagement are not identified",
            )
        )
    if r.surroundings == "bolt":
        if r.bench_hole_diameter is not None:
            result.append(
                FastenerClearance(
                    feature_id="base",
                    diameter=r.bench_hole_diameter,
                    nominal=r.bench_fastener,
                    basis="Explicit base clearance override",
                    origin="user",
                )
            )
        else:
            nominal = fastener_size(r.bench_fastener or r.nominal_fastener)
            supplied = nominal is not None
            if nominal is None:
                if r.base_mount:
                    from .intake import get_interface

                    base_face = get_interface(
                        r.base_mount.analysis, r.base_mount.interface_id
                    )
                    measured = min(
                        base_face.diameters[base_face.hole_ids.index(h)]
                        for h in r.base_mount.hole_ids
                    )
                    candidates = [n for n in SIZES if n <= measured + 0.05]
                    if not candidates:
                        raise ValueError(
                            "Selected base holes need an explicit custom fastener clearance."
                        )
                    nominal = max(candidates)
                elif not assumed_sizes:
                    if not interface.diameters:
                        raise ValueError(
                            "Specify the base screw size for this hole-free fixture; no part fastener size can be inferred."
                        )
                    candidates = [
                        n for n in SIZES if n <= min(interface.diameters) + 0.05
                    ]
                    if not candidates:
                        raise ValueError(
                            "Base fastener cannot be chosen from the supported metric range."
                        )
                    nominal = max(candidates)
                else:
                    nominal = min(assumed_sizes, key=major_diameter)
            diameter, standard = standard_size(nominal, r.clearance_fit)
            result.append(
                FastenerClearance(
                    feature_id="base",
                    diameter=diameter,
                    nominal=nominal_label(nominal),
                    fit=r.clearance_fit,
                    standard=standard,
                    source_url=SOURCE,
                    source_verified=VERIFIED,
                    origin="derived",
                    basis="Specified base/mounting nominal"
                    if supplied
                    else "Assumed metric nominal from selected measured base openings; threads are not identified"
                    if r.base_mount
                    else "Assumed base fastener from the smallest selected mounting size",
                )
            )
    return tuple(result)


def clearance_summary(records):
    groups = {}
    for record in records:
        label = "Base" if record.feature_id == "base" else "Mounting"
        choice = f"{record.nominal or 'custom'} → Ø{record.diameter:g} mm"
        policy = (
            f"{record.standard} {record.fit}" if record.standard else "custom override"
        )
        groups[(label, choice, policy)] = True
    return " · ".join(
        f"{label}: {choice} ({policy})" for label, choice, policy in groups
    )
