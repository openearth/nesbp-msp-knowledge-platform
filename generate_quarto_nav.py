
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate _quarto.yml (navbar + sidebars) and create/update page .qmd files
from:
  - a normalized navigation file (nodes.csv), and
  - an optional content file (page_content.csv) to drive page bodies.

USAGE (standard, same as pre-render from _quarto.yml, which is also used by running 'quarto render'):
  python generate_quarto_nav.py nodes.csv --yml-out _quarto.yml --create-stubs --sidebar-style docked --sidebar-background light --sidebar-collapse-level 1 --logo assets/GNSBI_NESBp_combined.png

USAGE (basic):
  python generate_quarto_nav.py nodes.csv --yml-out _quarto.yml --create-stubs

USAGE (validate only; prints a tree and warnings; no files written):
  python generate_quarto_nav.py nodes.csv --validate

USAGE (dry run; print YAML to stdout; no files written):
  python generate_quarto_nav.py nodes.csv --dry-run

USAGE (custom content CSV path):
  python generate_quarto_nav.py nodes.csv --content-csv my_content.csv --create-stubs

USAGE (with logo):
  python generate_quarto_nav.py nodes.csv --yml-out _quarto.yml --create-stubs --logo assets/logo.png

OPTIONS:
  --site-title "NESBp"                      Title injected into _quarto.yml
  --yml-out _quarto.yml                     Where to write the Quarto YAML (default: _quarto.yml)
  --create-stubs                            Create/refresh .qmd files (see autogen rules below)
  --content-csv page_content.csv            CSV that defines page bodies (default: page_content.csv)
  --validate                                Print nav tree + warnings; do not write files
  --dry-run                                 Print YAML only; do not write files
  --sidebar-style docked                    Optional sidebar style for each sidebar
  --sidebar-background light                Optional sidebar background for each sidebar
  --sidebar-collapse-level 1                Quarto collapse-level (1 = sections collapsed on load; default Quarto is 2)
  --theme1 cosmo --theme2 brand             Quarto themes to include
  --css styles.css                          Project CSS file
  --logo assets/GNSBI_NESBp_combined.png    Logo image path for navbar (optional)
  --no-toc                                  Disable global table of contents in YAML

CSV: nodes.csv (required)
  Columns (min): id, label, kind
  Optional: parent_id, slug, file_path, order, description, draft, search_exclude, external_url, icon
  'kind' one of: navbar | landing | section | item | external
  'sidebar_as' (landing only): "text" | "section" | "" (auto: section if has children, else text)

CSV: page_content.csv (optional; default filename used if present)
  Columns (common): id, template, layout, grid_sidebar_width, grid_body_width, grid_margin_width, grid_gutter_width, intro_md, image_src, image_width
  Optional images (below intro_md, above iframes):
    image_src: single asset path, JSON array of paths, or pipe-separated paths
    image_width: CSS width for each image (height scales automatically; default 600px)
  Note: when adding image_src/image_width, keep two empty CSV fields before iframe1_src on rows
        that do not use images (,,). Extra trailing columns in the CSV are ignored on read.
  Templates:
    - content:
        intro_md and/or image_src only (no iframes)
    - single_iframe:
        accepts iframe1_* keys (or legacy iframe_*): iframe1_src, iframe1_height, iframe1_width, iframe1_style
        default layout: "[ [1] ]"
    - doble_iframe (two iframes side-by-side):
        requires iframe1_* and iframe2_* sets (…_src, …_height, …_width, …_style)
        default layout: "[ [1,1] ]"

Behavior:
  - Writes _quarto.yml (navbar + per-root sidebars) and includes:
      project.pre-render (to rerun this script)
      project.resources: [nodes.csv, page_content.csv, logo.png (if --logo specified)]
      website.navbar.logo: logo path (if --logo specified)
  - --logo: Adds logo image to navbar (replaces title text) and includes it in resources
  - --create-stubs:
      * If a page has a content row in page_content.csv:
          - Create or update the .qmd ONLY if it does not exist OR contains 'autogen: true' in front matter.
          - Injects grid settings, intro markdown, and the selected template content.
      * Otherwise, create a minimal stub .qmd only if missing.
  - Change-only writes to avoid preview reload loops.

