"""Turn an OpenStreetMap extract of Britain and Ireland into small map tiles
of drinking-water and bottle-refill points for the website.

The "Update water data" GitHub Action downloads the extract from Geofabrik,
filters it with osmium, and runs this on the result (one GeoJSON feature per line):

    python scripts/update_data.py water.geojsonseq
"""
import json, math, os, sys, time

TILE = 0.25  # tile size in degrees (about 28 x 17 km in the UK)
KEEP = ["name", "amenity", "shop", "man_made", "bottle", "fee", "indoor", "seasonal",
        "opening_hours", "drinking_water", "drinking_water:refill", "access",
        "operational_status", "disused:amenity"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def wanted(t):
    if t.get("amenity") in ("drinking_water", "water_point"):
        return True
    if t.get("drinking_water") == "yes" or t.get("drinking_water:refill") == "yes":
        return True
    return False


def centre(geom):
    """Rough centre of any GeoJSON geometry (average of its coordinates)."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for part in c:
                walk(part)
    walk(geom["coordinates"])
    return sum(ys) / len(ys), sum(xs) / len(xs)


def main(path):
    points = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            f = json.loads(line)
            props = f.get("properties") or {}
            tags = {k: v for k, v in props.items() if not k.startswith("@")}
            if not wanted(tags) or not f.get("geometry"):
                continue
            lat, lon = centre(f["geometry"])
            typ = props.get("@type", "node")
            oid = props.get("@id", 0)
            points[f"{typ}/{oid}"] = {
                "type": typ, "id": oid, "lat": round(lat, 6), "lon": round(lon, 6),
                "tags": {k: v for k, v in tags.items() if k in KEEP}}

    if len(points) < 1000:
        print(f"Only {len(points)} points found; something went wrong, keeping old data.")
        sys.exit(1)

    tiles = {}
    for p in points.values():
        key = f"{math.floor(p['lat'] / TILE)}_{math.floor(p['lon'] / TILE)}"
        tiles.setdefault(key, []).append(p)

    tdir = os.path.join(OUT, "tiles")
    os.makedirs(tdir, exist_ok=True)
    for f in os.listdir(tdir):
        os.remove(os.path.join(tdir, f))
    for key, els in tiles.items():
        els.sort(key=lambda e: (e["type"], e["id"]))
        with open(os.path.join(tdir, key + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"elements": els}, fh, separators=(",", ":"), ensure_ascii=False)
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump({"updated": time.strftime("%Y-%m-%d"), "tile": TILE, "count": len(points),
                   "tiles": sorted(tiles)}, fh, separators=(",", ":"))
    print(f"Saved {len(points)} points in {len(tiles)} tiles.")


if __name__ == "__main__":
    main(sys.argv[1])
