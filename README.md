# NL-SBB RDF Integration PoC

Streamlit + rdflib demo that merges JSON-LD/CSV glossaries into an RDF graph, runs SPARQL, and synthesizes answers with OpenAI.

Quick start (local development)

Python version note (Windows): use Python 3.12 (or 3.11) for this PoC. Newer versions such as 3.14 can trigger NumPy source builds and fail without a C/C++ toolchain.

- Create a Python venv and install deps (example):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

- Configure Streamlit secrets (do NOT commit your key):

Add your OpenAI key to `.streamlit/secrets.toml`:

```toml
OPENAI_API_KEY = "sk-..."
api_base = "http://localhost:8000"
```

- Run the mock API (in one terminal):
```powershell
uvicorn api.app:app --reload --port 8000
```

- Run the Streamlit app (in another terminal):
```powershell
streamlit run streamlit_app.py
```

Security note: `.streamlit/secrets.toml` is ignored by `.gitignore`; ensure it is not committed. If it was committed accidentally, remove it from git history before pushing.
# RDF Integration PoC: business-glossary federation

This PoC demonstrates using RDF/JSON-LD as an integration layer: organisations expose JSON APIs (CSV-backed) with mapping JSON‑LD that link to a shared ontology; a Streamlit app fetches and merges them into an RDF graph and answers natural-language questions using OpenAI.

Quick start

1. Create a Python venv and install deps:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

2. Run the mock API server (serves ontology, mappings and CSV-backed glossaries):

```powershell
uvicorn api.app:app --reload --port 8000
```

3. In another terminal run the Streamlit app:

```powershell
streamlit run streamlit_app.py
```

4. Provide your OpenAI API key in the sidebar and click `Load data`.

Files and endpoints

- **API server:** `api/app.py`
	- Serves the ontology at `/ontology.jsonld` and the NL‑SBB TTL at `/nl-sbb.ttl`.
	- Glossary endpoints (CSV-backed):
		- `/logius/glossary` → `api/data/logius.csv`
		- `/duo/glossary` → `api/data/duo.csv` (DUO: Dienst Uitvoering Onderwijs)
		- `/tax-authority/glossary` → `api/data/tax-authority.csv` (Tax Authority)
		- `/minvws/glossary` → `api/data/minvws.csv` (MinVWS)
		- `/vng/glossary` → `api/data/vng.csv` (VNG)
	- Mapping contexts are under `api/mappings/` (e.g. `duo-mapping.jsonld`). Each mapping includes `dct:source` mapped from the CSV `source` column.

- **Streamlit app:** `streamlit_app.py` — fetches the endpoints above, converts rows to JSON‑LD using the mapping contexts, merges RDF, runs SPARQL, and calls OpenAI for NL answers.

- **Verification script:** `scripts/verify_merge.py` — fetches all glossary endpoints, builds a merged RDF graph and prints sample triples (used during development to validate SKOS links and `dct:source`).

Notes

- Each organisation in `api/data/` intentionally uses a different CSV schema; the mapping JSON‑LD files map those column names to SKOS and `dct:source`.
- Glossary rows include a `source` column; mappings map `source` → `dct:source`, producing triples like:

	- `<http://localhost:8000/duo/glossary#row1> dct:source "DUO (Dienst Uitvoering Onderwijs)" .`

- To add new orgs consider adding a CSV in `api/data/` and a mapping in `api/mappings/`, then add an endpoint in `api/app.py` or use the `/publish/{org}` endpoint if implemented.

If you'd like, I can add the `/publish/{org}` upload endpoint next or enhance the Streamlit UI to visualise `dct:source` per concept.