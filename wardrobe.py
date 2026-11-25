"""Wardrobe catalog, design briefs, and outfit constraint checking.

An outfit is a dict slot -> item_id (or list of ids for "accessories").
Structure rules:
  - either (top AND bottom) OR onepiece
  - footwear required
  - outerwear, headwear optional (at most one each)
  - accessories: 0-2 items
"""

from __future__ import annotations

# id, slot, name, colors, formality(1-5), warmth(0-3), tags
_RAW = [
    # tops
    ("T01", "top", "white oxford button-down shirt", ["white"], 4, 1, ["classic", "crisp"]),
    ("T02", "top", "black turtleneck sweater", ["black"], 3, 2, ["minimal", "intellectual"]),
    ("T03", "top", "faded band t-shirt", ["grey"], 1, 0, ["casual", "music", "vintage"]),
    ("T04", "top", "chunky cable-knit fisherman sweater", ["beige"], 2, 3, ["cozy", "nautical", "rugged"]),
    ("T05", "top", "silk blouse with a pussy-bow", ["pink"], 4, 0, ["elegant", "retro"]),
    ("T06", "top", "hawaiian print camp shirt", ["multicolor"], 1, 0, ["playful", "beach", "loud"]),
    ("T07", "top", "sequined crop top", ["silver"], 2, 0, ["party", "shiny", "night"]),
    ("T08", "top", "linen tunic", ["green"], 2, 0, ["breezy", "earthy"]),
    ("T09", "top", "striped breton shirt", ["navy", "white"], 2, 1, ["nautical", "classic"]),
    ("T10", "top", "mesh long-sleeve top", ["black"], 1, 0, ["club", "edgy"]),
    ("T11", "top", "embroidered peasant blouse", ["white", "red"], 2, 0, ["folk", "handmade"]),
    ("T12", "top", "flannel work shirt", ["red", "black"], 1, 2, ["rugged", "outdoorsy"]),
    # bottoms
    ("B01", "bottom", "charcoal tailored trousers", ["grey"], 5, 1, ["classic", "sharp"]),
    ("B02", "bottom", "dark selvedge jeans", ["navy"], 2, 1, ["casual", "durable"]),
    ("B03", "bottom", "pleated midi skirt", ["yellow"], 3, 0, ["retro", "flowy"]),
    ("B04", "bottom", "cargo pants with many pockets", ["green"], 1, 1, ["utility", "rugged", "outdoorsy"]),
    ("B05", "bottom", "board shorts", ["orange"], 1, 0, ["beach", "playful"]),
    ("B06", "bottom", "velvet flared trousers", ["purple"], 3, 1, ["70s", "party", "plush"]),
    ("B07", "bottom", "leather mini skirt", ["black"], 2, 0, ["edgy", "night"]),
    ("B08", "bottom", "corduroy overalls (bottom half)", ["brown"], 1, 1, ["workwear", "whimsical"]),
    ("B09", "bottom", "white tennis skirt", ["white"], 2, 0, ["sporty", "preppy"]),
    ("B10", "bottom", "thermal-lined hiking pants", ["grey"], 1, 3, ["outdoorsy", "technical", "rugged"]),
    # one-pieces
    ("O01", "onepiece", "black floor-length evening gown", ["black"], 5, 1, ["glamorous", "elegant"]),
    ("O02", "onepiece", "navy three-piece suit", ["navy"], 5, 2, ["classic", "sharp", "formal"]),
    ("O03", "onepiece", "orange mechanic's coverall", ["orange"], 1, 2, ["workwear", "utility"]),
    ("O04", "onepiece", "floral sundress", ["yellow", "green"], 2, 0, ["summer", "garden", "breezy"]),
    ("O05", "onepiece", "metallic silver jumpsuit", ["silver"], 3, 1, ["futuristic", "shiny", "party"]),
    ("O06", "onepiece", "moss-green velvet slip dress", ["green"], 4, 0, ["romantic", "earthy", "plush"]),
    ("O07", "onepiece", "full-body dinosaur onesie", ["green"], 1, 2, ["whimsical", "costume", "cozy"]),
    # outerwear
    ("W01", "outerwear", "camel wool overcoat", ["beige"], 4, 3, ["classic", "warm"]),
    ("W02", "outerwear", "yellow fisherman's raincoat", ["yellow"], 1, 2, ["nautical", "waterproof", "rugged"]),
    ("W03", "outerwear", "black leather biker jacket", ["black"], 2, 2, ["edgy", "music"]),
    ("W04", "outerwear", "faux-fur coat", ["pink"], 3, 3, ["glamorous", "plush", "loud"]),
    ("W05", "outerwear", "denim jacket covered in patches", ["blue", "multicolor"], 1, 1, ["casual", "music", "handmade"]),
    ("W06", "outerwear", "down puffer parka", ["red"], 1, 3, ["technical", "warm", "outdoorsy"]),
    ("W07", "outerwear", "velvet smoking jacket", ["red"], 4, 2, ["elegant", "plush", "eccentric"]),
    ("W08", "outerwear", "hand-knit patchwork cardigan", ["multicolor"], 2, 2, ["handmade", "cozy", "whimsical"]),
    ("W09", "outerwear", "reflective safety vest", ["orange"], 1, 0, ["utility", "workwear"]),
    # footwear
    ("F01", "footwear", "polished black oxford shoes", ["black"], 5, 1, ["classic", "formal"]),
    ("F02", "footwear", "white canvas sneakers", ["white"], 1, 0, ["casual", "sporty"]),
    ("F03", "footwear", "rubber wellington boots", ["green"], 1, 2, ["rugged", "waterproof", "outdoorsy"]),
    ("F04", "footwear", "gold strappy heels", ["gold"], 4, 0, ["glamorous", "party"]),
    ("F05", "footwear", "leather hiking boots", ["brown"], 1, 2, ["rugged", "outdoorsy", "technical"]),
    ("F06", "footwear", "platform moon boots", ["silver"], 2, 3, ["futuristic", "loud", "warm"]),
    ("F07", "footwear", "flip-flops", ["blue"], 1, 0, ["beach", "casual"]),
    ("F08", "footwear", "embroidered velvet slippers", ["purple"], 3, 1, ["eccentric", "plush", "cozy"]),
    ("F09", "footwear", "brown chelsea boots", ["brown"], 3, 1, ["classic", "versatile"]),
    # headwear
    ("H01", "headwear", "black wide-brim fedora", ["black"], 3, 0, ["classic", "mysterious"]),
    ("H02", "headwear", "knitted beanie with pom-pom", ["red"], 1, 2, ["cozy", "winter"]),
    ("H03", "headwear", "straw sun hat", ["beige"], 2, 0, ["beach", "garden", "summer"]),
    ("H04", "headwear", "over-ear headphones (worn as headpiece)", ["black"], 1, 1, ["music", "tech"]),
    ("H05", "headwear", "fascinator with feathers", ["purple"], 4, 0, ["glamorous", "eccentric"]),
    ("H06", "headwear", "captain's cap", ["navy", "white"], 2, 0, ["nautical", "costume"]),
    ("H07", "headwear", "hard hat", ["yellow"], 1, 0, ["utility", "workwear"]),
    # accessories
    ("A01", "accessory", "silk necktie", ["navy"], 4, 0, ["classic", "formal"]),
    ("A02", "accessory", "pearl necklace", ["white"], 4, 0, ["elegant", "classic"]),
    ("A03", "accessory", "chunky gold chain", ["gold"], 2, 0, ["loud", "music"]),
    ("A04", "accessory", "pocket watch on a chain", ["silver"], 3, 0, ["vintage", "eccentric"]),
    ("A05", "accessory", "wool tartan scarf", ["red", "green"], 2, 2, ["cozy", "winter", "classic"]),
    ("A06", "accessory", "round sunglasses", ["black"], 2, 0, ["cool", "mysterious"]),
    ("A07", "accessory", "canvas tote bag of paintbrushes", ["beige"], 1, 0, ["artsy", "handmade"]),
    ("A08", "accessory", "brass compass pendant", ["gold"], 2, 0, ["nautical", "vintage"]),
    ("A09", "accessory", "LED light-up wristbands", ["multicolor"], 1, 0, ["party", "tech", "club"]),
    ("A10", "accessory", "dried-flower corsage", ["pink", "brown"], 3, 0, ["romantic", "garden", "handmade"]),
    ("A11", "accessory", "leather work gloves", ["brown"], 1, 1, ["utility", "rugged"]),
    ("A12", "accessory", "a single large mushroom-shaped brooch", ["red", "white"], 2, 0, ["whimsical", "garden"]),
]

