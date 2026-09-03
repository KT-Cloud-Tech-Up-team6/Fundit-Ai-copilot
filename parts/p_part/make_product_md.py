import json
from pathlib import Path


INPUT_FILE = Path(__file__).parent / "data" / "product_5454434.json"
OUTPUT_FILE = Path(__file__).parent / "data" / "product_5454434.md"


with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


lines = []

lines.append(f"# {data['product_name']}")
lines.append("")
lines.append(f"- product_id: {data['product_id']}")
lines.append(f"- product_category: {data['product_category']}")
lines.append("")
lines.append("---")
lines.append("")


for item in data["knowledge"]:

    lines.append(
        f"## {item['chunk_id']} | {item['category']}"
    )
    lines.append("")

    lines.append(item["text"])
    lines.append("")

    lines.append(
        f"- strict: {str(item.get('strict', False)).lower()}"
    )

    lines.append(
        f"- source: {item.get('source', '')}"
    )

    lines.append("")
    lines.append("---")
    lines.append("")


OUTPUT_FILE.write_text(
    "\n".join(lines),
    encoding="utf-8"
)


print(f"생성 완료: {OUTPUT_FILE.resolve()}")