from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import json
from pathlib import Path
import csv

app = FastAPI(title="Mock Glossary APIs (CSV-backed, mapping references)")

ROOT = Path(__file__).parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/ontology.jsonld")
def ontology():
    return JSONResponse(content=load_json(ROOT / "ontology.jsonld"))


@app.get("/nl-sbb.ttl")
def nl_sbb_ttl():
    ttl_path = ROOT / "nl-sbb.ttl"
    if not ttl_path.exists():
        return JSONResponse(status_code=404, content={"error": "NL-SBB TTL not found"})
    content = ttl_path.read_text(encoding='utf-8')
    return Response(content=content, media_type='text/turtle')


def read_csv_rows(path: Path):
    rows = []
    with path.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    return rows


@app.post("/logius/glossary")
def logius_glossary(request: Request):
    rows = read_csv_rows(ROOT / "data" / "logius.csv")
    mapping_url = str(request.url_for("get_mapping", name="logius-mapping.jsonld"))
    return JSONResponse(content={"source": "logius", "rows": rows, "mapping": mapping_url})


@app.post("/duo/glossary")
def orga_glossary(request: Request):
    rows = read_csv_rows(ROOT / "data" / "duo.csv")
    mapping_url = str(request.url_for("get_mapping", name="duo-mapping.jsonld"))
    return JSONResponse(content={"source": "DUO", "rows": rows, "mapping": mapping_url})


@app.post("/tax-authority/glossary")
def orgb_glossary(request: Request):
    rows = read_csv_rows(ROOT / "data" / "tax-authority.csv")
    mapping_url = str(request.url_for("get_mapping", name="tax-authority-mapping.jsonld"))
    return JSONResponse(content={"source": "Tax Authority", "rows": rows, "mapping": mapping_url})


@app.post("/minvws/glossary")
def orgc_glossary(request: Request):
    rows = read_csv_rows(ROOT / "data" / "minvws.csv")
    mapping_url = str(request.url_for("get_mapping", name="minvws-mapping.jsonld"))
    return JSONResponse(content={"source": "MinVWS", "rows": rows, "mapping": mapping_url})


@app.post("/vng/glossary")
def orgd_glossary(request: Request):
    rows = read_csv_rows(ROOT / "data" / "vng.csv")
    mapping_url = str(request.url_for("get_mapping", name="vng-mapping.jsonld"))
    return JSONResponse(content={"source": "VNG", "rows": rows, "mapping": mapping_url})


@app.get("/mappings/{name}", name="get_mapping")
def get_mapping(name: str):
    path = ROOT / "mappings" / name
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "mapping not found"})
    return JSONResponse(content=load_json(path))
