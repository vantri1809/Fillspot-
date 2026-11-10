"""Download UK drinking-water and refill points from OpenStreetMap (Overpass API)
and save them as small map tiles the website loads directly.

Run by the "Update water data" GitHub Action every week.
"""
import json, math, os, sys, time, urllib.parse, urllib.request

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "Fillspot/1.0 (+https://github.com/vantri1809/Fillspot-)"
# UK and Ireland, split into 2x2 degree boxes so each request stays small
SOUTH, NORTH, WEST, EAST = 49.8, 61.0, -11.0, 2.0
STEP = 2.0
TILE = 0.25  # website tile size in degrees
KEEP = ["name", "amenity", "shop", "man_made", "bottle", "fee", "indoor", "seasonal",
        "opening_hours", "drinking_water", "drinking_water:refill", "access",
        "operational_status", "disused:amenity"]
OUT = os.path.join(os.path.dirname(__file__), "..", "data")


def query(bbox):
    b = "%.4f,%.4f,%.4f,%.4f" % bbox
    return ("[out:json][timeout:180];("
            f'nwr["amenity"="drinking_water"]({b});'
            f'nwr["amenity"="water_point"]({b});'
            f'nwr["man_made"="water_tap"]["drinking_water"="yes"]({b});'
            f'nwr["drinking_water"="yes"]({b});'
            f'nwr["drinking_water:refill"="yes"]({b});'
            ");out center tags;")


def fetch(q):
    last = None
    for attempt in range(6):
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  {url} failed: {e}; retrying", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"all mirrors failed: {last}")


def main():
    points = {}
    boxes = []
    lat = SOUTH
    while lat < NORTH:
        lng = WEST
        while lng < EAST:
            boxes.append((lat, lng, min(lat + STEP, NORTH), min(lng + STEP, EAST)))
            lng += STEP
        lat += STEP
    failed = 0
    for i, bbox in enumerate(boxes, 1):
        print(f"[{i}/{len(boxes)}] {bbox}", flush=True)
        try:
            data = fetch(query(bbox))
        except RuntimeError as e:
            print(f"  giving up on this box: {e}", flush=True)
            failed += 1
            continue
        for el in data.get("elements", []):
            la = el.get("lat", (el.get("center") or {}).get("lat"))
            lo = el.get("lon", (el.get("center") or {}).get("lon"))
            if la is None or lo is None:
                continue
            tags = {k: v for k, v in (el.get("tags") or {}).items() if k in KEEP}
            points[f'{el["type"]}/{el["id"]}'] = {
                "type": el["type"], "id": el["id"],
                "lat": round(la, 6), "lon": round(lo, 6), "tags": tags}
        time.sleep(3)

    if failed > len(boxes) // 4 or len(points) < 1000:
        print(f"Too many failures ({failed} boxes, {len(points)} points); keeping old data.")
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
        with open(os.path.join(tdir, key + ".json"), "w") as fh:
            json.dump({"elements": els}, fh, separators=(",", ":"), ensure_ascii=False)
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump({"updated": time.strftime("%Y-%m-%d"), "tile": TILE, "count": len(points),
                   "tiles": sorted(tiles)}, fh, separators=(",", ":"))
    print(f"Saved {len(points)} points in {len(tiles)} tiles ({failed} boxes failed).")


if __name__ == "__main__":
    main()
