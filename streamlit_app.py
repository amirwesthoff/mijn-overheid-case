import streamlit as st
import requests
import os
import json
import streamlit.components.v1 as components
from rdflib import Namespace, URIRef
from rdflib import Graph
from rdflib.namespace import RDFS, SKOS
from difflib import SequenceMatcher

DCT = Namespace('http://purl.org/dc/terms/')
FOAF = Namespace('http://xmlns.com/foaf/0.1/')

st.set_page_config(page_title="RDF Integration PoC", layout="wide")

try:
    # attempt to read api_base from Streamlit secrets; FileNotFoundError is raised
    # when no secrets file exists, so catch and fall back to env/default.
    api_base_secret = None
    try:
        api_base_secret = st.secrets.get("api_base")
    except Exception:
        # st.secrets may raise FileNotFoundError when no secrets file is present
        api_base_secret = None
    API_BASE = api_base_secret or os.environ.get("API_BASE") or "http://localhost:8000"
except Exception:
    API_BASE = os.environ.get("API_BASE") or "http://localhost:8000"

def fetch_jsonld(path: str, method: str = "get"):
    url = API_BASE.rstrip("/") + path
    if method.lower() == "post":
        r = requests.post(url)
    else:
        r = requests.get(url)
    r.raise_for_status()
    # Try to decode JSON, but fall back to raw text when not JSON
    try:
        return r.json(), url
    except ValueError:
        return r.text, url

def load_graph_from_endpoints(endpoints):
    g = Graph()
    for ep in endpoints:
        data, url = fetch_jsonld(ep)
        # parse JSON-LD string by serializing to str
        g.parse(data=json.dumps(data), format="json-ld")
    return g

def ask_openai(api_key: str, system: str, user: str, model: str = "gpt-4o-mini"):
    # Support both openai>=1.0.0 (new client) and older openai versions.
    try:
        import openai
    except Exception as e:
        raise RuntimeError(f"openai package is required: {e}")

    # Try new OpenAI client API: `from openai import OpenAI; client = OpenAI(); client.chat.completions.create(...)`
    # Prefer the new OpenAI client when available (openai>=1.0.0)
    # Execute call and surface richer errors on failure
    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=512,
            )
            # Extract message content robustly
            try:
                choice = resp.choices[0]
                msg = getattr(choice, 'message', None) or (choice.get('message') if isinstance(choice, dict) else None)
                if msg:
                    return msg.content if hasattr(msg, 'content') else msg.get('content')
            except Exception:
                pass
            return str(resp)
        else:
            openai.api_key = api_key
            resp = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=512,
            )
            return resp["choices"][0]["message"]["content"]
    except Exception as e:
        # Gather diagnostic hints
        ver = getattr(openai, '__version__', None)
        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        base = os.environ.get('OPENAI_API_BASE') or os.environ.get('OPENAI_API_BASE_URL')
        hint_lines = [
            f"Exception: {type(e).__name__}: {e}",
            f"openai.__version__={ver}",
            f"HTTP_PROXY={http_proxy}",
            f"HTTPS_PROXY={https_proxy}",
            f"OPENAI_API_BASE={base}",
            "Check: network access to api.openai.com, valid API key, and any corporate proxy/firewall.",
            "If using openai-python>=1.0.0 ensure the package is up-to-date and compatible.",
            "To test connectivity locally, run: curl -H \"Authorization: Bearer $OPENAI_API_KEY\" https://api.openai.com/v1/models"
        ]
        raise RuntimeError("OpenAI request failed. Debug info:\n" + "\n".join(hint_lines)) from e


import json

st.title("NL-SBB demo — Business Glossary Federation")


