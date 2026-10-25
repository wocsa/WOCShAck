"""
Bank PDF generation utilities.

Generates:
  - Individual transaction receipts (generate_transaction_receipt)
  - Card statements for a date range (generate_card_statement)

Uses reportlab for PDF generation, following the same pattern as
Shopping/utils/invoice.py. Returns PDF as bytes; never raises to callers.
"""
import io
import logging
from decimal import Decimal

logger = logging.getLogger('bank')


def generate_transaction_receipt(transaction, user):
    """
    Generate a PDF receipt for a single transaction.

    Args:
        transaction: Bank.models.Transaction instance.
        user: Django User object (owner of the transaction).

    Returns:
        bytes: PDF document, or None if generation fails.
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
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT

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

        title_style = ParagraphStyle(
            'ReceiptTitle',
            parent=styles['Normal'],
            fontSize=22,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#667eea'),
            spaceAfter=4,
        )
        normal_style = ParagraphStyle(
            'ReceiptNormal',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            leading=14,
        )
        bold_style = ParagraphStyle(
            'ReceiptBold',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#333333'),
        )
        right_style = ParagraphStyle(
            'ReceiptRight',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            alignment=TA_RIGHT,
        )
        amount_style = ParagraphStyle(
            'ReceiptAmount',
            parent=styles['Normal'],
            fontSize=28,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
        )
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#aaaaaa'),
            alignment=TA_CENTER,
        )

        story = []

        # Header
        header_data = [
            [
                Paragraph(
                    '<b>V.R.C</b><br/><font size="9" color="#888888">Banking</font>',
                    styles['Normal']
                ),
                Paragraph(
                    '<b><font size="18" color="#667eea">RECEIPT</font></b><br/>'
                    f'<font size="8" color="#888888">TX #{transaction.id}</font>',
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
        story.append(HRFlowable(
            width='100%', thickness=2,
            color=colors.HexColor('#667eea'), spaceAfter=14
        ))

        # Amount (centered, coloured)
        is_debit = transaction.transaction_type in ('transfer_out', 'payment')
        amount_color = '#ef4444' if is_debit else '#22c55e'
        sign = '-' if is_debit else '+'
        story.append(Paragraph(
            f'<font color="{amount_color}">{sign}{transaction.amount:.2f} NE</font>',
            amount_style
        ))
        story.append(Paragraph(
            transaction.get_transaction_type_display(),
            ParagraphStyle('Sub', parent=styles['Normal'], fontSize=11,
                           textColor=colors.HexColor('#888888'), alignment=TA_CENTER,
                           spaceAfter=18)
        ))

        # Transaction details table
        story.append(HRFlowable(
            width='100%', thickness=0.5,
            color=colors.HexColor('#dddddd'), spaceAfter=8
        ))

        # Build user info string
        full_name = user.get_full_name().strip()
        user_display = full_name if full_name else user.username
        user_email = user.email or ''

        details_data = [
            [Paragraph('<b>Account Holder</b>', bold_style),
             Paragraph(f'{user_display}<br/>{user_email}', normal_style)],
            [Paragraph('<b>Transaction ID</b>', bold_style),
             Paragraph(str(transaction.id), normal_style)],
            [Paragraph('<b>Date &amp; Time</b>', bold_style),
             Paragraph(transaction.created_at.strftime('%B %d, %Y at %H:%M UTC'), normal_style)],
            [Paragraph('<b>Type</b>', bold_style),
             Paragraph(transaction.get_transaction_type_display(), normal_style)],
            [Paragraph('<b>Status</b>', bold_style),
             Paragraph(transaction.get_status_display(), normal_style)],
        ]

        if transaction.counterpart_payment_number:
            masked = f"**** **** **** {transaction.counterpart_payment_number[-4:]}"
            label = 'To' if is_debit else 'From'
            details_data.append([
                Paragraph(f'<b>{label}</b>', bold_style),
                Paragraph(masked, normal_style),
            ])

        if transaction.counterpart_label:
            details_data.append([
                Paragraph('<b>Description</b>', bold_style),
                Paragraph(transaction.counterpart_label, normal_style),
            ])

        if transaction.note:
            import html as _html
            safe_note = _html.escape(transaction.note[:500])
            details_data.append([
                Paragraph('<b>Note</b>', bold_style),
                Paragraph(safe_note, normal_style),
            ])

        if transaction.balance_after is not None:
            details_data.append([
                Paragraph('<b>Balance After</b>', bold_style),
                Paragraph(f'{transaction.balance_after:.2f} NE', normal_style),
            ])

        if transaction.card:
            details_data.append([
                Paragraph('<b>Card</b>', bold_style),
                Paragraph(transaction.card.masked_number(), normal_style),
            ])

        details_table = Table(details_data, colWidths=['35%', '65%'])
        details_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#eeeeee')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
        ]))
        story.append(details_table)

        # Footer
        story.append(Spacer(1, 1.2 * cm))
        story.append(HRFlowable(
            width='100%', thickness=0.5,
            color=colors.HexColor('#dddddd'), spaceAfter=8
        ))
        story.append(Paragraph(
            'This is an automatically generated receipt from V.R.C Banking.<br/>'
            'For support, contact us via the platform. Keep this receipt for your records.',
            footer_style
        ))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    except ImportError:
        logger.error("reportlab is not installed. Cannot generate transaction receipt PDF.")
        return None
    except Exception as e:
        logger.error("Transaction receipt PDF generation failed: %s", str(e))
        return None


def generate_card_statement(user, transactions, period_label, card=None):
    """
    Generate a PDF card/account statement for a date range.

    Args:
        user: Django User object.
        transactions: Queryset or list of Transaction objects (already filtered).
        period_label: String like "January 2026" or "Q1 2026".
        card: Optional BankCard instance (for card-specific statement).

    Returns:
        bytes: PDF document, or None if generation fails.
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
        from django.utils import timezone

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

        normal_style = ParagraphStyle(
            'StmtNormal',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            leading=13,
        )
        bold_style = ParagraphStyle(
            'StmtBold',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#333333'),
        )
        right_style = ParagraphStyle(
            'StmtRight',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555'),
            alignment=TA_RIGHT,
        )
        section_title_style = ParagraphStyle(
            'StmtSection',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#333333'),
            spaceBefore=10,
            spaceAfter=4,
        )
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#aaaaaa'),
            alignment=TA_CENTER,
        )

        story = []

        # Build user display info
        full_name = user.get_full_name().strip()
        user_display = full_name if full_name else user.username
        user_email = user.email or ''

        # Header
        header_data = [
            [
                Paragraph(
                    '<b>V.R.C</b><br/><font size="9" color="#888888">Banking Statement</font>',
                    styles['Normal']
                ),
                Paragraph(
                    f'<b><font size="16" color="#667eea">STATEMENT</font></b><br/>'
                    f'<font size="9" color="#888888">{period_label}</font>',
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
        story.append(HRFlowable(
            width='100%', thickness=2,
            color=colors.HexColor('#667eea'), spaceAfter=12
        ))

        # Account info
        card_info = card.masked_number() if card else 'All Cards'
        account_info = f'Account: {user_display}<br/>{user_email}'
        info_data = [
            [
                Paragraph(account_info, normal_style),
                Paragraph(
                    f'<b>Card:</b> {card_info}<br/>'
                    f'<b>Generated:</b> {timezone.now().strftime("%B %d, %Y")}',
                    ParagraphStyle('InfoRight', parent=normal_style, alignment=TA_RIGHT)
                ),
            ]
        ]
        info_table = Table(info_data, colWidths=['50%', '50%'])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(info_table)

        # Summary
        tx_list = list(transactions)
        total_in = sum(
            tx.amount for tx in tx_list
            if tx.transaction_type in ('transfer_in', 'refund', 'deposit')
            and tx.status == 'completed'
        )
        total_out = sum(
            tx.amount for tx in tx_list
            if tx.transaction_type in ('transfer_out', 'payment')
            and tx.status == 'completed'
        )
        total_count = len(tx_list)

        story.append(Paragraph('Period Summary', section_title_style))
        story.append(HRFlowable(
            width='100%', thickness=0.5,
            color=colors.HexColor('#dddddd'), spaceAfter=6
        ))

        summary_data = [
            [
                Paragraph('<b>Total Transactions</b>', bold_style),
                Paragraph('<b>Money In</b>', bold_style),
                Paragraph('<b>Money Out</b>', bold_style),
                Paragraph('<b>Net</b>', bold_style),
            ],
            [
                Paragraph(str(total_count), normal_style),
                Paragraph(f'<font color="#22c55e">+{total_in:.2f} NE</font>', normal_style),
                Paragraph(f'<font color="#ef4444">-{total_out:.2f} NE</font>', normal_style),
                Paragraph(
                    f'<font color="{"#22c55e" if total_in >= total_out else "#ef4444"}">'
                    f'{"+" if total_in >= total_out else ""}{(total_in - total_out):.2f} NE</font>',
                    normal_style
                ),
            ],
        ]
        summary_table = Table(summary_data, colWidths=['25%', '25%', '25%', '25%'])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f2ff')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.5 * cm))

        # Transactions
        story.append(Paragraph('Transaction Detail', section_title_style))
        story.append(HRFlowable(
            width='100%', thickness=0.5,
            color=colors.HexColor('#dddddd'), spaceAfter=6
        ))

        if tx_list:
            table_rows = [[
                Paragraph('<b>Date</b>', bold_style),
                Paragraph('<b>Type</b>', bold_style),
                Paragraph('<b>Counterpart</b>', bold_style),
                Paragraph('<b>Note</b>', bold_style),
                Paragraph('<b>Status</b>', bold_style),
                Paragraph('<b>Amount</b>', ParagraphStyle('RB', parent=bold_style, alignment=TA_RIGHT)),
            ]]
            for tx in tx_list:
                is_debit = tx.transaction_type in ('transfer_out', 'payment')
                sign = '-' if is_debit else '+'
                amt_color = '#ef4444' if is_debit else '#22c55e'
                counterpart = ''
                if tx.counterpart_payment_number:
                    counterpart = f"**** {tx.counterpart_payment_number[-4:]}"
                elif tx.counterpart_label:
                    counterpart = tx.counterpart_label[:30]

                import html as _html
                safe_note = _html.escape(tx.note[:40]) if tx.note else ''

                table_rows.append([
                    Paragraph(tx.created_at.strftime('%m/%d/%Y'), normal_style),
                    Paragraph(tx.get_transaction_type_display(), normal_style),
                    Paragraph(counterpart, normal_style),
                    Paragraph(safe_note, normal_style),
                    Paragraph(tx.get_status_display(), normal_style),
                    Paragraph(
                        f'<font color="{amt_color}">{sign}{tx.amount:.2f}</font>',
                        ParagraphStyle('RA', parent=normal_style, alignment=TA_RIGHT)
                    ),
                ])

            tx_table = Table(
                table_rows,
                colWidths=['13%', '14%', '18%', '25%', '13%', '17%'],
            )
            tx_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f2ff')),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(tx_table)
        else:
            story.append(Paragraph(
                'No transactions found for this period.',
                ParagraphStyle('Empty', parent=normal_style, textColor=colors.HexColor('#aaaaaa'),
                               alignment=TA_CENTER, spaceBefore=12)
            ))

        # Footer
        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(
            width='100%', thickness=0.5,
            color=colors.HexColor('#dddddd'), spaceAfter=8
        ))
        story.append(Paragraph(
            'This is an automatically generated statement from V.R.C Banking.<br/>'
            'For support, contact us via the platform. Keep this document for your records.',
            footer_style
        ))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    except ImportError:
        logger.error("reportlab is not installed. Cannot generate card statement PDF.")
        return None
    except Exception as e:
        logger.error("Card statement PDF generation failed: %s", str(e))
        return None
