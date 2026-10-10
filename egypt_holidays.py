from datetime import datetime, date
from typing import Optional, Dict, Any

# Pre-computed official Egyptian public holidays with Pay Multipliers
# Multipliers:
# 2 = Double Pay (National & Minor Religious Holidays)
# 3 = Triple Pay (Major Eids: Eid Al-Fitr & Eid Al-Adha)

EGYPT_HOLIDAYS_TABLE = {
    # 2025
    "2025-01-07": {"name": "عيد الميلاد المجيد", "multiplier": 2, "category": "national"},
    "2025-01-25": {"name": "عيد الشرطة وثورة 25 يناير", "multiplier": 2, "category": "national"},
    "2025-03-30": {"name": "عيد الفطر المبارك (اليوم الأول)", "multiplier": 3, "category": "eid"},
    "2025-03-31": {"name": "عيد الفطر المبارك (اليوم الثاني)", "multiplier": 3, "category": "eid"},
    "2025-04-01": {"name": "عيد الفطر المبارك (اليوم الثالث)", "multiplier": 3, "category": "eid"},
    "2025-04-21": {"name": "شم النسيم", "multiplier": 2, "category": "national"},
    "2025-04-25": {"name": "عيد تحرير سيناء", "multiplier": 2, "category": "national"},
    "2025-05-01": {"name": "عيد العمال", "multiplier": 2, "category": "national"},
    "2025-06-05": {"name": "وقفة عرفات", "multiplier": 3, "category": "eid"},
    "2025-06-06": {"name": "عيد الأضحى المبارك (اليوم الأول)", "multiplier": 3, "category": "eid"},
    "2025-06-07": {"name": "عيد الأضحى المبارك (اليوم الثاني)", "multiplier": 3, "category": "eid"},
    "2025-06-08": {"name": "عيد الأضحى المبارك (اليوم الثالث)", "multiplier": 3, "category": "eid"},
    "2025-06-09": {"name": "عيد الأضحى المبارك (اليوم الرابع)", "multiplier": 3, "category": "eid"},
    "2025-06-26": {"name": "رأس السنة الهجرية", "multiplier": 2, "category": "religious"},
    "2025-06-30": {"name": "ثورة 30 يونيو", "multiplier": 2, "category": "national"},
    "2025-07-23": {"name": "ثورة 23 يوليو", "multiplier": 2, "category": "national"},
    "2025-09-04": {"name": "المولد النبوي الشريف", "multiplier": 2, "category": "religious"},
    "2025-10-06": {"name": "عيد القوات المسلحة (6 أكتوبر)", "multiplier": 2, "category": "national"},

    # 2026 (Current Year)
    "2026-01-07": {"name": "عيد الميلاد المجيد", "multiplier": 2, "category": "national"},
    "2026-01-25": {"name": "عيد الشرطة وثورة 25 يناير", "multiplier": 2, "category": "national"},
    "2026-03-20": {"name": "عيد الفطر المبارك (اليوم الأول)", "multiplier": 3, "category": "eid"},
    "2026-03-21": {"name": "عيد الفطر المبارك (اليوم الثاني)", "multiplier": 3, "category": "eid"},
    "2026-03-22": {"name": "عيد الفطر المبارك (اليوم الثالث)", "multiplier": 3, "category": "eid"},
    "2026-04-13": {"name": "شم النسيم", "multiplier": 2, "category": "national"},
    "2026-04-25": {"name": "عيد تحرير سيناء", "multiplier": 2, "category": "national"},
    "2026-05-01": {"name": "عيد العمال", "multiplier": 2, "category": "national"},
    "2026-05-26": {"name": "وقفة عرفات", "multiplier": 3, "category": "eid"},
    "2026-05-27": {"name": "عيد الأضحى المبارك (اليوم الأول)", "multiplier": 3, "category": "eid"},
    "2026-05-28": {"name": "عيد الأضحى المبارك (اليوم الثاني)", "multiplier": 3, "category": "eid"},
    "2026-05-29": {"name": "عيد الأضحى المبارك (اليوم الثالث)", "multiplier": 3, "category": "eid"},
    "2026-05-30": {"name": "عيد الأضحى المبارك (اليوم الرابع)", "multiplier": 3, "category": "eid"},
    "2026-06-16": {"name": "رأس السنة الهجرية", "multiplier": 2, "category": "religious"},
    "2026-06-30": {"name": "ثورة 30 يونيو", "multiplier": 2, "category": "national"},
    "2026-07-23": {"name": "ثورة 23 يوليو", "multiplier": 2, "category": "national"},
    "2026-08-25": {"name": "المولد النبوي الشريف", "multiplier": 2, "category": "religious"},
    "2026-10-06": {"name": "عيد القوات المسلحة (6 أكتوبر)", "multiplier": 2, "category": "national"},

    # 2027
    "2027-01-07": {"name": "عيد الميلاد المجيد", "multiplier": 2, "category": "national"},
    "2027-01-25": {"name": "عيد الشرطة وثورة 25 يناير", "multiplier": 2, "category": "national"},
    "2027-03-09": {"name": "عيد الفطر المبارك (اليوم الأول)", "multiplier": 3, "category": "eid"},
    "2027-03-10": {"name": "عيد الفطر المبارك (اليوم الثاني)", "multiplier": 3, "category": "eid"},
    "2027-03-11": {"name": "عيد الفطر المبارك (اليوم الثالث)", "multiplier": 3, "category": "eid"},
    "2027-05-03": {"name": "شم النسيم", "multiplier": 2, "category": "national"},
    "2027-04-25": {"name": "عيد تحرير سيناء", "multiplier": 2, "category": "national"},
    "2027-05-01": {"name": "عيد العمال", "multiplier": 2, "category": "national"},
    "2027-05-16": {"name": "وقفة عرفات", "multiplier": 3, "category": "eid"},
    "2027-05-17": {"name": "عيد الأضحى المبارك (اليوم الأول)", "multiplier": 3, "category": "eid"},
    "2027-05-18": {"name": "عيد الأضحى المبارك (اليوم الثاني)", "multiplier": 3, "category": "eid"},
    "2027-05-19": {"name": "عيد الأضحى المبارك (اليوم الثالث)", "multiplier": 3, "category": "eid"},
    "2027-05-20": {"name": "عيد الأضحى المبارك (اليوم الرابع)", "multiplier": 3, "category": "eid"},
    "2027-06-06": {"name": "رأس السنة الهجرية", "multiplier": 2, "category": "religious"},
    "2027-06-30": {"name": "ثورة 30 يونيو", "multiplier": 2, "category": "national"},
    "2027-07-23": {"name": "ثورة 23 يوليو", "multiplier": 2, "category": "national"},
    "2027-08-14": {"name": "المولد النبوي الشريف", "multiplier": 2, "category": "religious"},
    "2027-10-06": {"name": "عيد القوات المسلحة (6 أكتوبر)", "multiplier": 2, "category": "national"}
}

def get_holiday_info(target_date: str) -> Optional[Dict[str, Any]]:
    """
    Check if a given date (YYYY-MM-DD) is an official Egyptian holiday.
    Returns dictionary with name, multiplier, and category, or None if regular work day.
    """
    if target_date in EGYPT_HOLIDAYS_TABLE:
        h = EGYPT_HOLIDAYS_TABLE[target_date]
        return {
            "is_holiday": True,
            "name": h["name"],
            "multiplier": h["multiplier"],
            "category": h["category"]
        }
    return None

def get_all_holidays_for_year(year: int) -> Dict[str, Dict[str, Any]]:
    """Return all holidays for a given year."""
    prefix = f"{year}-"
    return {d: info for d, info in EGYPT_HOLIDAYS_TABLE.items() if d.startswith(prefix)}
