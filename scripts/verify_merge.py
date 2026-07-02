import requests
import json
from rdflib import Graph, Namespace, URIRef

API_BASE = "http://localhost:8000"

def fetch(endpoint, method='post'):
    url = API_BASE.rstrip('/') + endpoint
    if method.lower() == 'post':
        r = requests.post(url)
    else:
        r = requests.get(url)
    r.raise_for_status()
    return r.json(), url

def build_graph():
    g = Graph()
    # load ontology
    ont, ont_url = fetch('/ontology.jsonld', method='get')
    try:
        g.parse(data=json.dumps(ont), format='json-ld')
    except Exception as e:
        print('Warning: ontology parse failed:', e)

    endpoints = [('/logius/glossary','post'), ('/duo/glossary','post'), ('/tax-authority/glossary','post'), ('/minvws/glossary','post'), ('/vng/glossary','post')]
    for ep, method in endpoints:
        data, url = fetch(ep, method=method)
        print(f'Fetched {url} — rows: {len(data.get("rows", []))}')
        mapping_url = data.get('mapping')
        rows = data.get('rows', [])
        if mapping_url:
            m = requests.get(mapping_url).json()
            ctx = m.get('@context', m.get('context', {}))
            jsonld_nodes = []
            for i, r in enumerate(rows, start=1):
                node = {'@context': ctx}
                node['@id'] = f"{url}#row{i}"
                for k, v in r.items():
                    if v is None or v == '':
                        continue
                    if isinstance(v, str) and ('|' in v or ';' in v):
                        vals = [s.strip() for s in v.replace(';','|').split('|') if s.strip()]
                        node[k] = vals
                    else:
                        node[k] = v
                jsonld_nodes.append(node)
            try:
                g.parse(data=json.dumps(jsonld_nodes), format='json-ld')
            except Exception as e:
                print('Error parsing JSON-LD nodes for', url, e)
    return g

def verify_links(g: Graph):
    SKOS = Namespace('http://www.w3.org/2004/02/skos/core#')
    query = '''
    SELECT ?s ?p ?o WHERE {
      ?s ?p ?o .
      FILTER(?p = <http://www.w3.org/2004/02/skos/core#relatedMatch> || ?p = <http://www.w3.org/2004/02/skos/core#narrowMatch>)
    }
    '''
    res = g.query(query)
    rows = list(res)
    print(f'Found {len(rows)} SKOS relation triples (relatedMatch/narrowMatch).')
    for r in rows:
        s = str(r.s)
        p = str(r.p)
        o = str(r.o)
        print(f'- {s} {p} {o}')

if __name__ == '__main__':
    print('Building merged RDF graph from APIs...')
    g = build_graph()
    print(f'Total triples in merged graph: {len(g)}')
    verify_links(g)
    # optionally serialize a small TTL for inspection
    print('\n--- Sample triples (up to 30) ---')
    for i, t in enumerate(g):
        if i >= 30:
            break
        print(t)
