"""Renders the dict returned by calculations.build_month_payslip() as a
one-page PDF payslip."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

COMPANY_NAME = "StaffScore Pvt. Ltd."

INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
BORDER = colors.HexColor("#E2E8F0")
HEADER_BG = colors.HexColor("#F1F5F9")


def generate_payslip_pdf(payslip):
    """payslip: the dict returned by calculations.build_month_payslip().
    Returns the PDF as bytes, ready for st.download_button."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PayslipTitle", parent=styles["Title"], fontSize=16, spaceAfter=2)
    subtitle_style = ParagraphStyle("PayslipSubtitle", parent=styles["Normal"], textColor=MUTED)
    section_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], fontSize=11,
        spaceBefore=10, spaceAfter=4, textColor=INK,
    )
    note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=7.5, textColor=MUTED)

    story = [
        Paragraph(COMPANY_NAME, title_style),
        Paragraph(f"Payslip for {payslip['month']}", subtitle_style),
        Spacer(1, 10),
        HRFlowable(width="100%", color=BORDER),
        Spacer(1, 10),
    ]

    emp_table = Table(
        [
            ["Employee Name", payslip["name"], "Employee ID", str(payslip["employee_id"])],
            ["Department", payslip["department"], "Email", payslip["email"] or "-"],
        ],
        colWidths=[35 * mm, 55 * mm, 30 * mm, 50 * mm],
    )
    emp_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]))
    story.append(emp_table)

    story.append(Paragraph("Earnings", section_style))
    earnings_rows = [
        ["Component", "Amount (Rs.)"],
        ["Monthly Base Salary", f"{payslip['base_salary']:,.2f}"],
        ["HRA", f"{payslip['hra']:,.2f}"],
        ["Allowance", f"{payslip['allowance']:,.2f}"],
        [
            f"Performance Bonus ({payslip['bonus_percent']:.0f}% of base, "
            f"score {payslip['overall_score']:.1f}/100)",
            f"{payslip['performance_bonus']:,.2f}",
        ],
        ["Spot Bonus", f"{payslip['spot_bonus']:,.2f}"],
        ["Team Bonus", f"{payslip['team_bonus']:,.2f}"],
        ["Profit-Sharing Bonus", f"{payslip['profit_share_bonus']:,.2f}"],
        ["Referral Bonus", f"{payslip['referral_bonus']:,.2f}"],
    ]
    earnings_table = Table(earnings_rows, colWidths=[130 * mm, 40 * mm])
    earnings_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(earnings_table)

    story.append(Spacer(1, 6))
    total_table = Table(
        [["Gross Pay for the Month", f"Rs. {payslip['gross_pay']:,.2f}"]],
        colWidths=[130 * mm, 40 * mm],
    )
    total_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(total_table)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "This payslip reflects performance-based bonus components (Performance, Spot, "
        "Team, Profit-Sharing and Referral) as recorded in StaffScore. No statutory "
        "deductions (tax, provident fund, etc.) are tracked by this system, so gross "
        "pay is shown as the final figure.",
        note_style,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()