from __future__ import annotations

import json
import os
import googleapiclient
import yaml
import json
import textwrap

from mkdocs import config
from mkdocs.commands import build, serve

# Construct the path to the bundled discovery documents
discovery_doc_dir = os.path.join(googleapiclient.__path__[0], 'discovery_cache', 'documents')

def schema2json(schema, indent = 0):
    if "type" in schema:
        if schema["type"] == "object":
            props = schema.get("properties", {})
            if not props:
                return "{}"
            inner = ",\n".join(f'"{k}": {schema2json(v, indent + 2)}' for k,v in props.items())
            return "{\n" + textwrap.indent(inner, " " * (indent + 2)) + "\n" + (" " * indent) + "}"
        elif schema["type"] == "array":
            items = schema.get("items", {})
            return "[\n" + textwrap.indent(schema2json(items, indent + 2), " " * (indent + 2)) + "\n" + (" " * (indent+2)) + "\n" + (" " * indent) + "]"
        else:
            return f'{schema["type"]}'
    elif "$ref" in schema:
        return f'{schema["$ref"]}'
    else:
        return 'unknown'


class DiscoveryDocument:
    def __init__(self, file) -> None:
        with open(file) as f:
            doc = json.load(f)
            self.name = doc.get("canonicalName", doc.get("title",""))
            self.docname = doc["name"]
            self.version = doc["version"]
            self.endpointBaseUrl = doc["baseUrl"]
            self.schemas: dict[str, dict] = doc["schemas"]
            self.resources = doc["resources"]

    def document_method(self, rname, mname, method) -> str:
        desc = method.get("desc", "*No description provided.*")
        content = f"# Method: {rname}.{mname}\n{desc}\n\n"
        
        httpMethod = method["httpMethod"]
        path = method["path"]
        content += f"## HTTP Request\n`{httpMethod} {self.endpointBaseUrl}{path}`\n\n"

        params: dict[str, dict[str,dict]] = method.get("parameters")

        if params:
            pathParams = {k:v for k,v in params.items() if v["location"] == "path"}
            queryParams = {k:v for k,v in params.items() if v["location"] == "query"}

            content += "## Path parameters\n" + self.dm_document_params(pathParams)
            content += "## Query parameters\n" + self.dm_document_params(queryParams)

        content += "## Request body\n"
        if "request" in method:
            content += "The request body contains "+self.dm_document_type(method["request"]) + "\n"
        else:
            content += "The request body must be empty.\n"

        content += "## Response body\n"
        supportsMediaDownload = method.get("supportsMediaDownload", False)
        if "response" not in method and not supportsMediaDownload:
            content += "The response content is empty."
        else:
            content += "If succeeded, the response body contains "+(self.dm_document_type(method["response"]) if not supportsMediaDownload else "the requested content in bytes.") + "\n"

        return content
    # Create a 2 column table (one side for name and another for type and description (leave blank if none))
    def dm_document_params(s,p):
        if not p:
            return "*No parameters.*\n\n"
        table = "| Name | Type | Description |\n|-|-|-|\n"
        for name, param in p.items():
            type = param["type"]
            desc = param.get("desc", "")
            table += f"| `{name}` | `{type}` | {desc} |\n"
        return table + "\n"

    def dm_document_type(self, typ):
        if "$ref" in typ:
            #if typ["$ref"] in self.resource_reps.values():
                #rsc = [next(r for r,t in self.resource_reps.items() if t == typ["$ref"])]
                rsc = typ["$ref"]
                return f"an instance of [{rsc}](../../types/{rsc}.html)."
            #else:
                #typ = self.schemas[typ["$ref"]]

        return f"an object of the following format:\n\n{self._document_type_shared(typ)}"

    # assumes the passed in typ represents an object (which it is)
    def _document_type_shared(self, typ):
        ret = f"```\n{schema2json(typ)}\n```\n\n"
        # table documenting the fields
        if "properties" in typ:
            ret += "| Field | Type | Description |\n|-|-|-|\n"
            for name, field in typ["properties"].items():
                ftype = self.dm_document_type(field)
                desc = field.get("desc", "")
                ret += f"| `{name}` | {ftype} | {desc} |\n"
        return ret




    def generate_docs(self, parent: DocgenResource):
        doc: DocgenResource = {}
        parent[self.name] = (self.docname, doc)
        self.generate_resource(doc, self.resources)
    def generate_resource(self, doc, resources):
        for rname,rsc in resources.items():
            rdoc: DocgenResource = {}
            doc[rname] = (rname,rdoc)
            if "methods" in rsc: # im not sure why it wouldnt
                for mname,method in rsc["methods"].items():
                    rdoc[mname] = (f"method/{mname}.md", self.document_method(rname, mname, method))
            if "resources" in rsc:
                self.generate_resource(doc, rsc["resources"])


type DocgenResource = dict[str, tuple[str, DocgenResource | str]]


def main():
    # for every json files in the discovery_cache documents directory
    output = {}
    for file in os.listdir(discovery_doc_dir):
        if file.endswith(".json") and file != "index.json":
            try:
                doc = DiscoveryDocument(os.path.join(discovery_doc_dir, file))
                print(f"Generating docs for {doc.name} ({doc.version}) from {file}...")
                doc.generate_docs(output)
            except: 
                print(f"While trying to parse {file}, an exception occurs:")
                raise

    # Construct the docs/services directory based on output
    def write_docs(resource: DocgenResource, path: str):
        os.makedirs(path, exist_ok=True)
        for (filename, content) in resource.values():
            if isinstance(content, str):
                p = os.path.join(path, filename)
                # create dir (recurse) beforehand
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as f:
                    f.write(content)
            else:
                write_docs(content, os.path.join(path, filename))

    write_docs(output, "docs/services")

    # Load the mkdocs_base.yml file and construct the nav object based on output
    with open("mkdocs_base.yml") as f:
        mkdocs = yaml.safe_load(f)
    mkdocs["nav"] = [{"Home": "index.md"}, {"Services": []}]

    def construct_nav(resource: DocgenResource, path: str):
        nav = []
        for (filename, content) in resource.values():
            if isinstance(content, str):
                nav.append({filename: os.path.join(path, filename)})
            else:
                nav.append({filename: construct_nav(content, os.path.join(path, filename))})
        return nav

    mkdocs["nav"][1]["Services"] = construct_nav(output, "services")

    # save as mkdocs.yml
    with open("mkdocs.yml", "w") as f:
        yaml.dump(mkdocs, f)

    cfg = config.load_config()
    serve.serve()



if __name__ == "__main__":
    main()
