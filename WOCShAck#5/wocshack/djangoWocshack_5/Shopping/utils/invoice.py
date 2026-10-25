"""
Shopping invoice utilities.

Generates PDF invoices for completed orders using reportlab and sends them
via the internal webmail service (Flask container at 172.28.0.4).

Uses the same HTTP-based email sending pattern as the Account and Forum modules.
The PDF is base64-encoded and embedded in an HTML email attachment simulation.
"""
import io
import base64
import logging
import os
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

INVOICE_EMAIL_SOURCE = 'V.R.C Marketplace'


def generate_invoice_pdf(order, order_items):
    """
    Generate a PDF invoice for an order using reportlab.

    Builds a professional invoice document with order details, itemised list,
    and payment summary. Returns the PDF as bytes.

    Args:
        order: Order model instance (completed order).
        order_items: QuerySet of OrderItem objects for the order.

    Returns:
        bytes: The PDF document as raw bytes, or None if generation fails.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Table, TableStyle,
            Spacer, HRFlowable
        )
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        story = []

        # ------------------------------------------------------------------
        # Custom styles
        # ------------------------------------------------------------------
        title_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Normal'],
            fontSize=24,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#667eea'),
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            'InvoiceSubtitle',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Helvetica',
            textColor=colors.HexColor('#888888'),
            spaceAfter=2,
        )
        section_title_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#333333'),
            spaceBefore=8,
            spaceAfter=4,
        )
        normal_style = ParagraphStyle(
            'InvoiceNormal',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            leading=13,
        )
        bold_style = ParagraphStyle(
            'InvoiceBold',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#333333'),
        )
        right_style = ParagraphStyle(
            'InvoiceRight',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            alignment=TA_RIGHT,
        )
        total_style = ParagraphStyle(
            'InvoiceTotal',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#667eea'),
            alignment=TA_RIGHT,
        )

        # ------------------------------------------------------------------
        # Header: Company name + Invoice label
        # ------------------------------------------------------------------
        header_data = [
            [
                Paragraph('<b>V.R.C</b><br/><font size="9" color="#888888">Virtual Reality Commerce</font>', styles['Normal']),
                Paragraph(
                    f'<b><font size="18" color="#667eea">INVOICE</font></b><br/>'
                    f'<font size="8" color="#888888">Order #{str(order.id)[:13].upper()}</font>',
                    ParagraphStyle('Right', parent=styles['Normal'], alignment=TA_RIGHT)
                ),
            ]
        ]
        header_table = Table(header_data, colWidths=['50%', '50%'])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(header_table)
        story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#667eea'), spaceAfter=12))

        # ------------------------------------------------------------------
        # Billing info + Order info side by side
        # ------------------------------------------------------------------
        order_date = order.created_at.strftime('%B %d, %Y')
        completed_date = order.completed_at.strftime('%B %d, %Y') if order.completed_at else order_date

        billing_content = (
            f'<b>Billed To:</b><br/>'
            f'{order.billing_first_name} {order.billing_last_name}<br/>'
            f'{order.billing_email}<br/>'
            f'{order.billing_phone or ""}'
        )
        order_info_content = (
            f'<b>Order Date:</b> {order_date}<br/>'
            f'<b>Payment Date:</b> {completed_date}<br/>'
            f'<b>Status:</b> {order.get_status_display()}<br/>'
            f'<b>Order ID:</b> {str(order.id)}'
        )

        info_data = [
            [
                Paragraph(billing_content, normal_style),
                Paragraph(order_info_content, ParagraphStyle('InfoRight', parent=normal_style, alignment=TA_RIGHT)),
            ]
        ]
        info_table = Table(info_data, colWidths=['50%', '50%'])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(info_table)

        # ------------------------------------------------------------------
        # Items table
        # ------------------------------------------------------------------
        story.append(Paragraph('Items Purchased', section_title_style))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#dddddd'), spaceAfter=6))

        table_header = [
            Paragraph('<b>CSS Loader</b>', bold_style),
            Paragraph('<b>Author</b>', bold_style),
            Paragraph('<b>Qty</b>', ParagraphStyle('C', parent=bold_style, alignment=TA_CENTER)),
            Paragraph('<b>Unit Price</b>', ParagraphStyle('R', parent=bold_style, alignment=TA_RIGHT)),
            Paragraph('<b>Total</b>', ParagraphStyle('R', parent=bold_style, alignment=TA_RIGHT)),
        ]
        table_rows = [table_header]

        for item in order_items:
            row = [
                Paragraph(item.css_name, normal_style),
                Paragraph(item.css_author, normal_style),
                Paragraph(str(item.quantity), ParagraphStyle('C', parent=normal_style, alignment=TA_CENTER)),
                Paragraph(f'{item.price_at_purchase} N', right_style),
                Paragraph(f'{item.get_total()} N', right_style),
            ]
            table_rows.append(row)

        items_table = Table(
            table_rows,
            colWidths=['35%', '25%', '8%', '16%', '16%'],
        )
        items_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f2ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            # Data rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            # Borders
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#dddddd')),
            ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 0.5 * cm))

        # ------------------------------------------------------------------
        # Totals section (right-aligned)
        # ------------------------------------------------------------------
        subtotal = order.total_amount
        discount = order.discount_amount
        final_total = order.get_final_total()

        totals_data = []
        totals_data.append([
            '',
            Paragraph('<b>Subtotal:</b>', right_style),
            Paragraph(f'{subtotal} Neuros', right_style),
        ])
        if discount > Decimal('0.00'):
            coupon_label = f' ({order.coupon_code})' if order.coupon_code else ''
            totals_data.append([
                '',
                Paragraph(f'<font color="#27ae60"><b>Discount{coupon_label}:</b></font>', right_style),
                Paragraph(f'<font color="#27ae60">-{discount} Neuros</font>', right_style),
            ])
        totals_data.append([
            '',
            Paragraph('<b>Total Paid:</b>', total_style),
            Paragraph(f'<b>{final_total} Neuros</b>', total_style),
        ])

        totals_table = Table(totals_data, colWidths=['50%', '30%', '20%'])
        totals_table.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEABOVE', (1, -1), (-1, -1), 1, colors.HexColor('#667eea')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(totals_table)

        # ------------------------------------------------------------------
        # Footer
        # ------------------------------------------------------------------
        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#dddddd'), spaceAfter=8))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#aaaaaa'),
            alignment=TA_CENTER,
        )
        story.append(Paragraph(
            'Thank you for your purchase! This is an automatically generated invoice from V.R.C Marketplace.<br/>'
            'For support, please contact us via the platform.',
            footer_style
        ))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    except ImportError:
        logger.error("reportlab is not installed. Cannot generate PDF invoice.")
        return None
    except Exception as e:
        logger.error("PDF invoice generation failed: %s", str(e))
        return None


def send_invoice_email(order, order_items):
    """
    Send an order confirmation email with an embedded PDF invoice link.

    Sends via the internal webmail HTTP service at 172.28.0.4, following the
    same pattern used by Account.views.build_send_email_url and
    Forum.Utils.email_utils.build_send_email_url.

    The PDF bytes are base64-encoded and embedded in the HTML email as a
    data URI link, allowing the recipient to open/save the invoice directly
    from their email client.

    Email failures are suppressed so they never break the order completion flow.

    Args:
        order: Completed Order model instance.
        order_items: QuerySet of OrderItem objects for the order.

    Returns:
        dict with send result, or None if email could not be sent.
    """
    if not order.billing_email:
        logger.debug("Invoice email skipped: no billing email on order %s", order.id)
        return None

    try:
        # Generate PDF
        pdf_bytes = generate_invoice_pdf(order, order_items)

        # Build HTML email content
        order_date = order.created_at.strftime('%B %d, %Y')
        items_html = ''.join(
            f'<tr>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">{item.css_name}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:center;">{item.quantity}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">{item.price_at_purchase} N</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">{item.get_total()} N</td>'
            f'</tr>'
            for item in order_items
        )

        discount_row = ''
        if order.discount_amount > Decimal('0.00'):
            coupon = f' ({order.coupon_code})' if order.coupon_code else ''
            discount_row = (
                f'<tr>'
                f'<td colspan="3" style="text-align:right;padding:4px 10px;color:#27ae60;"><b>Discount{coupon}:</b></td>'
                f'<td style="text-align:right;padding:4px 10px;color:#27ae60;">-{order.discount_amount} Neuros</td>'
                f'</tr>'
            )

        # Build PDF attachment section
        pdf_section = ''
        if pdf_bytes:
            pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
            pdf_section = (
                f'<div style="margin-top:20px;padding:16px;background:#f0f2ff;border-radius:8px;">'
                f'<p style="margin:0 0 8px 0;font-weight:bold;color:#667eea;">Your Invoice (PDF)</p>'
                f'<a href="data:application/pdf;base64,{pdf_b64}" '
                f'download="invoice-{str(order.id)[:13]}.pdf" '
                f'style="display:inline-block;padding:8px 16px;background:#667eea;color:white;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;">'
                f'Download Invoice PDF</a>'
                f'</div>'
            )

        html_content = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333;">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:24px;border-radius:8px 8px 0 0;">
        <h1 style="color:white;margin:0;font-size:24px;">Order Confirmed!</h1>
        <p style="color:rgba(255,255,255,0.85);margin:4px 0 0 0;font-size:14px;">
            Thank you for your purchase, {order.billing_first_name}.
        </p>
    </div>

    <div style="padding:24px;background:#ffffff;border:1px solid #eee;">
        <p style="color:#555;font-size:14px;">
            Your order has been completed successfully on <strong>{order_date}</strong>.
            A summary is provided below.
        </p>

        <h3 style="color:#333;border-bottom:2px solid #667eea;padding-bottom:6px;">Order Summary</h3>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
                <tr style="background:#f0f2ff;">
                    <th style="padding:8px 10px;text-align:left;">CSS Loader</th>
                    <th style="padding:8px 10px;text-align:center;">Qty</th>
                    <th style="padding:8px 10px;text-align:right;">Unit Price</th>
                    <th style="padding:8px 10px;text-align:right;">Total</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
            <tfoot>
                <tr>
                    <td colspan="3" style="text-align:right;padding:6px 10px;"><b>Subtotal:</b></td>
                    <td style="text-align:right;padding:6px 10px;"><b>{order.total_amount} Neuros</b></td>
                </tr>
                {discount_row}
                <tr style="border-top:2px solid #667eea;">
                    <td colspan="3" style="text-align:right;padding:8px 10px;font-size:16px;color:#667eea;"><b>Total Paid:</b></td>
                    <td style="text-align:right;padding:8px 10px;font-size:16px;color:#667eea;"><b>{order.get_final_total()} Neuros</b></td>
                </tr>
            </tfoot>
        </table>

        <p style="color:#888;font-size:12px;margin-top:16px;">
            <b>Order ID:</b> {order.id}
        </p>

        {pdf_section}
    </div>

    <div style="padding:16px 24px;background:#fafafa;border:1px solid #eee;border-top:none;
                border-radius:0 0 8px 8px;text-align:center;">
        <p style="color:#aaa;font-size:12px;margin:0;">
            This is an automated receipt from V.R.C Marketplace.<br>
            Thank you for shopping with us!
        </p>
    </div>
</div>
"""

        result = _send_webmail(
            destination=order.billing_email,
            subject=f'Your V.R.C Order Receipt - #{str(order.id)[:13].upper()}',
            content=html_content,
        )

        if result and 'error' in result:
            logger.warning(
                "Invoice email delivery issue for order %s: %s",
                order.id, result['error']
            )
        return result

    except Exception as e:
        logger.error("Invoice email unexpected error for order %s: %s", order.id, str(e))
        return None


def _send_webmail(destination, subject, content, source=INVOICE_EMAIL_SOURCE, timeout=8):
    """
    Internal helper: send email via the webmail HTTP service.

    Mirrors the pattern from Account.views.build_send_email_url and
    Forum.Utils.email_utils.build_send_email_url.

    Args:
        destination: Recipient email address.
        subject: Email subject line.
        content: HTML email body content.
        source: Sender display name.
        timeout: HTTP request timeout in seconds.

    Returns:
        dict with 'url' and either 'status'+'body' on success, or 'error' on failure.
    """
    query_data = {
        'source': source,
        'destination': destination,
        'subject': subject,
        'content': content,
    }
    url = f'http://{settings.WEBMAIL_HOST}/send?' + urllib.parse.urlencode(query_data)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wocshack-invoice-sender/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode('utf-8', errors='replace')
            return {'url': url, 'status': status, 'body': body}
    except Exception as e:
        logger.warning(
            "Invoice webmail send failed: destination=%s subject=%s error=%s",
            destination, subject, str(e)
        )
        return {'url': url, 'error': str(e)}
