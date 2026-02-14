#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  B2B Intelligence Platform — PDF КП Generator
  Интеллектуальная собственность АО «Арагант Групп»
  Copyright (c) 2024-2026 АО «Арагант Групп». Все права защищены.
═══════════════════════════════════════════════════════════════════

Генерация персонализированных коммерческих предложений (PDF).
Использует AI (Gemini) для персонализации текста под боли клиента.

Skills used: pdf-official (reportlab), gemini-api-dev, copywriting
Запуск: python scripts/generate_kp.py --company-id <ID> [--output <file.pdf>]
"""
import os
import sys
import json
import argparse
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy.orm import Session
from src.database import engine
from src.database.models import Company, Contact, Person, Intelligence

# PDF generation (reportlab)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, HRFlowable, Image
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Colors
PRIMARY = HexColor("#1a5276")
SECONDARY = HexColor("#2e86c1")
ACCENT = HexColor("#e74c3c")
LIGHT_BG = HexColor("#f8f9fa")
TEXT_COLOR = HexColor("#2c3e50")
MUTED = HexColor("#7f8c8d")

# Try to register Cyrillic fonts
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

try:
    # Try DejaVu for Cyrillic support
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", font_path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")))
            FONT_REGULAR = "DejaVuSans"
            FONT_BOLD = "DejaVuSans-Bold"
            break
except Exception:
    pass


def create_styles():
    """Create paragraph styles for the KP."""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='KPTitle',
        fontName=FONT_BOLD,
        fontSize=24,
        textColor=PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=6*mm,
        leading=30,
    ))
    
    styles.add(ParagraphStyle(
        name='KPSubtitle',
        fontName=FONT_REGULAR,
        fontSize=14,
        textColor=SECONDARY,
        alignment=TA_CENTER,
        spaceAfter=12*mm,
    ))
    
    styles.add(ParagraphStyle(
        name='KPHeading',
        fontName=FONT_BOLD,
        fontSize=16,
        textColor=PRIMARY,
        spaceBefore=8*mm,
        spaceAfter=4*mm,
    ))
    
    styles.add(ParagraphStyle(
        name='KPBody',
        fontName=FONT_REGULAR,
        fontSize=11,
        textColor=TEXT_COLOR,
        alignment=TA_JUSTIFY,
        spaceAfter=3*mm,
        leading=16,
    ))
    
    styles.add(ParagraphStyle(
        name='KPBullet',
        fontName=FONT_REGULAR,
        fontSize=11,
        textColor=TEXT_COLOR,
        leftIndent=15*mm,
        spaceAfter=2*mm,
        bulletIndent=8*mm,
        leading=15,
    ))
    
    styles.add(ParagraphStyle(
        name='KPSmall',
        fontName=FONT_REGULAR,
        fontSize=9,
        textColor=MUTED,
        alignment=TA_CENTER,
    ))
    
    styles.add(ParagraphStyle(
        name='KPHighlight',
        fontName=FONT_BOLD,
        fontSize=12,
        textColor=ACCENT,
        spaceBefore=3*mm,
        spaceAfter=3*mm,
    ))

    return styles


def generate_kp_pdf(company_id: int, output_path: str = None) -> str:
    """Generate personalized KP (commercial proposal) PDF."""
    session = Session(engine)
    
    company = session.query(Company).filter_by(id=company_id).first()
    if not company:
        print(f"❌ Компания #{company_id} не найдена")
        return None
    
    persons = session.query(Person).filter_by(company_id=company.id).all()
    contacts = session.query(Contact).filter_by(company_id=company.id).all()
    intel = session.query(Intelligence).filter_by(company_id=company.id).first()
    
    # Output path
    if not output_path:
        safe_name = company.name.replace(" ", "_").replace("/", "_")[:30]
        os.makedirs(os.path.join(ROOT, "output", "kp"), exist_ok=True)
        output_path = os.path.join(ROOT, "output", "kp", f"KP_{safe_name}_{datetime.now().strftime('%Y%m%d')}.pdf")
    
    # Create PDF
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=20*mm,
    )
    
    styles = create_styles()
    story = []
    
    # ═══════════ PAGE 1: COVER ═══════════
    story.append(Spacer(1, 30*mm))
    
    # Company logo placeholder
    story.append(Paragraph(
        "АО «Арагант Групп»",
        styles['KPTitle']
    ))
    
    story.append(Paragraph(
        "Контрактное производство БАД и спортивного питания",
        styles['KPSubtitle']
    ))
    
    story.append(HRFlowable(
        width="80%", thickness=2, color=SECONDARY,
        spaceAfter=10*mm, spaceBefore=5*mm
    ))
    
    # Personalized title
    director_name = ""
    if persons:
        director_name = persons[0].full_name
        story.append(Paragraph(
            f"Персональное предложение для",
            styles['KPBody']
        ))
        story.append(Paragraph(
            f"{company.name}",
            styles['KPHeading']
        ))
        if director_name:
            story.append(Paragraph(
                f"Уважаемый(ая) {director_name}",
                styles['KPBody']
            ))
    else:
        story.append(Paragraph(
            f"Коммерческое предложение для {company.name}",
            styles['KPHeading']
        ))
    
    story.append(Spacer(1, 20*mm))
    
    story.append(Paragraph(
        f"Дата: {datetime.now().strftime('%d.%m.%Y')}",
        styles['KPSmall']
    ))
    story.append(Paragraph(
        "Конфиденциально",
        styles['KPSmall']
    ))
    
    story.append(PageBreak())
    
    # ═══════════ PAGE 2: ABOUT + PAIN POINTS ═══════════
    story.append(Paragraph("О нас", styles['KPHeading']))
    story.append(Paragraph(
        "АО «Арагант Групп» — ведущий российский производитель "
        "биологически активных добавок и спортивного питания. "
        "Мы предлагаем полный цикл контрактного производства: "
        "от разработки рецептуры до упаковки готовой продукции.",
        styles['KPBody']
    ))
    
    # Advantages
    story.append(Paragraph("Наши преимущества", styles['KPHeading']))
    advantages = [
        "✅ Собственное производство площадью 5000+ м²",
        "✅ Сертификаты GMP, ISO 22000, ТР ТС",
        "✅ 200+ рецептур в портфеле",
        "✅ Минимальная партия от 1000 шт.",
        "✅ Разработка индивидуальной рецептуры",
        "✅ Полный цикл: от идеи до маркетплейса",
    ]
    for adv in advantages:
        story.append(Paragraph(adv, styles['KPBullet']))
    
    # Personalized section based on AI intel
    if intel:
        story.append(Paragraph(
            f"Почему мы обращаемся к {company.name}",
            styles['KPHeading']
        ))
        
        if intel.summary:
            story.append(Paragraph(
                f"Мы изучили вашу компанию: {intel.summary}",
                styles['KPBody']
            ))
        
        # Pain points → our solutions
        if intel.pain_points:
            try:
                pains = json.loads(intel.pain_points)
                story.append(Paragraph("Мы понимаем ваши задачи:", styles['KPHighlight']))
                for p in pains[:4]:
                    story.append(Paragraph(f"🎯 {p}", styles['KPBullet']))
            except: pass
        
        if intel.approach_strategy:
            story.append(Spacer(1, 3*mm))
            story.append(Paragraph(
                f"💡 {intel.approach_strategy}",
                styles['KPBody']
            ))
    
    story.append(PageBreak())
    
    # ═══════════ PAGE 3: SERVICES + PRICING ═══════════
    story.append(Paragraph("Услуги контрактного производства", styles['KPHeading']))
    
    services_data = [
        ["Услуга", "Описание", "Сроки"],
        ["Разработка рецептуры", "Индивидуальная формула под ваш бренд", "2-4 недели"],
        ["Производство БАД", "Капсулы, таблетки, порошки, жидкости", "3-6 недель"],
        ["Спортивное питание", "Протеин, гейнеры, BCAA, предтренировочные", "3-6 недель"],
        ["Дизайн упаковки", "Разработка этикетки и коробки", "1-2 недели"],
        ["Регистрация СГР", "Свидетельство о гос. регистрации", "4-8 недель"],
        ["Фасовка и упаковка", "Дой-пак, банки, блистеры, коробки", "1-2 недели"],
    ]
    
    service_table = Table(services_data, colWidths=[45*mm, 70*mm, 35*mm])
    service_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#ffffff")),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), TEXT_COLOR),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, MUTED),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor("#ffffff"), LIGHT_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(service_table)
    
    story.append(Spacer(1, 8*mm))
    
    story.append(Paragraph("Специальное предложение", styles['KPHighlight']))
    story.append(Paragraph(
        "При заказе первой партии — бесплатная разработка рецептуры "
        "и скидка 15% на производство. Предложение действительно 30 дней.",
        styles['KPBody']
    ))
    
    story.append(PageBreak())
    
    # ═══════════ PAGE 4: CONTACTS ═══════════
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph("Свяжитесь с нами", styles['KPHeading']))
    
    contact_info = [
        "📞 +7 (XXX) XXX-XX-XX",
        "📧 sales@aragant-group.ru",
        "🌐 www.aragant-group.ru",
        "📍 Россия, Москва",
        "",
        "Telegram: @aragant_sales",
    ]
    for c in contact_info:
        story.append(Paragraph(c, styles['KPBody']))
    
    story.append(Spacer(1, 15*mm))
    story.append(HRFlowable(width="60%", thickness=1, color=MUTED, spaceAfter=5*mm))
    
    story.append(Paragraph(
        "© 2024-2026 АО «Арагант Групп». Все права защищены.",
        styles['KPSmall']
    ))
    story.append(Paragraph(
        "Данное коммерческое предложение является конфиденциальным.",
        styles['KPSmall']
    ))
    
    # Build PDF
    doc.build(story)
    
    session.close()
    
    file_size = os.path.getsize(output_path) / 1024
    print(f"  ✅ КП создано: {output_path} ({file_size:.0f} KB)")
    return output_path


def generate_all_kp(limit: int = 10):
    """Generate KP for top scored companies."""
    session = Session(engine)
    
    companies = session.query(Company).filter(
        Company.lead_score >= 30
    ).order_by(Company.lead_score.desc()).limit(limit).all()
    
    print(f"\n{'='*70}")
    print(f"  📄 ГЕНЕРАЦИЯ КП — {len(companies)} компаний")
    print(f"{'='*70}")
    
    generated = 0
    for idx, c in enumerate(companies, 1):
        print(f"\n[{idx}/{len(companies)}] {c.name} (score={c.lead_score})")
        path = generate_kp_pdf(c.id)
        if path:
            generated += 1
    
    print(f"\n  📊 Создано КП: {generated}")
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate KP PDFs")
    parser.add_argument("--company-id", type=int, help="Generate for specific company")
    parser.add_argument("--all", action="store_true", help="Generate for all top companies")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", help="Output PDF path")
    args = parser.parse_args()
    
    if args.company_id:
        generate_kp_pdf(args.company_id, args.output)
    elif args.all:
        generate_all_kp(args.limit)
    else:
        print("Usage: python scripts/generate_kp.py --company-id <ID> or --all")