Examples:
  python generate_quarto_nav.py nodes.csv --validate
  python generate_quarto_nav.py nodes.csv --yml-out _quarto.yml --create-stubs
  python generate_quarto_nav.py nodes.csv --content-csv alt_content.csv --create-stubs
  python generate_quarto_nav.py nodes.csv --yml-out _quarto.yml --create-stubs --logo assets/GNSBI_NESBp_combined.png
"""
import csv
import os
import argparse
import json
import re
from collections import defaultdict

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-_\s]+", "", text)
    text = re.sub(r"[\s]+", "-", text).strip("-")
    return text or "page"

def detect_dialect(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        except Exception:
            class _D(csv.Dialect):
                delimiter=","
                quotechar='"'
                doublequote=True
                skipinitialspace=True
                lineterminator="\n"
                quoting=csv.QUOTE_MINIMAL
            dialect = _D()
        return dialect

def normalize_row_keys(row):
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        nk = k.strip().lstrip("\ufeff").lower()
        out[nk] = (v or "").strip()
    return out

def read_nodes(csv_path):
    nodes = {}
    children = defaultdict(list)
    required = {"id","label","kind"}

    dialect = detect_dialect(csv_path)
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        line_no = 1
        for raw in reader:
            line_no += 1
            row = normalize_row_keys(raw)
            if not any((row.get(k) or "").strip() for k in row):
                continue
            missing = [c for c in required if (row.get(c) or "") == ""]
            if missing:
                raise ValueError(f"CSV validation error on line {line_no}: missing required column(s) {missing}. Row: {row}")
            nid = row["id"]
            if nid in nodes:
                raise ValueError(f"Duplicate id '{nid}' on line {line_no}")
            node = {
                "id": nid,
                "parent_id": row.get("parent_id",""),
                "label": row["label"],
                "slug": row.get("slug") or slugify(row["label"]),
                "kind": row["kind"],  # navbar | landing | section | item | external
                "file_path": row.get("file_path",""),
                "order": int(row["order"]) if (row.get("order") or "").isdigit() else 999,
                "description": row.get("description",""),
                "draft": row.get("draft",""),
                "search_exclude": row.get("search_exclude",""),
                "external_url": row.get("external_url",""),
                "icon": row.get("icon",""),
                "sidebar_as": row.get("sidebar_as","").lower(),  # "", "text", "section"
            }
            nodes[node["id"]] = node
        for n in nodes.values():
            pid = n["parent_id"]
            if pid:
                if pid not in nodes:
                    raise ValueError(f"parent_id '{pid}' of node '{n['id']}' not found in CSV")
                children[pid].append(n["id"])
        for pid in list(children.keys()):
            children[pid].sort(key=lambda nid: (nodes[nid]["order"], nodes[nid]["label"].lower()))
    return nodes, children

def find_roots(nodes):
    return [n for n in nodes.values() if n["parent_id"] == "" and n["kind"] == "navbar"]

def compute_default_file_path(nodes, children, node_id):
    n = nodes[node_id]
    if n["kind"] == "external":
        return ""
    path_slugs = [n["slug"]]
    pid = n["parent_id"]
    while pid:
        path_slugs.append(nodes[pid]["slug"])
        pid = nodes[pid]["parent_id"]
    path_slugs.reverse()
    if n["kind"] in ("navbar","landing","section"):
        rel = "/".join(path_slugs + ["index.qmd"])
    else:
        rel = "/".join(path_slugs[:-1] + [f"{n['slug']}.qmd"])
    return rel

def ensure_paths(nodes, children):
    for nid, n in nodes.items():
        if not n["slug"]:
            n["slug"] = slugify(n["label"])
        if n["kind"] != "external" and not n["file_path"]:
            n["file_path"] = compute_default_file_path(nodes, children, nid)

def make_dirs_for(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def write_stub(page_path, title, is_landing=False, children_links=None, description=""):
    if os.path.exists(page_path):
        return
    make_dirs_for(page_path)
    front_matter = [
        "---",
        f'title: "{title}"',
    ]
    if description:
        front_matter.append(f'description: "{description}"')
    front_matter.append("---")
    fm = "\n".join(front_matter) + "\n\n"
    body = ""
    if is_landing and children_links:
        body += "## Contents\n\n"
        for text, href in children_links:
            body += f"- [{text}]({href})\n"
        body += "\n"
    else:
        body += f"Content for **{title}**.\n"
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(fm + body)

def landing_render_mode(node, has_children):
    mode = (node.get("sidebar_as") or "").lower()
    if mode in ("text","section"):
        return mode, ("explicit")
    # auto
    return ("section" if has_children else "text"), ("auto")

def build_sidebar_contents(nodes, children, node_id):
    n = nodes[node_id]
    lines = []
    kids = children.get(node_id, [])
    if n["kind"] in ("landing","section"):
        if n["kind"] == "landing":
            mode, _ = landing_render_mode(n, has_children=bool(kids))
        else:
            mode = "section"
        if mode == "section":
            lines.append(f'- section: "{n["label"]}"')
            if n.get("file_path"):
                lines.append(f'  href: {n["file_path"]}')
            if kids:
                lines.append('  contents:')
                for cid in kids:
                    child = nodes[cid]
                    if child["kind"] in ("landing","section"):
                        sub = build_sidebar_contents(nodes, children, cid)
                        lines.extend(["    " + l for l in sub])
                    else:
                        href = child["external_url"] if child["kind"]=="external" else child["file_path"]
                        lines.append(f'    - text: "{child["label"]}"')
                        lines.append(f'      href: {href}')
        else:  # text
            href = n["external_url"] if n["kind"]=="external" else n["file_path"]
            lines.append(f'- text: "{n["label"]}"')
            lines.append(f'  href: {href}')
    else:
        href = n["external_url"] if n["kind"]=="external" else n["file_path"]
        lines.append(f'- text: "{n["label"]}"')
        lines.append(f'  href: {href}')
    return lines

def build_yaml(site_title, roots, nodes, children, theme1, theme2, css, toc, sidebar_style, sidebar_background, logo=None, sidebar_collapse_level=None):
    L = []
    L.append("project:")
    L.append("  pre-render:")
    # Build pre-render command with current arguments
    pre_render_cmd = 'python generate_quarto_nav.py nodes.csv --yml-out _quarto.yml --create-stubs --sidebar-style docked --sidebar-background light'
    if sidebar_collapse_level is not None:
        pre_render_cmd += f' --sidebar-collapse-level {sidebar_collapse_level}'
    if logo:
        pre_render_cmd += f' --logo {logo}'
    L.append(f'    - "{pre_render_cmd}"')
    L.append("  resources:")
    L.append("    - nodes.csv")
    L.append("    - page_content.csv")
    if logo:
        L.append(f"    - {logo}")
    L.append("  type: website")
    L.append("")
    L.append("execute:")
    L.append("  freeze: auto")
    L.append("")
    L.append("website:")
    L.append(f'  title: "{site_title}"')
    L.append("  navbar:")
    if logo:
        L.append(f'    logo: {logo}')
    L.append("    left:")
    for root in roots:
        L.append(f'      - text: "{root["label"]}"')
        if root.get("file_path"):
            L.append(f'        href: {root["file_path"]}')
    L.append("")
    L.append("  sidebar:")
    for root in roots:
        L.append(f'    - title: "{root["label"]}"')
        if sidebar_style:
            L.append(f'      style: "{sidebar_style}"')
        if sidebar_background:
            L.append(f'      background: {sidebar_background}')
        if sidebar_collapse_level is not None:
            L.append(f'      collapse-level: {sidebar_collapse_level}')
        L.append("      contents:")

        root_children = children.get(root["id"], [])
        has_explicit_landing_child = any(nodes[cid]["kind"] == "landing" for cid in root_children)

        # Only insert the default root link if there is NO explicit landing node.
        if root.get("file_path") and not has_explicit_landing_child:
            L.append(f'        - text: "{root["label"]}"')
            L.append(f'          href: {root["file_path"]}')

        for cid in root_children:
            c = nodes[cid]
            if c["kind"] in ("landing","section"):
                sub = build_sidebar_contents(nodes, children, cid)
                L.extend(["        " + l for l in sub])
            elif c["kind"] in ("item","external"):
                href = c["external_url"] if c["kind"]=="external" else c["file_path"]
                L.append(f'        - text: "{c["label"]}"')
                L.append(f'          href: {href}')
        L.append("")
    L.append("")
    L.append("format:")
    L.append("  html:")
    L.append("    theme:")
    L.append(f"      - {theme1}")
    L.append(f"      - {theme2}")
    L.append(f"    css: {css}")
    L.append(f"    toc: {'true' if toc else 'false'}")
    L.append("")
    return "\n".join(L).rstrip() + "\n"

def validate_tree(nodes, children):
    roots = [n for n in nodes.values() if n["parent_id"]=="" and n["kind"]=="navbar"]
    roots.sort(key=lambda n: (n["order"], n["label"].lower()))
    warnings = []

    def node_line(n):
        basic = f'{n["label"]} [{n["kind"]}]'
        if n["kind"] == "landing":
            mode, origin = landing_render_mode(n, has_children=bool(children.get(n["id"])))
            extra = f' (sidebar_as={n.get("sidebar_as") or "auto"} -> {mode})'
            return basic + extra
        return basic

    # warn: landing as text with children (children would not be shown beneath it)
    for n in nodes.values():
        if n["kind"] == "landing":
            has_kids = bool(children.get(n["id"]))
            mode, origin = landing_render_mode(n, has_children=has_kids)
            if mode == "text" and has_kids:
                warnings.append(f"Landing '{n['label']}' (id={n['id']}) set to 'text' but has children; children won't appear nested under it.")

    # print tree
    def walk(nid, depth=0):
        n = nodes[nid]
        indent = "  " * depth
        print(f"{indent}- {node_line(n)}")
        for cid in children.get(nid, []):
            walk(cid, depth+1)

    print("=== Navigation tree ===")
    for r in roots:
        walk(r["id"], 0)

    if warnings:
        print("\n=== Warnings ===")
        for w in warnings:
            print(f"- {w}")
    else:
        print("\nNo warnings.")

PAGE_CONTENT_FIELDS = (
    "id", "template", "layout", "grid_sidebar_width", "grid_body_width",
    "grid_margin_width", "grid_gutter_width", "intro_md", "image_src", "image_width",
    "iframe1_src", "iframe1_height", "iframe1_width", "iframe1_style",
    "iframe2_src", "iframe2_height", "iframe2_width", "iframe2_style",
)

def read_page_content(csv_path):
    """Return dict by node id with content config; ignore if file missing."""
    if not os.path.exists(csv_path):
        return {}
    dialect = detect_dialect(csv_path)
    items = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        for raw in reader:
            row = normalize_row_keys(raw)
            nid = (row.get("id") or "").strip()
            if not nid:
                continue
            # Keep only known columns so stray/extra CSV columns cannot shift values.
            items[nid] = {field: row.get(field, "") for field in PAGE_CONTENT_FIELDS if field != "id"}
    return items

def file_has_autogen_flag(path):
    """Return True if front matter contains 'autogen: true'."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(2000)
        # crude but effective: look for autogen: true in front matter
        return "autogen: true" in head
    except Exception:
        return False