ITEMS = {
    r[0]: {"id": r[0], "slot": r[1], "name": r[2], "colors": r[3],
           "formality": r[4], "warmth": r[5], "tags": r[6]}
    for r in _RAW
}

SLOTS = ["headwear", "top", "bottom", "onepiece", "outerwear", "footwear", "accessory"]


def wardrobe_text() -> str:
    lines = []
    for slot in SLOTS:
        lines.append(f"## {slot}")
        for it in ITEMS.values():
            if it["slot"] == slot:
                lines.append(
                    f"- {it['id']}: {it['name']} | colors: {', '.join(it['colors'])} | "
                    f"formality {it['formality']}/5 | warmth {it['warmth']}/3 | {', '.join(it['tags'])}"
                )
    return "\n".join(lines)


# ---------------------------------------------------------------- briefs
# kind: conventional | constrained | open
BRIEFS = [
    {"id": "interview", "kind": "conventional",
     "text": "A job interview at a traditional law firm.",
     "constraints": {"min_avg_formality": 4.0}},
    {"id": "winter_wedding", "kind": "conventional",
     "text": "Attending an outdoor winter wedding where it is -5°C.",
     "constraints": {"min_total_warmth": 6, "min_avg_formality": 3.0}},
    {"id": "art_teacher", "kind": "conventional",
     "text": "Your first day as a kindergarten art teacher.",
     "constraints": {"max_item_formality": 4}},
    {"id": "mud_to_gallery", "kind": "constrained",
     "text": "Hiking a muddy trail, then going straight to a gallery opening with no time to change.",
     "constraints": {"footwear_tag": "rugged"}},
    {"id": "robot_funeral", "kind": "constrained",
     "text": "The funeral of a beloved household robot. You may not wear anything black.",
     "constraints": {"forbid_color": "black"}},
    {"id": "beach_tie", "kind": "constrained",
     "text": "A day at the beach, but the dress code says you must wear a necktie.",
     "constraints": {"require_item": "A01"}},
    {"id": "two_colors", "kind": "constrained",
     "text": "An outfit for a dinner party that uses at most two distinct colors but is still not boring.",
     "constraints": {"max_distinct_colors": 2}},
    {"id": "sunday_evening", "kind": "open",
     "text": "Dress as the feeling of a Sunday evening.",
     "constraints": {}},
    {"id": "lighthouse_dj", "kind": "open",
     "text": "A lighthouse keeper who is secretly a famous DJ, on the night of their big gig.",
     "constraints": {}},
    {"id": "mushroom_party", "kind": "open",
     "text": "A garden party thrown by sentient mushrooms.",
     "constraints": {}},
    {"id": "grandmother_job", "kind": "open",
     "text": "An outfit that tells the story of your grandmother's first job.",
     "constraints": {}},
    {"id": "time_traveler", "kind": "open",
     "text": "A time traveler arriving in the year 2126 who desperately wants to blend in.",
     "constraints": {}},
]
BRIEFS_BY_ID = {b["id"]: b for b in BRIEFS}