def render_network_from_graph(g):
        SKOS = Namespace('http://www.w3.org/2004/02/skos/core#')
        RDFS_NS = Namespace('http://www.w3.org/2000/01/rdf-schema#')
        mapping_preds = [SKOS.relatedMatch, SKOS.narrowMatch, SKOS.closeMatch, SKOS.broadMatch]
        nodes_map = {}
        nodes = []
        edges = []

        def add_node(uri, label=None, color=None):
            if uri not in nodes_map:
                nid = len(nodes_map) + 1
                nodes_map[uri] = nid
                label_text = label or (uri.split('/')[-1] if '/' in uri else uri)
                node = {"id": nid, "label": label_text, "title": uri}
                if color:
                    node["color"] = {"background": color}
                nodes.append(node)
            return nodes_map[uri]

        # collect labels and sources
        labels = {}
        sources = {}
        for s, p, o in g:
            if p == SKOS.prefLabel or p == RDFS_NS.label:
                labels[str(s)] = str(o)
            # check for dct:source
            if str(p).startswith('http://purl.org/dc/terms/') and str(p).endswith('source'):
                sources[str(s)] = str(o)

        # build nodes/edges from mapping relations
        for s, p, o in g:
            if p in mapping_preds and isinstance(o, URIRef):
                s_uri = str(s)
                o_uri = str(o)
                s_label = labels.get(s_uri, s_uri.split('/')[-1])
                o_label = labels.get(o_uri, o_uri.split('/')[-1])
                # determine colors by source
                s_source = sources.get(s_uri)
                o_source = sources.get(o_uri)
                sid = add_node(s_uri, s_label)
                oid = add_node(o_uri, o_label)
                edges.append({"from": sid, "to": oid, "label": (str(p).split('#')[-1] if '#' in str(p) else str(p)), "source_from": s_source, "source_to": o_source})

        # fallback add prefLabel nodes if empty
        if not nodes:
            for uri, lab in labels.items():
                add_node(uri, lab, color=None)

        # color map per source
        unique_sources = list({v for v in sources.values() if v})
        palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
        source_color = {s: palette[i % len(palette)] for i, s in enumerate(unique_sources)}

        # apply colors to nodes based on source
        for node in nodes:
            uri = node.get('title')
            src = sources.get(uri)
            if src and src in source_color:
                node['color'] = {"background": source_color[src]}

        return nodes, edges, source_color


def build_vis_html(nodes, edges):
        nodes_json = json.dumps(nodes)
        edges_json = json.dumps(edges)
        html = f"""
        <html>
        <head>
            <script type="text/javascript" src="https://unpkg.com/vis-network@9.1.2/dist/vis-network.min.js"></script>
            <style type="text/css">#network {{ width: 100%; height: 600px; border: 1px solid lightgray; }}</style>
        </head>
        <body>
            <div id="network"></div>
            <script type="text/javascript">
                const nodes = new vis.DataSet({nodes_json});
                const edges = new vis.DataSet({edges_json});
                const container = document.getElementById('network');
                const data = {{ nodes: nodes, edges: edges }};
                const options = {{
                    nodes: {{ shape: 'dot', size: 16 }},
                    edges: {{ arrows: 'to', smooth: true }},
                    physics: {{
                        stabilization: {{ enabled: true, iterations: 1000 }}
                    }},
                    layout: {{ improvedLayout: true }}
                }};
                const network = new vis.Network(container, data, options);
                // after stabilization, fit the view to show the whole graph
                network.once('stabilizationIterationsDone', function () {{
                    try {{
                        network.fit({{animation: {{duration: 300}}}});
                    }} catch (e) {{ console.error(e); }}
                }});
            </script>
        </body>
        </html>
        """
        return html

st.sidebar.header("Load glossaries")

# LLM settings in sidebar (optional - can be provided via env or secrets)
st.sidebar.subheader("LLM")
openai_key = st.sidebar.text_input("OpenAI API key", type="password")
model = st.sidebar.selectbox("Model", options=["gpt-4o-mini", "gpt-4o"], index=0)


def get_openai_key(sidebar_val=None):
    """Resolve OpenAI API key from sidebar, env vars, or Streamlit secrets (multiple keys tried)."""
    if sidebar_val:
        return sidebar_val
    # check common env var names
    for name in ("OPENAI_API_KEY", "OPENAI_APIKEY", "OPENAI_KEY"):
        v = os.environ.get(name)
        if v:
            return v
    # check Streamlit secrets under several common keys
    try:
        s = st.secrets
        for key_name in ("OPENAI_API_KEY", "openai_api_key", "openai_key", "openai", "api_key"):
            v = s.get(key_name) if isinstance(s, dict) or hasattr(s, 'get') else None
            if v:
                return v
    except Exception:
        pass
    return None

