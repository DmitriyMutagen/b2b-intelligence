#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  B2B Intelligence Platform — Call Analyzer
  Интеллектуальная собственность АО «Арагант Групп»
  Copyright (c) 2024-2026 АО «Арагант Групп». Все права защищены.
═══════════════════════════════════════════════════════════════════

Анализ звонков из Bitrix24 CRM.
- Получение записей звонков через API
- Транскрибация через Gemini (multimodal audio)
- AI-анализ: тональность, возражения, потребности, результат
- Рекомендации менеджеру

Skills used: gemini-api-dev, business-analyst, marketing-psychology
Запуск: python src/analytics/call_analyzer.py [--limit N]
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

WEBHOOK_URL = os.getenv("BITRIX24_WEBHOOK_URL", "").rstrip("/")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def bitrix_call(method: str, params: dict = None) -> dict:
    """Call Bitrix24 REST API."""
    url = f"{WEBHOOK_URL}/{method}.json"
    try:
        resp = requests.post(url, json=params or {}, timeout=15)
        return resp.json()
    except Exception as e:
        print(f"  ❌ Bitrix error: {e}")
        return {}


def get_call_records(days: int = 30, limit: int = 50) -> List[Dict]:
    """Get call records from Bitrix24."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    
    result = bitrix_call("voximplant.statistic.get", {
        "FILTER": {
            ">CALL_START_DATE": since,
            "CALL_TYPE": 1,  # Outgoing
        },
        "SORT": "CALL_START_DATE",
        "ORDER": "desc",
    })
    
    calls = result.get("result", [])
    print(f"  📞 Найдено {len(calls)} звонков за {days} дней")
    return calls[:limit]


def get_call_audio_url(call_id: str) -> Optional[str]:
    """Get audio recording URL for a call."""
    result = bitrix_call("voximplant.statistic.get", {
        "FILTER": {"ID": call_id},
        "SELECT": ["RECORD_FILE_ID", "CALL_RECORD_URL"]
    })
    
    records = result.get("result", [])
    if records and records[0].get("CALL_RECORD_URL"):
        return records[0]["CALL_RECORD_URL"]
    return None


def analyze_call_with_gemini(transcript: str, call_info: dict) -> dict:
    """Analyze call transcript using Gemini AI."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        prompt = f"""Ты — эксперт по анализу B2B продаж. Проанализируй транскрипцию звонка менеджера по продажам.

Контекст: Компания АО «Арагант Групп» предлагает контрактное производство БАД и спортивного питания.

Транскрипция звонка:
{transcript[:5000]}

Информация о звонке:
- Длительность: {call_info.get('duration', 'неизв.')} сек
- Дата: {call_info.get('date', 'неизв.')}
- Тип: исходящий

Проанализируй и верни JSON:
{{
    "overall_score": 0-100,
    "sentiment": "positive/neutral/negative",
    "call_result": "успех/перезвонить/отказ/неопределенно",
    "client_interest_level": "высокий/средний/низкий/нет",
    "objections": ["список возражений клиента"],
    "pain_points_identified": ["выявленные боли клиента"],
    "products_discussed": ["обсуждавшиеся продукты"],
    "next_steps": ["следующие шаги"],
    "manager_strengths": ["что менеджер сделал хорошо"],
    "manager_improvements": ["что менеджер мог сделать лучше"],
    "recommendation": "конкретная рекомендация для менеджера",
    "summary": "краткое резюме звонка (2-3 предложения)"
}}

ТОЛЬКО JSON."""

        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
        
    except Exception as e:
        print(f"  ❌ Gemini analysis error: {e}")
        return {}


def analyze_text_messages(days: int = 30) -> List[Dict]:
    """Analyze CRM activities (texts, emails, notes)."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    
    result = bitrix_call("crm.activity.list", {
        "filter": {
            ">CREATED": since,
            "TYPE_ID": 4,  # Email
        },
        "select": ["ID", "SUBJECT", "DESCRIPTION", "CREATED", "RESPONSIBLE_ID"],
        "order": {"CREATED": "desc"},
    })
    
    activities = result.get("result", [])
    print(f"  📧 Найдено {len(activities)} email активностей за {days} дней")
    return activities


