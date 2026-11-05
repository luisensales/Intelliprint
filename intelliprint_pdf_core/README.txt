IntelliPrint - bibliotecas PDF principales

Incluye instalacion de:
- PyMuPDF 1.28.2
- pypdf 6.21.1
- pikepdf 10.17.0

CairoSVG se ha excluido porque en Windows requiere ademas la biblioteca nativa Cairo (DLL) y no es necesaria para la primera fase de IntelliPrint.

Uso:
1. Descomprime el ZIP.
2. Ejecuta instalar_intelliprint_pdf_core_windows.bat.
3. Al final deben aparecer tres lineas OK.

Nota:
PyMuPDF recomienda actualmente `import pymupdf` en lugar de `import fitz`.