# define endpoint groups
ENDPOINT_ALL = [
    ("/ontology.jsonld", "get"),
    ("/logius/glossary", "post"),
    ("/duo/glossary", "post"),
    ("/tax-authority/glossary", "post"),
    ("/minvws/glossary", "post"),
    ("/vng/glossary", "post"),
]
ENDPOINT_LOGIUS_DUO = [
    ("/ontology.jsonld", "get"),
    ("/logius/glossary", "post"),
    ("/duo/glossary", "post"),
]

if st.sidebar.button("Load Logius + DUO"):
    st.session_state['load_choice'] = 'logius_duo'
if st.sidebar.button("Load All"):
    st.session_state['load_choice'] = 'all'

def load_endpoints(endpoints):
    st.session_state['loading'] = True
    raw = {}
    g = Graph()
    errors = []
    try:
        for ep, method in endpoints:
            try:
                data, url = fetch_jsonld(ep, method=method)
                raw[url] = data

                # If we received an rdflib-compatible JSON-LD dict or list, parse it
                if isinstance(data, dict) and ("@context" in data or data.get("@type") == "skos:ConceptScheme"):
                    g.parse(data=json.dumps(data), format='json-ld')
                elif isinstance(data, list) and data and isinstance(data[0], dict) and "@context" in data[0]:
                    g.parse(data=json.dumps(data), format='json-ld')
                else:
                    # expect standard JSON with rows and mapping URL
                    if not isinstance(data, dict):
                        # nothing we can do with plain text here (e.g., TTL). skip.
                        continue
                    mapping_url = data.get('mapping')
                    rows = data.get('rows', [])
                    if mapping_url:
                        try:
                            mapping_resp = requests.get(str(mapping_url))
                            mapping_resp.raise_for_status()
                            mapping = mapping_resp.json()
                        except Exception as me:
                            errors.append(f"Mapping fetch failed for {mapping_url}: {me}")
                            continue

                        ctx = mapping.get('@context', mapping.get('context', {}))
                        # identify which fields are typed as @id in the mapping context
                        id_fields = {k for k, v_ctx in ctx.items() if isinstance(v_ctx, dict) and v_ctx.get('@type') == '@id'}
                        jsonld_nodes = []
                        from urllib.parse import urlparse, quote
                        for i, r in enumerate(rows, start=1):
                            node = {'@context': ctx}
                            node['@id'] = f"{url}#row{i}"
                            for k, v in r.items():
                                if v is None:
                                    continue
                                # handle lists encoded in cell values
                                if isinstance(v, str) and ('|' in v or ';' in v):
                                    vals = [s.strip() for s in v.replace(';','|').split('|') if s.strip()]
                                else:
                                    vals = [v]

                                # for fields that should be IRIs, ensure values are absolute IRIs
                                if k in id_fields:
                                    resolved = []
                                    for val in vals:
                                        if not val:
                                            continue
                                        parsed = urlparse(val)
                                        if parsed.scheme:
                                            resolved.append(val)
                                        else:
                                            # construct an absolute IRI under the source URL to avoid file:/// expansion
                                            resolved.append(f"{url}#{quote(val)}")
                                    # use single value or list depending on original
                                    node[k] = resolved if len(resolved) > 1 else (resolved[0] if resolved else None)
                                else:
                                    node[k] = vals if len(vals) > 1 else vals[0]
                            jsonld_nodes.append(node)

                        try:
                            g.parse(data=json.dumps(jsonld_nodes), format='json-ld')
                        except Exception as pe:
                            errors.append(f"JSON-LD parse failed for {url}: {pe}")
                            continue
            except Exception as ep_err:
                import traceback
                tb = traceback.format_exc()
                errors.append(f"Endpoint {ep} failed: {ep_err}\n{tb}")

        st.session_state['graph'] = g.serialize(format='ttl').decode('utf-8') if hasattr(g.serialize(format='ttl'), 'decode') else g.serialize(format='ttl')
        st.session_state['rdflib_graph_obj'] = g
        st.session_state['raw'] = raw
        # indicate successful load when there are no errors
        if not errors:
            try:
                st.success(f"Loaded {len(raw)} source(s); merged graph has {len(g)} triples")
                st.session_state['last_load_success'] = True
            except Exception:
                # Streamlit may disallow widget creation in some contexts; fall back to state flag
                st.session_state['last_load_success'] = True
        else:
            st.session_state['last_load_success'] = False
    except Exception as e:
        st.error(f"Unexpected error while loading endpoints: {e}")
        errors.append(str(e))
    finally:
        st.session_state['loading'] = False
        if errors:
            for err in errors:
                st.error(err)

