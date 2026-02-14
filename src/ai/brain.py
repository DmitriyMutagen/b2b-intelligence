"""
AI Brain — Lead analysis, pain point identification, approach strategy generation.
Uses OpenAI GPT-4o for analysis.
"""
import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Lazy import — only load openai when actually calling
_client = None


def get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def load_company_profile():
    """Load our company profile for context."""
    profile_path = os.path.join(os.path.dirname(__file__), "..", "data", "company_profile.json")
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"company_name": "Bio Innovations", "industry": "Contract Manufacturing"}


# ─── System Prompt ───
SYSTEM_PROMPT = """Ты — AI-аналитик в компании контрактного производства спортивного питания и БАДов.

КОНТЕКСТ НАШЕЙ КОМПАНИИ:
{company_context}

Твоя задача — анализировать потенциальных клиентов (B2B) и помогать продавцам:
1. Определять боли и потребности клиента
2. Генерировать стратегии подхода
3. Оценивать лиды по перспективности
4. Создавать персонализированные скрипты продаж

Отвечай всегда на русском языке. Будь конкретным, избегай шаблонных фраз.
"""


def analyze_lead(company_data: dict, crawl_data: dict = None, bitrix_data: dict = None) -> dict:
    """
    Full lead analysis: pain points, approach strategy, brand DNA, lead score.

    Args:
        company_data: Company record from our DB
        crawl_data: Web crawler results (emails, phones, socials)
        bitrix_data: CRM history (previous deals, interactions)

    Returns:
        dict with pain_points, approach_strategy, brand_dna, lead_score, call_script
    """
    profile = load_company_profile()
    system = SYSTEM_PROMPT.format(company_context=json.dumps(profile, ensure_ascii=False, indent=2))

    # Build analysis prompt
    info_parts = [f"**Компания:** {company_data.get('name', 'Unknown')}"]

    if company_data.get('legal_form'):
        info_parts.append(f"**Форма:** {company_data['legal_form']}")
    if company_data.get('revenue_total'):
        info_parts.append(f"**Выручка:** {company_data['revenue_total']:,.0f} ₽")
    if company_data.get('sales_total'):
        info_parts.append(f"**Продажи:** {company_data['sales_total']:,.0f} шт")
    if company_data.get('wb_present'):
        info_parts.append("**Wildberries:** Присутствует")
    if company_data.get('ozon_present'):
        info_parts.append("**Ozon:** Присутствует")
    if company_data.get('website'):
        info_parts.append(f"**Сайт:** {company_data['website']}")

    if crawl_data:
        if crawl_data.get('description'):
            info_parts.append(f"**Описание с сайта:** {crawl_data['description']}")
        if crawl_data.get('emails'):
            info_parts.append(f"**Email:** {', '.join(crawl_data['emails'][:3])}")
        if crawl_data.get('social_links'):
            info_parts.append(f"**Соцсети:** {json.dumps(crawl_data['social_links'], ensure_ascii=False)}")

    if bitrix_data:
        if bitrix_data.get('deals_count'):
            info_parts.append(f"**Сделок в CRM:** {bitrix_data['deals_count']}")
        if bitrix_data.get('last_interaction'):
            info_parts.append(f"**Последнее касание:** {bitrix_data['last_interaction']}")

    company_info = "\n".join(info_parts)

    user_prompt = f"""Проанализируй потенциального клиента для контрактного производства:

{company_info}

Ответь строго в JSON формате:
{{
    "pain_points": ["боль 1", "боль 2", "боль 3"],
    "brand_dna": {{
        "positioning": "как позиционируется бренд",
        "target_audience": "целевая аудитория",
        "price_segment": "эконом/средний/премиум",
        "strengths": ["сильная сторона 1", "сильная сторона 2"],
        "weaknesses": ["слабость 1", "слабость 2"]
    }},
    "approach_strategy": "конкретная стратегия подхода к этому клиенту (2-3 предложения)",
    "lead_score": 0-100,
    "lead_score_reasoning": "почему такая оценка",
    "call_script_opener": "первая фраза для звонка, персонализированная под этого клиента",
    "email_subject": "тема персонализированного email для этого клиента",
    "recommended_products": ["продукт 1 для предложения", "продукт 2"],
    "deal_potential_rub": 0
}}"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        result = json.loads(content)

        # Ensure lead_score is integer
        result["lead_score"] = int(result.get("lead_score", 0))

        return result

    except Exception as e:
        print(f"AI analysis error: {e}")
        return {
            "pain_points": [],
            "brand_dna": {},
            "approach_strategy": f"Error: {str(e)}",
            "lead_score": 0,
            "error": str(e)
        }


def calculate_lead_score(company: dict) -> int:
    """
    Rule-based lead score (0-100) when AI is not available.
    Factors: revenue, marketplace presence, sales volume, avg price.
    """
    score = 0

    # Revenue factor (0-30)
    rev = company.get('revenue_total') or 0
    if rev > 100_000_000:
        score += 30
    elif rev > 50_000_000:
        score += 25
    elif rev > 10_000_000:
        score += 20
    elif rev > 1_000_000:
        score += 10

    # Marketplace presence (0-20)
    if company.get('wb_present') and company.get('ozon_present'):
        score += 20
    elif company.get('wb_present') or company.get('ozon_present'):
        score += 12

    # Sales volume (0-20)
    sales = company.get('sales_total') or 0
    if sales > 100_000:
        score += 20
    elif sales > 50_000:
        score += 15
    elif sales > 10_000:
        score += 10
    elif sales > 1_000:
        score += 5

    # Average price indicates premium segment (0-15)
    avg = company.get('avg_price') or 0
    if avg > 2000:
        score += 15
    elif avg > 1000:
        score += 10
    elif avg > 500:
        score += 5

    # Has website (0-10)
    if company.get('website'):
        score += 10

    # Has contacts (0-5)
    if company.get('contacts_count', 0) > 0:
        score += 5

    return min(score, 100)


def generate_call_script(company_name: str, pain_points: list, approach: str) -> str:
    """Generate a quick call script without AI (template-based)."""
    pains = ", ".join(pain_points[:2]) if pain_points else "развитие ассортимента"
    return f"""
📞 СКРИПТ ЗВОНКА — {company_name}

1. ОТКРЫТИЕ:
   «Добрый день! Меня зовут [Имя], компания Bio Innovations — контрактное производство
   спортивного питания и БАДов. Мы видим, что {company_name} активно развивается
   на маркетплейсах, и у нас есть решение, которое поможет с {pains}.»

2. КВАЛИФИКАЦИЯ:
   - Вы сейчас производите сами или через контрактное производство?
   - Какие категории продукции для вас приоритетны?
   - Какой объём вам интересен?

3. ЦЕННОСТЬ:
   «{approach}»

4. ЗАКРЫТИЕ:
   «Давайте я пришлю вам каталог наших формул и примеры успешных кейсов?
   Когда вам удобно обсудить детали?»
"""


# ─── Quick test ───
if __name__ == "__main__":
    # Test rule-based scoring
    test = {
        "name": "Бомббар",
        "revenue_total": 483602176,
        "sales_total": 459864,
        "wb_present": True,
        "ozon_present": True,
        "avg_price": 1050,
    }
    score = calculate_lead_score(test)
    print(f"Lead Score for {test['name']}: {score}/100")

    script = generate_call_script(test["name"], ["масштабирование", "качество ингредиентов"], "Мы можем предложить готовые формулы из каталога 150+ рецептур")
    print(script)
