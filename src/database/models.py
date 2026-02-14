"""
═══════════════════════════════════════════════════════════════════
  B2B Intelligence Platform — Database Models
  Интеллектуальная собственность АО «Арагант Групп»
  Copyright (c) 2024-2026 АО «Арагант Групп». Все права защищены.
═══════════════════════════════════════════════════════════════════
"""
"""
Database models for B2B Intelligence Platform.
Uses SQLAlchemy ORM with async support.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, ForeignKey, 
    DateTime, JSON, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Company(Base):
    """Core entity — a seller/brand from STM Master or marketplace bases."""
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True)
    
    # From STM Master
    key = Column(String, unique=True, index=True)  # Slug from Excel e.g. 'primekraft'
    name = Column(String, index=True)               # Company name
    legal_form = Column(String)                      # OOO, IP, etc.
    inn = Column(String, index=True, nullable=True)
    
    # Marketplace presence
    wb_present = Column(Boolean, default=False)
    ozon_present = Column(Boolean, default=False)
    wb_brand_link = Column(String, nullable=True)
    ozon_brand_link = Column(String, nullable=True)
    
    # Financial (from STM file)
    revenue_total = Column(Float, nullable=True)
    sales_total = Column(Float, nullable=True)
    avg_price = Column(Float, nullable=True)
    
    # Enrichment
    website = Column(String, nullable=True)
    enrichment_status = Column(String, default='new')  # new, in_progress, enriched, failed
    lead_score = Column(Integer, default=0)  # 0-100
    
    # Metadata
    source_file = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    persons = relationship("Person", back_populates="company", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    intelligence = relationship("Intelligence", back_populates="company", uselist=False, cascade="all, delete-orphan")
    interactions = relationship("Interaction", back_populates="company")


class Person(Base):
    """LPR (decision maker), HR contact, etc."""
    __tablename__ = 'persons'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    
    full_name = Column(String)
    role = Column(String)  # CEO, Sales Manager, HR, Founder
    
    # From STM Master 'Names' column (may contain multiple names)
    source = Column(String)  # stm_file, rusprofile, telegram, hh_ru
    
    company = relationship("Company", back_populates="persons")
    contacts = relationship("PersonContact", back_populates="person", cascade="all, delete-orphan")


class PersonContact(Base):
    """Contact details for a specific person."""
    __tablename__ = 'person_contacts'

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('persons.id'))
    
    type = Column(String)   # phone, email, telegram, whatsapp, vk
    value = Column(String)
    is_verified = Column(Boolean, default=False)
    
    person = relationship("Person", back_populates="contacts")


class Contact(Base):
    """Company-level contacts (not tied to a specific person)."""
    __tablename__ = 'contacts'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    
    type = Column(String)   # phone, email, website, telegram_channel, vk_group, address
    value = Column(String)
    label = Column(String, nullable=True)  # "Главный офис", "Склад"
    source = Column(String)  # stm_file, 2gis, yandex_maps, web_crawl, whois
    is_verified = Column(Boolean, default=False)
    
    company = relationship("Company", back_populates="contacts")


class Intelligence(Base):
    """AI-generated intelligence for a company."""
    __tablename__ = 'intelligence'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), unique=True)
    
    # Brand analysis
    brand_dna = Column(JSON, nullable=True)       # {tone: "formal", values: [...]}
    pain_points = Column(JSON, nullable=True)      # ["bad packaging", "weak taste"]
    competitor_intel = Column(JSON, nullable=True)  # Who is their current manufacturer?
    
    # AI recommendations
    approach_strategy = Column(Text, nullable=True)  # How to approach this lead
    call_script = Column(Text, nullable=True)        # Generated call script
    proposal_draft = Column(Text, nullable=True)     # KP text draft
    
    # Scoring details
    score_breakdown = Column(JSON, nullable=True)  # {revenue: 30, alive: 20, ...}
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    company = relationship("Company", back_populates="intelligence")


class Interaction(Base):
    """Log of all interactions with a company."""
    __tablename__ = 'interactions'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    
    type = Column(String)     # call, email, telegram_msg, whatsapp_msg, proposal_sent
    direction = Column(String)  # inbound, outbound
    status = Column(String)   # sent, delivered, opened, replied, no_answer
    
    content_summary = Column(Text, nullable=True)
    ai_analysis = Column(JSON, nullable=True)  # Transcription + objections
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="interactions")


class Document(Base):
    """Uploaded documents (КП, спецификации, договоры) for RAG knowledge base."""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True)
    
    filename = Column(String)
    doc_type = Column(String)  # kp_template, specification, contract, price_list, presentation
    content_text = Column(Text)  # Extracted text for search/RAG
    content_embedding = Column(JSON, nullable=True)  # Vector embedding for semantic search
    
    doc_metadata = Column(JSON, nullable=True)  # {pages: 5, format: "pdf", ...}
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)