def analyze_funnel(days: int = 90) -> dict:
    """Analyze sales funnel from CRM data."""
    # Get leads
    leads = bitrix_call("crm.lead.list", {
        "select": ["ID", "STATUS_ID", "DATE_CREATE", "TITLE", "OPPORTUNITY"],
        "order": {"DATE_CREATE": "desc"},
    })
    lead_list = leads.get("result", [])
    
    # Get deals
    deals = bitrix_call("crm.deal.list", {
        "select": ["ID", "STAGE_ID", "DATE_CREATE", "TITLE", "OPPORTUNITY"],
        "order": {"DATE_CREATE": "desc"},
    })
    deal_list = deals.get("result", [])
    
    # Funnel analysis
    funnel = {
        "total_leads": len(lead_list),
        "leads_by_status": {},
        "total_deals": len(deal_list),
        "deals_by_stage": {},
        "conversion_rate": 0,
        "avg_deal_value": 0,
        "pipeline_value": 0,
    }
    
    for lead in lead_list:
        status = lead.get("STATUS_ID", "UNKNOWN")
        funnel["leads_by_status"][status] = funnel["leads_by_status"].get(status, 0) + 1
    
    for deal in deal_list:
        stage = deal.get("STAGE_ID", "UNKNOWN")
        funnel["deals_by_stage"][stage] = funnel["deals_by_stage"].get(stage, 0) + 1
        try:
            funnel["pipeline_value"] += float(deal.get("OPPORTUNITY", 0))
        except: pass
    
    if lead_list:
        funnel["conversion_rate"] = round(len(deal_list) / len(lead_list) * 100, 1)
    if deal_list:
        funnel["avg_deal_value"] = round(funnel["pipeline_value"] / len(deal_list))
    
    return funnel


def run_analysis(limit: int = 10):
    """Run full CRM analysis."""
    print(f"\n{'='*70}")
    print(f"  📊 CRM ANALYTICS — АО «Арагант Групп»")
    print(f"{'='*70}")
    
    # 1. Funnel analysis
    print(f"\n  📈 Анализ воронки...")
    funnel = analyze_funnel()
    print(f"    Лидов: {funnel['total_leads']}")
    print(f"    Статусы лидов: {json.dumps(funnel['leads_by_status'], indent=2, ensure_ascii=False)}")
    print(f"    Сделок: {funnel['total_deals']}")
    print(f"    Конверсия: {funnel['conversion_rate']}%")
    print(f"    Pipeline: {funnel['pipeline_value']:,.0f} ₽")
    
    # 2. Call records
    print(f"\n  📞 Анализ звонков...")
    calls = get_call_records(days=30, limit=limit)
    
    for call in calls:
        call_id = call.get("ID", "")
        duration = call.get("CALL_DURATION", 0)
        phone = call.get("PHONE_NUMBER", "")
        status = call.get("CALL_FAILED_CODE", "200")
        
        print(f"    #{call_id}: {phone} ({duration}с) — {'✅' if status == '200' else '❌'}")
        
        # Get transcript from recording if available
        audio_url = get_call_audio_url(call_id)
        if audio_url:
            print(f"      🎤 Запись: {audio_url[:60]}...")
            # Note: full audio analysis requires downloading + Gemini multimodal
    
    # 3. Text activities
    print(f"\n  📧 Анализ активностей...")
    activities = analyze_text_messages(days=30)
    
    # Summary
    print(f"\n{'='*70}")
    print(f"  📊 ИТОГИ CRM АНАЛИТИКИ")
    print(f"{'='*70}")
    print(f"  Лидов в CRM:      {funnel['total_leads']}")
    print(f"  Сделок:            {funnel['total_deals']}")
    print(f"  Конверсия:         {funnel['conversion_rate']}%")
    print(f"  Pipeline:          {funnel['pipeline_value']:,.0f} ₽")
    print(f"  Звонков найдено:   {len(calls)}")
    print(f"  Email активностей: {len(activities)}")
    print(f"{'='*70}")
    
    return {
        "funnel": funnel,
        "calls_count": len(calls),
        "activities_count": len(activities),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CRM Call & Activity Analyzer")
    parser.add_argument("--limit", type=int, default=10, help="Number of calls to analyze")
    args = parser.parse_args()
    
    run_analysis(limit=args.limit)
