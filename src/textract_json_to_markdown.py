import json
from pathlib import Path
from collections import defaultdict


INPUT_JSON = Path("data/outputs/textract_raw.json")
OUTPUT_MD = Path("data/outputs/sample-bill.md")


def escape_md_cell(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def get_child_text(block: dict, block_map: dict) -> str:
    """Get text inside a CELL block from WORD children."""
    texts = []

    for rel in block.get("Relationships", []):
        if rel.get("Type") != "CHILD":
            continue

        for child_id in rel.get("Ids", []):
            child = block_map.get(child_id)

            if not child:
                continue

            if child.get("BlockType") == "WORD":
                texts.append(child.get("Text", ""))

            elif child.get("BlockType") == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    texts.append("[x]")
                else:
                    texts.append("[ ]")

    return " ".join(texts).strip()


def table_to_markdown(table_block: dict, block_map: dict) -> str:
    """Convert a Textract TABLE block into a Markdown table."""
    cells = []

    for rel in table_block.get("Relationships", []):
        if rel.get("Type") != "CHILD":
            continue

        for child_id in rel.get("Ids", []):
            child = block_map.get(child_id)
            if child and child.get("BlockType") == "CELL":
                cells.append(child)

    if not cells:
        return ""

    max_row = max(cell.get("RowIndex", 1) for cell in cells)
    max_col = max(cell.get("ColumnIndex", 1) for cell in cells)

    grid = [["" for _ in range(max_col)] for _ in range(max_row)]

    for cell in cells:
        row = cell.get("RowIndex", 1) - 1
        col = cell.get("ColumnIndex", 1) - 1
        text = get_child_text(cell, block_map)
        grid[row][col] = escape_md_cell(text)

    # Remove empty rows
    grid = [row for row in grid if any(cell.strip() for cell in row)]

    if not grid:
        return ""

    header = grid[0]
    separator = ["---"] * len(header)
    body = grid[1:]

    md_lines = []
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("| " + " | ".join(separator) + " |")

    for row in body:
        md_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(md_lines)


def convert_textract_to_markdown(textract_json: dict) -> str:
    blocks = textract_json.get("Blocks", [])
    block_map = {block["Id"]: block for block in blocks if "Id" in block}

    lines_by_page = defaultdict(list)
    tables_by_page = defaultdict(list)

    for block in blocks:
        page = block.get("Page", 1)

        if block.get("BlockType") == "LINE" and block.get("Text"):
            lines_by_page[page].append(block["Text"])

        elif block.get("BlockType") == "TABLE":
            table_md = table_to_markdown(block, block_map)
            if table_md:
                tables_by_page[page].append(table_md)

    pages = sorted(set(lines_by_page.keys()) | set(tables_by_page.keys()))
    md_parts = []

    for page in pages:
        md_parts.append(f"# Page {page}\n")

        if lines_by_page.get(page):
            md_parts.append("## Extracted Text\n")
            for line in lines_by_page[page]:
                md_parts.append(line)
            md_parts.append("")

        if tables_by_page.get(page):
            md_parts.append("## Extracted Tables\n")
            for i, table_md in enumerate(tables_by_page[page], start=1):
                md_parts.append(f"### Table {i}\n")
                md_parts.append(table_md)
                md_parts.append("")

    return "\n".join(md_parts)


def main():
    if not INPUT_JSON.exists():
        raise FileNotFoundError(f"Cannot find {INPUT_JSON}")

    textract_json = json.loads(INPUT_JSON.read_text(encoding="utf-16"))
    markdown = convert_textract_to_markdown(textract_json)

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(markdown, encoding="utf-8")

    print(f"Markdown saved to: {OUTPUT_MD}")


if __name__ == "__main__":
    main()