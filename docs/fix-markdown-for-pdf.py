#!/usr/bin/env python3
"""Pre-process Markdown for Pandoc typst PDF generation.

Fixes common formatting issues that cause incorrect rendering in PDF output.
Writes the fixed content to a temporary file and prints the path.
"""
import re
import sys
import tempfile
from pathlib import Path


def fix_markdown_for_pdf(content: str) -> str:
    # Add blank line after bold headers before lists
    content = re.sub(r'(\*\*[^*]+:\*\*)\n(- )', r'\1\n\n\2', content)

    # Add blank line after text ending with : before lists
    content = re.sub(r'([^*\n]:\n)(- )', r'\1\n\2', content)

    # Add blank line after headings
    content = re.sub(
        r'(^#{1,3} .+)\n([^\n#])', r'\1\n\n\2', content, flags=re.MULTILINE
    )

    return content


def main():
    if len(sys.argv) < 2:
        print("Usage: fix-markdown-for-pdf.py <input.md>", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    content = input_path.read_text()
    fixed = fix_markdown_for_pdf(content)

    # Write to temp file preserving .md extension
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', delete=False, prefix='pandoc_'
    )
    tmp.write(fixed)
    tmp.close()
    print(tmp.name)


if __name__ == "__main__":
    main()