# Trigger loading depending on choice
if 'load_choice' in st.session_state:
    choice = st.session_state.get('load_choice')
    if choice == 'logius_duo':
        load_endpoints(ENDPOINT_LOGIUS_DUO)
    elif choice == 'all':
        load_endpoints(ENDPOINT_ALL)


def render_mermaid_html(diagram: str, height: int = 360):
    html = f"""
    <div class="mermaid">{diagram}</div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true}});</script>
    """
    return html


def detect_logius_concept(g, question, top_n=5):
    """Return top candidate Logius concepts from graph as (uri, label, score)"""
    ql = question.lower()
    candidates = []
    for s, p, o in g:
        # find prefLabel/altLabel for subjects that have dct:source Logius
        if p in (SKOS.prefLabel, SKOS.altLabel):
            subj = s
            # check if subject has dct:source containing 'logius'
            has_logius = False
            for _s, _p, _o in g.triples((subj, DCT.source, None)):
                if 'logius' in str(_o).lower():
                    has_logius = True
                    break
            if not has_logius:
                continue
            label = str(o)
            # compute simple similarity against question
            score = SequenceMatcher(None, ql, label.lower()).ratio()
            candidates.append((str(subj), label, score))

    # deduplicate by uri keeping max score
    best = {}
    for uri, label, score in candidates:
        if uri not in best or score > best[uri][1]:
            best[uri] = (label, score)

    sorted_cands = sorted([(u, v[0], v[1]) for u, v in best.items()], key=lambda x: x[2], reverse=True)
    return sorted_cands[:top_n]


def query_concept_facts(g, concept_uri):
    # SPARQL template to fetch labels, definitions, sources, pages and related concepts
    q = f"""
    SELECT ?s ?label ?def ?source ?page ?rel ?relLabel WHERE {{
      BIND(<{concept_uri}> AS ?s)
      OPTIONAL {{ ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label }}
      OPTIONAL {{ ?s <http://www.w3.org/2004/02/skos/core#definition> ?def }}
      OPTIONAL {{ ?s <http://purl.org/dc/terms/source> ?source }}
      OPTIONAL {{ ?s <http://xmlns.com/foaf/0.1/page> ?page }}
      OPTIONAL {{
        {{ ?s <http://www.w3.org/2004/02/skos/core#relatedMatch> ?rel }}
        UNION {{ ?s <http://www.w3.org/2004/02/skos/core#narrowMatch> ?rel }}
        UNION {{ ?s <http://www.w3.org/2004/02/skos/core#closeMatch> ?rel }}
        UNION {{ ?s <http://www.w3.org/2004/02/skos/core#broadMatch> ?rel }}
        OPTIONAL {{ ?rel <http://www.w3.org/2004/02/skos/core#prefLabel> ?relLabel }}
      }}
    }}
    """
    res = g.query(q)
    facts = []
    related = []
    for row in res:
        s = row[0] if len(row) > 0 else None
        label = row[1] if len(row) > 1 else None
        definition = row[2] if len(row) > 2 else None
        source = row[3] if len(row) > 3 else None
        page = row[4] if len(row) > 4 else None
        rel = row[5] if len(row) > 5 else None
        relLabel = row[6] if len(row) > 6 else None
        facts.append({
            's': str(s) if s else None,
            'label': str(label) if label else None,
            'def': str(definition) if definition else None,
            'source': str(source) if source else None,
            'page': str(page) if page else None,
        })
        if rel:
            related.append({'rel': str(rel), 'relLabel': str(relLabel) if relLabel else None})
    # collapse facts to a single representative (they will repeat per related)
    rep = {}
    for f in facts:
        for k, v in f.items():
            if v:
                rep[k] = v
    rep['related'] = related
    return rep