def parse_image_src(value):
    """Parse image_src as a single path, JSON array, or pipe-separated paths."""
    value = (value or "").strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(path).strip() for path in parsed if str(path).strip()]
        except json.JSONDecodeError:
            pass
    if "|" in value:
        return [path.strip() for path in value.split("|") if path.strip()]
    return [value]

def build_front_matter(cfg, title):
    grid_lines = []
    if any(cfg.get(k) for k in ("grid_sidebar_width", "grid_body_width", "grid_margin_width", "grid_gutter_width")):
        grid_lines = [
            "format:",
            "  html:",
            "    grid:",
            f"      sidebar-width: {cfg.get('grid_sidebar_width', '')}".rstrip(),
            f"      body-width: {cfg.get('grid_body_width', '')}".rstrip(),
            f"      margin-width: {cfg.get('grid_margin_width', '')}".rstrip(),
            f"      gutter-width: {cfg.get('grid_gutter_width', '')}".rstrip(),
        ]
        grid_lines = [ln for ln in grid_lines if not ln.endswith(": ")]
    fm = ["---", f'title: "{title}"', "autogen: true"]
    fm += grid_lines
    fm.append("---")
    return "\n".join(fm)

def render_images_block(cfg):
    """Return markdown/HTML for optional intro images below intro_md."""
    paths = parse_image_src(cfg.get("image_src"))
    if not paths:
        return []
    width = (cfg.get("image_width") or "600px").strip() or "600px"
    img_tags = "\n".join(
        f'    <img src="{path}" alt="" style="width:{width};height:auto;" />'
        for path in paths
    )
    return [
        "```{=html}",
        f'<div class="content-images-scroll" style="--content-image-width:{width};">',
        '  <div class="content-images-row">',
        img_tags,
        "  </div>",
        "</div>",
        "```",
        "",
    ]

