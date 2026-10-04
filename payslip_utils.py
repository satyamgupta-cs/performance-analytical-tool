import os
import io
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from db_utils import get_payslip_config

def generate_payslip_pdf(employee_data, month_str=None, year_str=None, output_path=None):
    """
    Generates a dynamic PDF payslip based on database settings and employee tier.
    
    :param employee_data: Dict containing employee details and salary components 
    :param month_str: Target month string or integer (optional, defaults to current month or payload key)
    :param year_str: Target year string or integer (optional, defaults to current year or payload key)
    :param output_path: Optional file path to save PDF. If None, returns BytesIO buffer.
    """
    now = datetime.datetime.now()
    
    # Resolve month_str and year_str safely if omitted
    if not month_str:
        month_str = employee_data.get('month', employee_data.get('month_str', f"{now.month:02d}"))
    if not year_str:
        year_str = employee_data.get('year', employee_data.get('year_str', str(now.year)))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        output_path if output_path else buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    story = []
    styles = getSampleStyleSheet()

    # Custom Paragraph Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=12
    )
    header_label = ParagraphStyle('HeaderLabel', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#64748B'))
    header_val = ParagraphStyle('HeaderVal', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#0F172A'), fontName='Helvetica-Bold')
    
    cell_style = ParagraphStyle('CellText', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#334155'))
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#0F172A'), fontName='Helvetica-Bold')
    cell_right_bold = ParagraphStyle('CellRightBold', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#0F172A'), fontName='Helvetica-Bold', alignment=2)
    cell_right = ParagraphStyle('CellRight', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#334155'), alignment=2)

    # 1. Header Title Block
    story.append(Paragraph(f"Payslip for {year_str}-{str(month_str).zfill(2)}", title_style))
    story.append(Paragraph("StaffScore Pvt. Ltd. • Employee Compensation Statement", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceAfter=15))

    # 2. Employee Metadata Block
    emp_id = str(employee_data.get('id', employee_data.get('employee_id', employee_data.get('emp_id', 'N/A'))))
    emp_name = str(employee_data.get('name', 'N/A'))
    emp_dept = str(employee_data.get('department', employee_data.get('dept', 'N/A')))
    emp_email = str(employee_data.get('email', 'N/A'))
    emp_type = str(employee_data.get('emp_type', 'Corporate'))

    meta_data = [
        [Paragraph("Employee Name", header_label), Paragraph(emp_name, header_val), Paragraph("Employee ID", header_label), Paragraph(emp_id, header_val)],
        [Paragraph("Department", header_label), Paragraph(emp_dept, header_val), Paragraph("Email", header_label), Paragraph(emp_email, header_val)],
        [Paragraph("Employment Tier", header_label), Paragraph(emp_type, header_val), Paragraph("", header_label), Paragraph("", header_val)]
    ]

    meta_table = Table(meta_data, colWidths=[100, 170, 100, 170])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # 3. Dynamic Configuration Retrieval
    all_configs = get_payslip_config()
    tier_config = all_configs.get(emp_type, all_configs.get("Corporate", {}))
    
    active_earnings = tier_config.get("earnings", [])
    active_deductions = tier_config.get("deductions", [])

    # Key Mapping Helper to normalize database dictionary keys
    key_map = {
        "Base Salary": ["base_salary", "Monthly Base Salary", "base", "Basic Salary"],
        "Basic Salary": ["base_salary", "Monthly Base Salary", "base", "Basic Salary"],
        "HRA": ["hra", "HRA"],
        "Allowance": ["allowance", "Special Allowance", "Allowance"],
        "Performance Bonus": ["performance_bonus", "Performance Bonus"],
        "Spot Bonus": ["spot_bonus", "Spot Bonus"],
        "Team Bonus": ["team_bonus", "Team Bonus"],
        "Profit-Sharing Bonus": ["profit_sharing", "profit_sharing_bonus", "Profit-Sharing Bonus"],
        "Referral Bonus": ["referral_bonus", "Referral Bonus"],
        "Provident Fund (PF)": ["pf", "provident_fund", "Provident Fund (PF)", "PF"],
        "PF": ["pf", "provident_fund", "Provident Fund (PF)", "PF"],
        "Tax Deducted at Source (TDS)": ["tds", "tax", "Tax Deducted at Source (TDS)", "TDS"],
        "TDS": ["tds", "tax", "Tax Deducted at Source (TDS)", "TDS"],
        "Health Insurance": ["insurance", "health_insurance", "Health Insurance"],
        "Professional Tax": ["professional_tax", "pt", "Professional Tax"],
        "Unpaid Leave Deduction": ["leave_deduction", "unpaid_leave", "Unpaid Leave Deduction"]
    }

    def fetch_amount(component_label):
        possible_keys = key_map.get(component_label, [component_label, component_label.lower().replace(" ", "_")])
        for k in possible_keys:
            if k in employee_data and employee_data[k] is not None:
                try:
                    return float(employee_data[k])
                except (ValueError, TypeError):
                    pass
        return 0.0

    # 4. Build Itemized Table Data
    table_data = [
        [Paragraph("Component", cell_bold), Paragraph("Type", cell_bold), Paragraph("Amount (₹)", cell_right_bold)]
    ]

    gross_pay = 0.0
    total_deductions = 0.0

    # Process Active Earnings
    for earning in active_earnings:
        amt = fetch_amount(earning)
        gross_pay += amt
        table_data.append([
            Paragraph(earning, cell_style),
            Paragraph("Earning", cell_style),
            Paragraph(f"{amt:,.2f}", cell_right)
        ])

    # Process Active Deductions
    for deduction in active_deductions:
        amt = fetch_amount(deduction)
        total_deductions += amt
        table_data.append([
            Paragraph(deduction, cell_style),
            Paragraph("Deduction", cell_style),
            Paragraph(f"{amt:,.2f}", cell_right)
        ])

    net_pay = gross_pay - total_deductions

    # 5. Table Formatting & Summary Rows
    summary_bg = colors.HexColor('#F8FAFC')
    
    table_data.append([
        Paragraph("Gross Pay", cell_bold),
        Paragraph("Total Earnings", cell_style),
        Paragraph(f"₹ {gross_pay:,.2f}", cell_right_bold)
    ])

    if active_deductions:
        table_data.append([
            Paragraph("Total Deductions", cell_bold),
            Paragraph("Total Deductions", cell_style),
            Paragraph(f"₹ {total_deductions:,.2f}", cell_right_bold)
        ])
        table_data.append([
            Paragraph("Net Take-Home Pay", cell_bold),
            Paragraph("Final Net", cell_style),
            Paragraph(f"₹ {net_pay:,.2f}", cell_right_bold)
        ])

    comp_table = Table(table_data, colWidths=[240, 150, 150])
    ts = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0,1), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]

    num_rows = len(table_data)
    if active_deductions:
        ts.append(('BACKGROUND', (0, num_rows-3), (-1, -1), summary_bg))
        ts.append(('LINEABOVE', (0, num_rows-3), (-1, num_rows-3), 1, colors.HexColor('#94A3B8')))
    else:
        ts.append(('BACKGROUND', (0, num_rows-1), (-1, -1), summary_bg))
        ts.append(('LINEABOVE', (0, num_rows-1), (-1, num_rows-1), 1, colors.HexColor('#94A3B8')))

    comp_table.setStyle(TableStyle(ts))
    story.append(comp_table)
    story.append(Spacer(1, 20))

    # 6. Footer Disclaimer
    if active_deductions:
        disclaimer = "This payslip reflects active earnings and applicable statutory/non-statutory deductions configured in system settings."
    else:
        disclaimer = "This payslip reflects gross earnings as configured for this employment tier. No active deductions are applicable."

    footer_style = ParagraphStyle('FooterStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#94A3B8'), alignment=1)
    story.append(Paragraph(disclaimer, footer_style))

    # Build PDF Document
    doc.build(story)

    if not output_path:
        buffer.seek(0)
        return buffer.getvalue()
    return output_path