from __future__ import annotations

import json
import os
import googleapiclient
import json
import textwrap
import airium
from string import Template
from dataclasses import dataclass

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
            return "[\n" + textwrap.indent(schema2json(items, indent + 2), " " * (indent + 2)) + ",\n" + (" " * (indent+2)) + "...\n" + (" " * indent) + "]"
        else:
            return f'{schema["type"]}'
    elif "$ref" in schema:
        return f'{schema["$ref"]}'
    else:
        return 'unknown'


@dataclass(kw_only=True)
class DocgenPage:
    contentHTML: str
    description: str
type DocgenResource = dict[str, tuple[str, DocgenResource | DocgenPage]]

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
        a = airium.Airium(source_minify=True)

        desc = method.get("description", "*No description provided.*")
        a.h1(_t = f"Method: {rname}.{mname}")
        a.p(_t = desc)
        
        httpMethod = method["httpMethod"]
        path = method["path"]
        a.h2(_t = "HTTP Request")
        a.code().pre(_t=f"{httpMethod} {self.endpointBaseUrl}{path}")

        params: dict[str, dict[str,dict]] = method.get("parameters")

        if params:
            pathParams = {k:v for k,v in params.items() if v["location"] == "path"}
            queryParams = {k:v for k,v in params.items() if v["location"] == "query"}

            if pathParams:
                a.h2(_t="Path parameters") 
                self.dm_document_params(a, pathParams)
            if queryParams:
                a.h2(_t="Query parameters")
                self.dm_document_params(a, queryParams)

        a.h2(_t="Request body")
        if "request" in method:
            # unblocked <p>
            self.dm_document_type(a, "The request body contains ", method["request"])
        else:
            a.p(_t="The request body must be empty.")

        a.h2(_t="Response body")
        supportsMediaDownload = method.get("supportsMediaDownload", False)
        if "response" not in method and not supportsMediaDownload:
            a.p(_t="The response content is empty.")
        else:
            leading = "If succeeded, the response body contains "
            if not supportsMediaDownload:
                self.dm_document_type(a, leading, method["response"])
            else:
                a.p(_t=f"{leading}the requested content in bytes.")

        return str(a)
    # Create a 2 column table (one side for name and another for type and description (leave blank if none))
    def dm_document_params(s,a,p):
        if not p:
            return "*No parameters.*\n\n"
        table = "| Name | Type | Description |\n|-|-|-|\n"
        for name, param in p.items():
            type = param["type"]
            desc = param.get("desc", "")
            table += f"| `{name}` | `{type}` | {desc} |\n"
        return table + "\n"

    def dm_document_type(self, a, leading, typ):
        if "$ref" in typ:
            rsc = typ["$ref"]
            with a.p():
                a(f"{leading}an instance of ")
                a.a(href=f"/simple_gapi_docs/services/{self.docname}/types/{rsc}.md", _t=rsc)
            return

        a.p(_t=f"an object of the following format:")
        self._document_type_shared(a,typ)

    # assumes the passed in typ represents an object (which it is)
    def _document_type_shared(self, a, typ):
        a.code().pre(_t=schema2json(typ))
        # table documenting the fields
        if "properties" in typ:
            with a.table():
                #ret += "| Field | Type | Description |\n|-|-|-|\n"
                props = typ["properties"]
                with a.tr():
                    a.th(_t="Field")
                    for name in props.keys():
                        a.th(_t=name)
                with a.tr():
                    a.th(_t="Type")
                    for field in props.values():
                        ftype = self.dm_document_type(a, "", field)
                        a.th(_t=ftype)
                with a.tr():
                    a.th(_t="Description")
                    for field in props.values():
                        desc = field.get("desc", "")
                        a.th(_t=desc)

    # The whole type page
    def document_type(self, name, typ):
        a = airium.Airium(source_minify=True)

        desc = typ.get("description", "*No description provided.*")
        a.h1(f"Type: {name}")
        a.p(desc)
        a.h2("JSON representation:")
        self._document_type_shared(a,typ)
        return str(a)

    def generate_docs(self, parent: DocgenResource):
        doc: DocgenResource = {}
        parent[self.name] = (self.docname, doc)
        self.generate_resource(doc, self.resources)

        # Run through the entire schemas
        tdoc: DocgenResource = {}
        doc["types"] = ("types", tdoc)
        for name, schema in self.schemas.items():
            tdoc[name] = (
                f"{name}", DocgenPage(
                    contentHTML=self.document_type(name, schema),
                    description = schema.get("description", "*No description provided.*")
                )
            )

    def generate_resource(self, doc, resources):
        for rname,rsc in resources.items():
            rdoc: DocgenResource = {}
            doc[rname] = (rname,rdoc)
            if "methods" in rsc: # im not sure why it wouldnt
                for mname,method in rsc["methods"].items():
                    rdoc[mname] = (
                        f"method/{mname}", DocgenPage(
                            contentHTML=self.document_method(rname, mname, method),
                            description=method.get("description", "*No description provided.*")
                        )
                    )
            if "resources" in rsc:
                self.generate_resource(doc, rsc["resources"])


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
        with open(os.path.join("assets","shell.html")) as f:
            shellHTML = Template(f.read())
        for name, (filename, content) in resource.items():
            if isinstance(content, DocgenPage):
                p = os.path.join(path, filename)
                # create dir (recurse) beforehand
                os.makedirs(p, exist_ok=True)
                with open(os.path.join(p, "content.html"), "w") as f:
                    f.write(str(content))
                with open(os.path.join(p, "index.html"), "w") as f:
                    f.write(shellHTML.substitute(
                        title = name,
                        desc = content.description,
                        content = content.contentHTML
                    ))
                with open(os.path.join(p, "metadata.json"), "w") as f:
                    json.dump({
                        "title": name,
                        "desc": content.description
                    }, f, indent=2)


            else:
                write_docs(content, os.path.join(path, filename))

    write_docs(output, "site/services")



if __name__ == "__main__":
    main()