def render_intro_and_images(cfg):
    body = []
    intro = (cfg.get("intro_md") or "").strip()
    if intro:
        body += [intro, ""]
    body.extend(render_images_block(cfg))
    return body

def render_content(cfg, title):
    fm_text = build_front_matter(cfg, title)
    body = render_intro_and_images(cfg)
    return fm_text + "\n\n" + "\n".join(body).rstrip() + "\n"

def render_single_iframe(cfg, title):
    fm_text = build_front_matter(cfg, title)

    layout = (cfg.get("layout") or "[ [1] ]").strip()

    # Back-compat: support both iframe_* and iframe1_* field names
    src   = cfg.get("iframe1_src")   or cfg.get("iframe_src")   or ""
    height= cfg.get("iframe1_height")or cfg.get("iframe_height")or "800"
    width = cfg.get("iframe1_width") or cfg.get("iframe_width") or "100%"
    style = cfg.get("iframe1_style") or cfg.get("iframe_style") or "border:none;"

    body = render_intro_and_images(cfg)

    body.append(f'::: {{layout="{layout}"}}')
    body.append("")
    body.append("```{=html}")
    body.append(f'<iframe style="{style}" height="{height}" width="{width}" src="{src}"></iframe>')
    body.append("```")
    body.append("")
    body.append(":::")
    body_text = "\n".join(body)

    return fm_text + "\n\n" + body_text + "\n"