# ---------------------------------------------------------------- outfit utils
def outfit_ids(outfit: dict) -> list[str]:
    ids = []
    for slot, v in outfit.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            ids.extend(str(x).strip().upper() for x in v if x)
        else:
            ids.append(str(v).strip().upper())
    return ids


import re as _re

_ID_IN_TEXT = _re.compile(r"\b([TBOWFHA]\d{2})\b", _re.I)
_NAME_TO_ID = {it["name"].lower(): it["id"] for it in ITEMS.values()}


def resolve_id(value: str) -> tuple[str, bool]:
    """Map a model's item reference to an ID. Returns (id, repaired?).
    Accepts a bare ID, text containing an ID ("biker jacket (W03)"), or an exact item name."""
    s = str(value).strip()
    if s.upper() in ITEMS:
        return s.upper(), False
    m = _ID_IN_TEXT.search(s)
    if m and m.group(1).upper() in ITEMS:
        return m.group(1).upper(), True
    key = _re.sub(r"\s*\(.*?\)\s*$", "", s).strip().lower()
    if key in _NAME_TO_ID:
        return _NAME_TO_ID[key], True
    return s.upper(), False


def repair_outfit(outfit: dict) -> tuple[dict, bool]:
    fixed, repaired = {}, False
    for slot, v in outfit.items():
        if isinstance(v, list):
            ids = [resolve_id(x) for x in v]
            fixed[slot] = [i for i, _ in ids]
            repaired |= any(r for _, r in ids)
        else:
            i, r = resolve_id(v)
            fixed[slot] = i
            repaired |= r
    return fixed, repaired


