import io
import re
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from rest_framework.exceptions import ValidationError


MAX_FILE_SIZE = 10 * 1024 * 1024


def validate_file(file):
    if file.size > MAX_FILE_SIZE:
        raise ValidationError('Choose a PDF, PNG or JPEG up to 10 MB.')
    head = file.read(16)
    file.seek(0)
    if head.startswith(b'%PDF-'):
        from pypdf import PdfReader
        try:
            reader = PdfReader(file)
            if reader.is_encrypted or len(reader.pages) > 50:
                raise ValueError()
        except Exception as exc:
            file.seek(0)
            raise ValidationError('Use an unencrypted PDF with at most 50 pages.') from exc
        file.seek(0)
        return 'application/pdf'
    if head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8\xff'):
        from PIL import Image
        try:
            with Image.open(file) as image:
                if image.width * image.height > 30_000_000:
                    raise ValueError()
                image.verify()
        except Exception as exc:
            raise ValidationError('Choose a valid PNG or JPEG under 30 megapixels.') from exc
        finally:
            file.seek(0)
        return 'image/png' if head.startswith(b'\x89PNG') else 'image/jpeg'
    raise ValidationError('Only PDF, PNG and JPEG files are supported.')


def parse_invoice(text):
    text = text[:100000]
    # Prefer an explicitly labelled total; never guess a payment status from text.
    patterns = [r'(?<!sub[ -])\b(?:grand total|amount paid|total paid|total|amount due)\s*[:\-]?\s*(USD|EUR|GBP|PKR|CAD|AUD|INR|JPY|CHF|\$|€|£)\s*([\d,]+\.\d{2})',
                r'\b(USD|EUR|GBP|PKR|CAD|AUD|INR|JPY|CHF)\s*([\d,]+\.\d{2})\b']
    result = {}
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = Decimal(match[2].replace(',', ''))
            if 0 <= value < Decimal('10000000000'):
                result['amount'] = value
                result['currency'] = {'$': 'USD', '€': 'EUR', '£': 'GBP'}.get(match[1], match[1].upper())
            break
    match = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', text)
    if match:
        try:
            result['issued_on'] = date.fromisoformat(match[1])
        except ValueError:
            pass
    return result


def extract_receipt(receipt, *, fallback=None):
    text = ''
    status = 'manual'
    try:
        if receipt.content_type == 'application/pdf':
            from pypdf import PdfReader
            with receipt.file.open('rb') as file:
                reader = PdfReader(file)
                text = '\n'.join((page.extract_text() or '')[:10000] for page in reader.pages[:20])[:100000]
            status = 'extracted' if text.strip() else 'needs_ocr'
        elif settings.TESSERACT_CMD:
            result = subprocess.run([settings.TESSERACT_CMD, str(Path(receipt.file.path).resolve()), 'stdout'],
                capture_output=True, timeout=30, check=True)
            text = result.stdout.decode('utf-8', errors='replace')[:100000]
            status = 'extracted' if text.strip() else 'manual'
        else:
            status = 'needs_ocr'
    except Exception:
        status = 'failed'
    receipt.extracted_text = text
    receipt.extraction_status = status
    for key, value in {**(fallback or {}), **parse_invoice(text)}.items():
        if getattr(receipt, key) in (None, ''):
            setattr(receipt, key, value)
    receipt.save()


def csv_response(headers, rows, filename):
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        # Spreadsheet applications can execute formulas in imported text.
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value for value in row])
    return response


def history_pdf(rows, title):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from django.http import HttpResponse
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    content = [Paragraph(escape(title), styles['Title']), Spacer(1, 12)]
    cells = [['Date', 'Service', 'Team', 'Currency', 'Your amount', 'Status']]
    for row in rows:
        cells.append([str(row.charged_for_date), Paragraph(escape(row.service_name_snapshot), styles['Normal']),
            Paragraph(escape(row.team.name if row.team_id else 'Personal'), styles['Normal']), row.currency, str(row.amount), row.payment_status])
    table = Table(cells, colWidths=[75, 210, 150, 65, 90, 80], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), .5, colors.grey)]))
    content.append(table)
    SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=30, rightMargin=30).build(content)
    return HttpResponse(output.getvalue(), content_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="dues-charge-history.pdf"', 'Cache-Control': 'no-store'})