def render_doble_iframe(cfg, title):
    fm_text = build_front_matter(cfg, title)

    layout = (cfg.get("layout") or "[ [1,1] ]").strip()

    # First iframe (same fallbacks as single_iframe)
    src1   = cfg.get("iframe1_src")   or cfg.get("iframe_src")   or ""
    height1= cfg.get("iframe1_height")or cfg.get("iframe_height")or "800"
    width1 = cfg.get("iframe1_width") or cfg.get("iframe_width") or "100%"
    style1 = cfg.get("iframe1_style") or cfg.get("iframe_style") or "border:none;"

    # Second iframe (requires the new keys)
    src2   = cfg.get("iframe2_src")   or ""
    height2= cfg.get("iframe2_height")or "800"
    width2 = cfg.get("iframe2_width") or "100%"
    style2 = cfg.get("iframe2_style") or "border:none;"

    body = render_intro_and_images(cfg)

    body.append(f'::: {{layout="{layout}"}}')
    body.append("")
    body.append("```{=html}")
    body.append(f'<iframe style="{style1}" height="{height1}" width="{width1}" src="{src1}"></iframe>')
    body.append("```")
    body.append("")
    body.append("```{=html}")
    body.append(f'<iframe style="{style2}" height="{height2}" width="{width2}" src="{src2}"></iframe>')
    body.append("```")
    body.append("")
    body.append(":::")
    body_text = "\n".join(body)

    return fm_text + "\n\n" + body_text + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="nodes.csv", help="Path to nodes.csv")
    ap.add_argument("--content-csv", default="page_content.csv",
                help="Optional CSV to drive page bodies (id-based templates)")
    ap.add_argument("--site-title", default="NESBp MSP knowledge sharing platform")
    ap.add_argument("--yml-out", default="_quarto.yml")
    ap.add_argument("--create-stubs", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate", action="store_true", help="Print a tree + warnings; do not write files")
    ap.add_argument("--sidebar-style", default=None)
    ap.add_argument("--sidebar-background", default=None)
    ap.add_argument("--sidebar-collapse-level", type=int, default=1,
                help="Quarto sidebar collapse-level (1 = collapsed on load, 2 = default Quarto expansion)")
    ap.add_argument("--theme1", default="cosmo")
    ap.add_argument("--theme2", default="brand")
    ap.add_argument("--css", default="styles.css")
    ap.add_argument("--logo", default=None, help="Logo image path for navbar (e.g., assets/GNSBI_NESBp_combined.png)")
    ap.add_argument("--no-toc", action="store_true")
    args = ap.parse_args()

    nodes, children = read_nodes(args.csv)
    roots = [*sorted([n for n in nodes.values() if n["parent_id"]=="" and n["kind"]=="navbar"],
                     key=lambda n: (n["order"], n["label"].lower()))]
    if not roots:
        raise SystemExit("No root navbar nodes found (kind=navbar & empty parent_id).")

    ensure_paths(nodes, children)
    content_by_id = read_page_content(args.content_csv)

    if args.validate:
        validate_tree(nodes, children)
        return

    yaml_text = build_yaml(
        site_title=args.site_title,
        roots=roots, nodes=nodes, children=children,
        theme1=args.theme1, theme2=args.theme2, css=args.css,
        toc=not args.no_toc,
        sidebar_style=args.sidebar_style,
        sidebar_background=args.sidebar_background,
        logo=args.logo,
        sidebar_collapse_level=args.sidebar_collapse_level,
    )

    if args.dry_run:
        print(yaml_text)
    else:
        old = None
        if os.path.exists(args.yml_out):
            with open(args.yml_out, "r", encoding="utf-8") as f:
                old = f.read()
        if old != yaml_text:
            with open(args.yml_out, "w", encoding="utf-8") as f:
                f.write(yaml_text)
            print(f"Wrote {args.yml_out}")
        else:
            print(f"{args.yml_out} unchanged")

    if args.create_stubs:
        for n in nodes.values():
            if n["kind"] == "external":
                continue
            fp = n.get("file_path")
            if not fp:
                continue

            content_cfg = content_by_id.get(n["id"])
            template = (content_cfg or {}).get("template", "").strip()
            if content_cfg and template in ("content", "single_iframe", "doble_iframe"):
                can_write = (not os.path.exists(fp)) or file_has_autogen_flag(fp)
                if not can_write:
                    print(f"Skip content write (manual page): {fp}")
                    continue
                if template == "content":
                    page_text = render_content(content_cfg, title=n["label"])
                elif template == "single_iframe":
                    page_text = render_single_iframe(content_cfg, title=n["label"])
                else:
                    page_text = render_doble_iframe(content_cfg, title=n["label"])
                make_dirs_for(fp)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(page_text)
                print(f"Wrote content for {fp} ({template})")
                continue

            if content_cfg and parse_image_src(content_cfg.get("image_src")):
                can_write = (not os.path.exists(fp)) or file_has_autogen_flag(fp)
                if not can_write:
                    print(f"Skip content write (manual page): {fp}")
                    continue
                page_text = render_content(content_cfg, title=n["label"])
                make_dirs_for(fp)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(page_text)
                print(f"Wrote content for {fp} (content)")
                continue

            # Otherwise fall back to the old 'stub if missing' behavior
            is_landing = n["kind"] in ("landing","section")
            children_links = None
            if is_landing and n["id"] in children:
                children_links = []
                for cid in children[n["id"]]:
                    child = nodes[cid]
                    href = child["external_url"] if child["kind"]=="external" else child["file_path"]
                    children_links.append((child["label"], href))
            write_stub(fp, n["label"], is_landing=is_landing, children_links=children_links, description=n.get("description",""))

if __name__ == "__main__":
    main()