# Always show the main tabs. Contents depend on whether data has been loaded.
tab1, tab2, tab3, tab4 = st.tabs(["Architecture", "Glossaries", "Graph", "Ask"])

with tab1:
    st.subheader("Architecture")
    diagram = """
    graph LR
      subgraph APIs
        L[Logius API] -->|CSV + mapping| G
        D[DUO API] -->|CSV + mapping| G
        T[Tax Authority API] -->|CSV + mapping| G
        M[MinVWS API] -->|CSV + mapping| G
        V[VNG API] -->|CSV + mapping| G
      end
      subgraph Integration
        G[RDF Integration Layer]\n(merge JSON-LD into RDFLib Graph)
        G --> SP[SPARQL queries]
        G --> QA[LLM synthesis]
      end
      SP -->|results| Chat[Streamlit Chatbot]
      QA -->|natural language answers| Chat
    """
    components.html(render_mermaid_html(diagram), height=420)

with tab2:
    st.subheader("Loaded glossaries")
    raw = st.session_state.get('raw')
    if raw:
        for url, data in raw.items():
            title = url.replace(API_BASE, '').lstrip('/')
            with st.expander(title, expanded=False):
                if isinstance(data, dict) and "rows" in data:
                    rows = data.get('rows', [])
                    if rows:
                        st.table(rows)
                    else:
                        st.write("No rows returned")
                    st.markdown(f"**Mapping**: {data.get('mapping')}")
                else:
                    st.json(data)
    else:
        st.info("No glossaries loaded. Use the sidebar buttons to load data from the API.")

with tab3:
    st.subheader("Graph visualization")
    if 'rdflib_graph_obj' in st.session_state:
        nodes, edges, source_color = render_network_from_graph(st.session_state['rdflib_graph_obj'])
        if not nodes:
            st.info("Graph contains no mapping relations to visualise.")
        else:
            html = build_vis_html(nodes, edges)
            components.html(html, height=640)
            # legend for sources
            if source_color:
                with st.container():
                    cols = st.columns(len(source_color))
                    for i, (src, col_hex) in enumerate(source_color.items()):
                        with cols[i]:
                            st.markdown(f"<div style='display:flex;align-items:center'><div style='width:16px;height:16px;background:{col_hex};margin-right:8px;border-radius:3px'></div><div>{src}</div></div>", unsafe_allow_html=True)

            # show raw Turtle under the visualization in a collapsible expander
            with st.expander("Raw merged graph (Turtle)", expanded=False):
                st.code(st.session_state.get('graph', ''), language='ttl')
    else:
        st.info("Load data to see graph visualization.")

