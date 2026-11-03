#!/bin/sh
# Download the standard texts the corpus is based on into reference/ (not redistributed:
# the C drafts are (c) ISO/IEC, the POSIX pages (c) IEEE and The Open Group).
# Needs curl, python3 and (for .txt versions of the PDFs) pdftotext from poppler.
set -e
cd "$(dirname "$0")/../reference"
get() { echo "fetching $2"; curl -fsSL --max-time 180 -o "$2" "$1"; }
get https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1256.pdf n1256.pdf   # C99 + TC1-3
get https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf n1570.pdf   # C11 final draft
get https://www.open-std.org/jtc1/sc22/wg14/www/docs/n3220.pdf n3220.pdf   # C23 working draft
get https://pubs.opengroup.org/onlinepubs/9799919799/functions/fprintf.html posix-9799919799-fprintf.html
get https://pubs.opengroup.org/onlinepubs/9799919799/functions/fwprintf.html posix-9799919799-fwprintf.html
get https://pubs.opengroup.org/onlinepubs/9699919799/functions/fprintf.html posix-9699919799-fprintf.html
if command -v pdftotext >/dev/null; then
  for f in n1256 n1570 n3220; do pdftotext -layout $f.pdf $f.txt; done
fi
python3 -I - <<'PY'
import glob, html, re
for f in glob.glob("posix-*.html"):
    s = open(f, encoding="utf-8", errors="replace").read()
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</dd>|</dt>|</li>|</h\d>|</tr>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    open(f[:-5] + ".txt", "w").write(re.sub(r"\n{3,}", "\n\n", s))
PY
echo done
