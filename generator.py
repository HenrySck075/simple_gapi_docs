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

    def write_page(self, path: str, name: str, content_html: str, description: str, shellHTML_template):
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "content.html"), "w") as f:
            f.write(content_html)
        with open(os.path.join(path, "index.html"), "w") as f:
            f.write(shellHTML_template.substitute(
                title=name,
                desc=description,
                content=content_html
            ))
        with open(os.path.join(path, "metadata.json"), "w") as f:
            json.dump({
                "title": name,
                "desc": description
            }, f, indent=2)

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
        with a.table():
            with a.tr():
                a.th(_t="Name")
                a.th(_t="Type")
                a.th(_t="Description")
            for name, param in p.items():
                type = param["type"]
                desc = param.get("description", "")
                with a.tr():
                    a.td().code(_t=name)
                    a.td().code(_t=type)
                    a.td(_t=desc)

    def dm_document_type(self, a, leading, typ):
        if "$ref" in typ:
            rsc = typ["$ref"]
            with a.p():
                a(f"{leading}an instance of ")
                a.a(href=f"/simple_gapi_docs/services/{self.docname}/{self.version}/types/{rsc}.md", _t=rsc)
            return

        if typ["type"] == "object":
            a.p(_t=f"{leading}an object of the following format:")
            self._document_type_shared(a,typ)
        elif typ["type"] == "array":
            self.dm_document_type(a, "an array of ", typ["items"])
        else: 
            a.p(_t=typ["type"])

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
                    a.th(_t="Type")
                    a.th(_t="Description")
                for name,field in props.items():
                    with a.tr():
                        a.th(_t=name)
                        with a.th():
                            self.dm_document_type(a, "", field)
                        desc = field.get("description", "")
                        a.th(_t=desc)

    # The whole type page
    def document_type(self, name, typ):
        a = airium.Airium(source_minify=True)

        desc = typ.get("description", "*No description provided.*")
        a.h1(_t=f"Type: {name}")
        a.p(_t=desc)
        a.h2(_t="JSON representation:")
        self._document_type_shared(a,typ)
        return str(a)

    def generate_docs(self, shellHTML_template, base_path: str):
        self._generate_resource(shellHTML_template, base_path, self.resources)
        
        # Write types
        types_path = os.path.join(base_path, "types")
        for name, schema in self.schemas.items():
            type_path = os.path.join(types_path, name)
            content_html = self.document_type(name, schema)
            description = schema.get("description", "*No description provided.*")
            self.write_page(type_path, name, content_html, description, shellHTML_template)

    def _generate_resource(self, shellHTML_template, base_path: str, resources):
        for rname, rsc in resources.items():
            resource_path = os.path.join(base_path, rname)
            
            if "methods" in rsc:
                for mname, method in rsc["methods"].items():
                    method_path = os.path.join(resource_path, f"method/{mname}")
                    content_html = self.document_method(rname, mname, method)
                    description = method.get("description", "*No description provided.*")
                    self.write_page(method_path, mname, content_html, description, shellHTML_template)
            
            if "resources" in rsc:
                self._generate_resource(shellHTML_template, resource_path, rsc["resources"])


def main():
    # for every json files in the discovery_cache documents directory
    with open(os.path.join("assets","shell.html")) as f:
        shellHTML = Template(f.read())
    
    for file in os.listdir(discovery_doc_dir):
        if file.endswith(".json") and file != "index.json":
            try:
                doc = DiscoveryDocument(os.path.join(discovery_doc_dir, file))
                print(f"Generating docs for {doc.name} ({doc.version}) from {file}...")
                service_path = os.path.join("site/services", doc.docname, doc.version)
                os.makedirs(service_path, exist_ok=True)
                doc.generate_docs(shellHTML, service_path)
            except: 
                print(f"While trying to parse {file}, an exception occurs:")
                raise


if __name__ == "__main__":
    main()