with tab4:
    st.subheader("Ask a question")
    g = st.session_state.get('rdflib_graph_obj')
    question = st.text_input("Natural language question (e.g. 'Which organisations link to the Turning 18 life event?')")
    ask_clicked = st.button("Ask", key="ask_button")
    if ask_clicked:
        st.session_state['ask_in_progress'] = True

    if st.session_state.get('ask_in_progress') and question.strip():
        if not g:
            st.error("Load data first to run queries.")
        else:
            # Logius-first detection
            candidates = detect_logius_concept(g, question, top_n=5)
            if candidates:
                top_uri, top_label, top_score = candidates[0]
                st.write(f"Detected Logius candidate: **{top_label}** (score {top_score:.2f})")
                chosen_uri = None
                if top_score < 0.60:
                    opts = [f"{lab} — {uri} (score {sc:.2f})" for uri, lab, sc in candidates]
                    sel = st.selectbox("Select the intended Logius concept", opts, key="logius_select")
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        confirm = st.button("Confirm selection", key="confirm_sel")
                    with col2:
                        cancel = st.button("Cancel", key="cancel_sel")
                    if cancel:
                        st.session_state['ask_in_progress'] = False
                        st.info("Selection cancelled.")
                    if confirm:
                        idx = opts.index(sel)
                        chosen_uri = candidates[idx][0]
                else:
                    chosen_uri = top_uri

                if chosen_uri:
                    facts = query_concept_facts(g, chosen_uri)
                    # Build structured context for LLM
                    snippet_lines = []
                    if facts.get('label'):
                        snippet_lines.append(f"Label: {facts.get('label')}")
                    if facts.get('def'):
                        snippet_lines.append(f"Definition: {facts.get('def')}")
                    if facts.get('source'):
                        snippet_lines.append(f"Source: {facts.get('source')}")
                    if facts.get('page'):
                        snippet_lines.append(f"Page: {facts.get('page')}")
                    if facts.get('related'):
                        for r in facts['related']:
                            snippet_lines.append(f"Related: {r.get('relLabel') or r.get('rel')} -> {r.get('rel')}")

                    snippet = "\n".join(snippet_lines)
                    system = (
                        "You are a concise assistant. Given structured facts about a Logius concept,"
                        " produce per-organisation actionable next steps a citizen should take."
                        " Always cite the authoritative page URLs when available and keep answers brief."
                    )
                    user = f"Question: {question}\n\nConcept facts:\n{snippet}\n\nReturn concise per-organisation next steps and cite sources."
                    key = get_openai_key(openai_key)
                    if not key:
                        st.error("OpenAI API key is required. Set it in the sidebar, `OPENAI_API_KEY` env var, or in `.streamlit/secrets.toml` under `OPENAI_API_KEY`.")
                    else:
                        try:
                            answer = ask_openai(key, system, user, model=model)
                            st.subheader("Answer")
                            st.write(answer)
                        except Exception as e:
                            st.error(f"OpenAI request failed: {e}")
                    # done with this ask interaction
                    st.session_state['ask_in_progress'] = False
            else:
                # Fallback: keyword-based SPARQL search
                keywords = [w.lower() for w in question.split() if len(w) > 3]
                if not keywords:
                    keywords = [question]

                filters = " || ".join([f"(contains(lcase(str(?label)), '{kw}'))" for kw in keywords])
                q = f"""
                SELECT ?s ?label ?desc WHERE {{
                    {{ ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label }} UNION {{ ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }} .
                    OPTIONAL {{ ?s <http://www.w3.org/2004/02/skos/core#definition> ?desc }} .
                    FILTER( {filters} )
                }} LIMIT 50
                """
                try:
                    res = g.query(q)
                    facts = []
                    for row in res:
                        facts.append({"s": str(row.s), "label": str(row.label), "desc": str(row.desc) if row.desc else ""})

                    if not facts:
                        st.warning("No direct matches found in the merged graph.")
                    else:
                        st.write("Retrieved facts:")
                        st.table(facts)

                    snippet = "\n".join([f"- {f['label']}: {f['desc']} (source: {f['s']})" for f in facts])
                    system = "You are a helpful assistant that synthesizes brief answers from factual snippets. Always cite the source URIs provided."
                    user = f"Question: {question}\n\nFacts:\n{snippet}\n\nAnswer concisely and mention source URIs."
                    key = get_openai_key(openai_key)
                    if not key:
                        st.error("OpenAI API key is required. Set it in the sidebar, `OPENAI_API_KEY` env var, or in `.streamlit/secrets.toml` under `OPENAI_API_KEY`.")
                    else:
                        try:
                            answer = ask_openai(key, system, user, model=model)
                            st.subheader("Answer")
                            st.write(answer)
                        except Exception as e:
                            st.error(f"OpenAI request failed: {e}")
                except Exception as e:
                    st.error(f"SPARQL/query error: {e}")