def normalize_outfit(raw) -> dict | None:
    """Coerce a model's outfit object into {slot: id | [ids]}; None if hopeless."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, v in raw.items():
        key = str(k).strip().lower().rstrip("s")  # accessories -> accessorie? handle below
        if key.startswith("accessor"):
            key = "accessory"
        if key == "shoe" or key == "shoes":
            key = "footwear"
        if key in ("hat", "head"):
            key = "headwear"
        if key in ("dres", "one_piece", "one-piece"):
            key = "onepiece"
        if key == "outerwear" or key == "coat" or key == "jacket":
            key = "outerwear"
        if v is None or v == "" or (isinstance(v, str) and v.strip().lower() in ("none", "null", "-")):
            continue
        if key == "accessory":
            vals = v if isinstance(v, list) else [v]
            vals = [str(x).strip().upper() for x in vals if x and str(x).strip().lower() not in ("none", "null")]
            if vals:
                out["accessory"] = vals
        else:
            if isinstance(v, list):
                v = v[0] if v else None
                if v is None:
                    continue
            out[key] = str(v).strip().upper()
    return out


def check_structure(outfit: dict) -> list[str]:
    """Return a list of structural errors (empty = valid)."""
    errs = []
    ids = outfit_ids(outfit)
    for i in ids:
        if i not in ITEMS:
            errs.append(f"unknown item {i}")
    if errs:
        return errs
    for slot, v in outfit.items():
        vals = v if isinstance(v, list) else [v]
        for i in vals:
            if ITEMS[i]["slot"] != slot:
                errs.append(f"{i} is a {ITEMS[i]['slot']}, placed in {slot}")
    if len(ids) != len(set(ids)):
        errs.append("duplicate item")
    has_top, has_bottom, has_one = "top" in outfit, "bottom" in outfit, "onepiece" in outfit
    if has_one and (has_top or has_bottom):
        errs.append("onepiece combined with top/bottom")
    if not has_one and not (has_top and has_bottom):
        errs.append("needs top+bottom or onepiece")
    if "footwear" not in outfit:
        errs.append("missing footwear")
    if len(outfit.get("accessory", [])) > 2:
        errs.append("more than 2 accessories")
    unknown_slots = set(outfit) - set(SLOTS)
    if unknown_slots:
        errs.append(f"unknown slots {sorted(unknown_slots)}")
    return errs


def check_constraints(outfit: dict, brief: dict) -> list[str]:
    errs = []
    items = [ITEMS[i] for i in outfit_ids(outfit) if i in ITEMS]
    c = brief["constraints"]
    if not items:
        return ["empty"]
    # formality averaged over clothing (accessories excluded)
    clothing = [it for it in items if it["slot"] != "accessory"]
    if "min_avg_formality" in c:
        avg = sum(it["formality"] for it in clothing) / max(1, len(clothing))
        if avg < c["min_avg_formality"]:
            errs.append(f"avg formality {avg:.2f} < {c['min_avg_formality']}")
    if "min_total_warmth" in c:
        w = sum(it["warmth"] for it in items)
        if w < c["min_total_warmth"]:
            errs.append(f"warmth {w} < {c['min_total_warmth']}")
    if "max_item_formality" in c:
        if any(it["formality"] > c["max_item_formality"] for it in items):
            errs.append("an item is too formal")
    if "footwear_tag" in c:
        fw = ITEMS.get(outfit.get("footwear", ""), None)
        if not fw or c["footwear_tag"] not in fw["tags"]:
            errs.append(f"footwear not {c['footwear_tag']}")
    if "forbid_color" in c:
        if any(c["forbid_color"] in it["colors"] for it in items):
            errs.append(f"contains {c['forbid_color']}")
    if "require_item" in c:
        if c["require_item"] not in outfit_ids(outfit):
            errs.append(f"missing required {c['require_item']}")
    if "max_distinct_colors" in c:
        cols = {col for it in items for col in it["colors"]}
        if len(cols) > c["max_distinct_colors"]:
            errs.append(f"{len(cols)} colors > {c['max_distinct_colors']}")
    return errs


def outfit_description(outfit: dict) -> str:
    return "; ".join(ITEMS[i]["name"] for i in outfit_ids(outfit) if i in ITEMS)
