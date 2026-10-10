import os
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import sqlite3
from database import get_connection

def generate_monthly_excel_report(year: int, month: int, output_path: str = None) -> str:
    """
    Generate professional, styled Excel report for HR & Payroll for a specific month.
    """
    if not output_path:
        reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"LiveOps_Report_{year}_{month:02d}.xlsx"
        output_path = os.path.join(reports_dir, filename)

    month_prefix = f"{year}-{month:02d}"

    conn = get_connection()
    cursor = conn.cursor()

    # Get active agents
    cursor.execute("SELECT id, name, code FROM agents WHERE role = 'agent' ORDER BY id ASC;")
    agents = cursor.fetchall()

    wb = openpyxl.Workbook()
    # Sheet 1: Summary
    ws_summary = wb.active
    ws_summary.title = "ملخص الأجور والعمليات"
    ws_summary.views.sheetView[0].rightToLeft = True

    # Sheet 2: Daily Log
    ws_daily = wb.create_sheet(title="سجل الحضور والانصراف اليومي")
    ws_daily.views.sheetView[0].rightToLeft = True

    # Styling Palettes
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    
    title_font = Font(name="Calibri", size=14, bold=True, color="1E293B")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="64748B")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    badge_double = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid") # Amber
    badge_triple = PatternFill(start_color="FCE7F3", end_color="FCE7F3", fill_type="solid") # Pink
    badge_over = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")   # Red

    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    right_align = Alignment(horizontal="right", vertical="center")

    # ==========================
    # SHEET 1: SUMMARY
    # ==========================
    ws_summary["A1"] = f"تقرير ملخص عمليات وأجور فريق LiveOps - لشهر {month:02d} / {year}"
    ws_summary["A1"].font = title_font
    ws_summary["A2"] = f"تاريخ الاستخراج: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | مواعيد الشفت الرسمية: 10:00 ص - 7:00 م (ساعة بريك)"
    ws_summary["A2"].font = subtitle_font

    summary_headers = [
        "كود الموظف",
        "اسم الموظفة",
        "أيام العمل المجدولة",
        "أيام العمل الفعلية",
        "صافي ساعات العمل (Net Hours)",
        "إجمالي ساعات التواجد (Gross)",
        "إجمالي دقائق البريك",
        "كسر البريك (دقيقة)",
        "دقائق الميتنج (Meeting)",
        "دقائق الطوارئ (Emergency)",
        "تأخير غير معوض (دقيقة)",
        "تأخيرات تم تعويضها",
        "استئذان معتمد (ساعات)",
        "ساعات إضافية (Overtime)",
        "أيام عادية (1x)",
        "أيام إجازة رسمية (2x Double)",
        "أيام أعياد كبرى (3x Triple)"
    ]

    header_row = 4
    for col_idx, h_text in enumerate(summary_headers, start=1):
        cell = ws_summary.cell(row=header_row, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    current_row = header_row + 1
    for row_idx, agent in enumerate(agents):
        agent_id = agent["id"]

        # Aggregate metrics from DB for this agent and month
        # 1. Scheduled work days
        cursor.execute("""
        SELECT COUNT(*) as sched_days 
        FROM schedules 
        WHERE agent_id = ? AND date LIKE ? AND shift_type = 'work';
        """, (agent_id, f"{month_prefix}%"))
        sched_days = cursor.fetchone()["sched_days"] or 0

        # 2. Time logs
        cursor.execute("""
        SELECT 
            COUNT(CASE WHEN clock_in IS NOT NULL THEN 1 END) as actual_days,
            SUM(total_work_minutes) as total_work_min,
            SUM(CASE WHEN is_compensated = 0 THEN late_minutes ELSE 0 END) as uncompensated_late,
            COUNT(CASE WHEN is_compensated = 1 AND late_minutes > 0 THEN 1 END) as compensated_count,
            SUM(overtime_minutes) as total_ot_min
        FROM time_logs
        WHERE agent_id = ? AND date LIKE ?;
        """, (agent_id, f"{month_prefix}%"))
        t_row = cursor.fetchone()
        actual_days = t_row["actual_days"] or 0
        total_work_min = t_row["total_work_min"] or 0
        uncompensated_late = t_row["uncompensated_late"] or 0
        compensated_count = t_row["compensated_count"] or 0
        total_ot_min = t_row["total_ot_min"] or 0

        # 3. Approved Excuses
        cursor.execute("""
        SELECT COUNT(*) as exc_cnt
        FROM excuse_requests
        WHERE agent_id = ? AND date LIKE ? AND status = 'approved';
        """, (agent_id, f"{month_prefix}%"))
        excuse_count = cursor.fetchone()["exc_cnt"] or 0

        # 4. Holidays worked
        cursor.execute("""
        SELECT 
            s.pay_multiplier, COUNT(*) as cnt
        FROM schedules s
        JOIN time_logs t ON s.agent_id = t.agent_id AND s.date = t.date
        WHERE s.agent_id = ? AND s.date LIKE ? AND t.clock_in IS NOT NULL
        GROUP BY s.pay_multiplier;
        """, (agent_id, f"{month_prefix}%"))
        h_rows = cursor.fetchall()
        days_1x = 0
        days_2x = 0
        days_3x = 0
        for hr in h_rows:
            if hr["pay_multiplier"] == 1:
                days_1x += hr["cnt"]
            elif hr["pay_multiplier"] == 2:
                days_2x += hr["cnt"]
            elif hr["pay_multiplier"] == 3:
                days_3x += hr["cnt"]

        # 5. Breaks
        cursor.execute("""
        SELECT SUM(duration_minutes) as total_break_min
        FROM break_logs
        WHERE agent_id = ? AND date LIKE ?;
        """, (agent_id, f"{month_prefix}%"))
        total_break_min = cursor.fetchone()["total_break_min"] or 0
        over_break_min = max(0, total_break_min - (actual_days * 60))

        # 6. Meeting pauses
        cursor.execute("""
        SELECT SUM(duration_minutes) as total_meeting_min
        FROM pause_logs
        WHERE agent_id = ? AND date LIKE ? AND pause_type = 'meeting';
        """, (agent_id, f"{month_prefix}%"))
        total_meeting_min = cursor.fetchone()["total_meeting_min"] or 0

        # 7. Emergency pauses
        cursor.execute("""
        SELECT SUM(duration_minutes) as total_emergency_min
        FROM pause_logs
        WHERE agent_id = ? AND date LIKE ? AND pause_type = 'emergency';
        """, (agent_id, f"{month_prefix}%"))
        total_emergency_min = cursor.fetchone()["total_emergency_min"] or 0

        row_fill = alt_fill if row_idx % 2 == 1 else white_fill

        gross_hours = round((total_work_min + total_break_min + total_meeting_min + total_emergency_min) / 60.0, 1)
        net_hours = round(total_work_min / 60.0, 1)

        values = [
            agent["code"],
            agent["name"],
            sched_days,
            actual_days,
            net_hours,
            gross_hours,
            total_break_min,
            over_break_min,
            total_meeting_min,
            total_emergency_min,
            uncompensated_late,
            compensated_count,
            round(excuse_count * 1.5, 1), # average excuse block or logged
            round(total_ot_min / 60.0, 1),
            days_1x,
            days_2x,
            days_3x
        ]

        for col_idx, val in enumerate(values, start=1):
            cell = ws_summary.cell(row=current_row, column=col_idx, value=val)
            cell.fill = row_fill
            cell.border = thin_border
            cell.alignment = center_align
            if col_idx == 2:
                cell.alignment = right_align
            # Highlight multipliers and late penalties
            if col_idx == 11 and uncompensated_late > 0:
                cell.fill = badge_over
                cell.font = Font(name="Calibri", bold=True, color="991B1B")
            elif col_idx == 16 and days_2x > 0:
                cell.fill = badge_double
            elif col_idx == 17 and days_3x > 0:
                cell.fill = badge_triple

        current_row += 1

    # Auto-adjust column widths
    for col in ws_summary.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_summary.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # ==========================
    # SHEET 2: DAILY LOG
    # ==========================
    ws_daily["A1"] = f"سجل الحضور والانصراف التفصيلي اليومي - لشهر {month:02d} / {year}"
    ws_daily["A1"].font = title_font

    daily_headers = [
        "التاريخ",
        "كود الموظف",
        "اسم الموظفة",
        "نوع الشفت",
        "ساعات الشفت",
        "تسجيل الحضور",
        "تسجيل الانصراف",
        "صافي دقائق العمل (Net)",
        "دقائق البريك",
        "دقائق الميتنج",
        "دقائق الطوارئ",
        "دقائق التأخير",
        "حالة التعويض",
        "مناسبة رسمية / أجر",
        "حالة اليوم"
    ]

    header_row = 3
    for col_idx, h_text in enumerate(daily_headers, start=1):
        cell = ws_daily.cell(row=header_row, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    cursor.execute("""
    SELECT 
        s.date, a.code, a.name, s.shift_type, s.shift_hours,
        t.clock_in, t.clock_out, t.total_work_minutes, t.late_minutes, t.is_compensated,
        s.holiday_name, s.pay_multiplier,
        (SELECT SUM(duration_minutes) FROM break_logs WHERE agent_id = a.id AND date = s.date) as break_min,
        (SELECT SUM(duration_minutes) FROM pause_logs WHERE agent_id = a.id AND date = s.date AND pause_type = 'meeting') as meeting_min,
        (SELECT SUM(duration_minutes) FROM pause_logs WHERE agent_id = a.id AND date = s.date AND pause_type = 'emergency') as emergency_min
    FROM schedules s
    JOIN agents a ON s.agent_id = a.id
    LEFT JOIN time_logs t ON s.agent_id = t.agent_id AND s.date = t.date
    WHERE s.date LIKE ?
    ORDER BY s.date ASC, a.id ASC;
    """, (f"{month_prefix}%",))
    daily_rows = cursor.fetchall()

    d_row_idx = header_row + 1
    for idx, dr in enumerate(daily_rows):
        row_fill = alt_fill if idx % 2 == 1 else white_fill

        mult_text = "يوم عادي (1x)"
        if dr["pay_multiplier"] == 2:
            mult_text = f"إجازة رسمية (2x) - {dr['holiday_name'] or ''}"
        elif dr["pay_multiplier"] == 3:
            mult_text = f"أعياد كبرى (3x) - {dr['holiday_name'] or ''}"

        comp_text = "لا يوجد"
        if dr["late_minutes"] and dr["late_minutes"] > 0:
            comp_text = "تم التعويض بالكامل" if dr["is_compensated"] == 1 else "تأخير غير معوض"

        status_text = "إجازة أسبوعية" if dr["shift_type"] == "off" else ("حاضر" if dr["clock_in"] else "غائب / لم يسجل")

        b_min = dr["break_min"] or 0
        m_min = dr["meeting_min"] or 0
        e_min = dr["emergency_min"] or 0
        net_min = dr["total_work_minutes"] or 0

        vals = [
            dr["date"],
            dr["code"],
            dr["name"],
            dr["shift_type"].upper(),
            dr["shift_hours"],
            dr["clock_in"] or "--:--",
            dr["clock_out"] or "--:--",
            net_min,
            b_min,
            m_min,
            e_min,
            dr["late_minutes"] or 0,
            comp_text,
            mult_text,
            status_text
        ]

        for col_idx, val in enumerate(vals, start=1):
            cell = ws_daily.cell(row=d_row_idx, column=col_idx, value=val)
            cell.fill = row_fill
            cell.border = thin_border
            cell.alignment = center_align
            if col_idx == 3:
                cell.alignment = right_align
            if col_idx == 14 and dr["pay_multiplier"] == 2:
                cell.fill = badge_double
            elif col_idx == 14 and dr["pay_multiplier"] == 3:
                cell.fill = badge_triple

        d_row_idx += 1

    for col in ws_daily.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_daily.column_dimensions[col_letter].width = max(max_len + 4, 12)
        col_letter = get_column_letter(col[0].column)
        ws_daily.column_dimensions[col_letter].width = max(max_len + 4, 12)

    conn.close()
    wb.save(output_path)
    return output_path

if __name__ == "__main__":
    now = datetime.now()
    path = generate_monthly_excel_report(now.year, now.month)
    print("Report generated successfully at:", path)
