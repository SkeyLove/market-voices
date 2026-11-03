"""Shared interchange contract for CLI, API and Codex-assisted production."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROMPT_VERSION = 'voices-summary.v1'
Category = Literal['creator','professional','institution','official','academic']
Stance = Literal['bullish','neutral','bearish','conditional','unclear']


def timestamp():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def normalized(text):
    return ' '.join(re.sub(r'\[\d+(?:\.\d+)?s\]', ' ', text).split())


def url(value):
    p=urlsplit(value)
    if (p.scheme!='https' or not p.hostname or '.' not in p.hostname or p.username or p.password
        or p.port not in (None,443) or '\\' in value or any(ord(c)<33 for c in value)
        or p.hostname.endswith(('.local','.localhost','.internal'))):
        raise ValueError('public_https_required')
    try:
        if not ip_address(p.hostname).is_global:
            raise ValueError('public_address_required')
    except ValueError as exc:
        if str(exc)=='public_address_required':
            raise
    return value


class Model(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)


class Source(Model):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,79}$')
    speaker_id: str = Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,79}$')
    speaker: str = Field(min_length=1,max_length=120)
    group: str = Field(min_length=1,max_length=80)
    category: Category
    identity_url: str
    feed_url: str = ''
    platform: Literal['official','youtube','x'] = 'official'
    verified: bool = False
    rights: Literal['pending','summary_link_only','licensed'] = 'pending'
    _identity=field_validator('identity_url')(url)

    @field_validator('feed_url')
    @classmethod
    def feed(cls, value):
        return url(value) if value else value


class Raw(Model):
    source_id: str
    url: str
    title: str = Field(min_length=1,max_length=600)
    published: datetime
    collected: datetime = Field(default_factory=lambda:datetime.now(UTC))
    text: str = Field(min_length=1,max_length=100000)
    evidence: Literal['full_text','transcript','official_text','feed_excerpt','summary_only','title_only','unavailable']
    locator: str = Field(default='',max_length=500)
    _url=field_validator('url')(url)

    @field_validator('published','collected')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:
            raise ValueError('timezone_required')
        return value.astimezone(UTC)

    @property
    def fingerprint(self):
        return digest({'raw':self.model_dump(mode='json'),'prompt':PROMPT_VERSION})


class Summary(Model):
    title_zh: str = Field(min_length=1,max_length=240)
    title_en: str = Field(min_length=1,max_length=300)
    summary_zh: str = Field(min_length=1,max_length=600)
    summary_en: str = Field(min_length=1,max_length=1000)
    speaker_id: str
    ticker: str = Field(default='',pattern=r'^$|^[A-Z][A-Z.-]{0,11}$')
    stance: Stance = 'unclear'
    horizon: Literal['unspecified','short_term','long_term'] = 'unspecified'
    quote: str = Field(default='',max_length=500)
    conditions_zh: str = Field(default='',max_length=500)
    conditions_en: str = Field(default='',max_length=700)
    input_hash: str
    method: Literal['api','skill','demo']
    producer: str
    prompt_version: str = PROMPT_VERSION
    generated_at: datetime = Field(default_factory=lambda:datetime.now(UTC))

    @field_validator('generated_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:
            raise ValueError('timezone_required')
        return value.astimezone(UTC)


def issues(raw: Raw, summary: Summary, source: Source):
    errors=[]
    if raw.source_id!=source.id or summary.speaker_id!=source.speaker_id:
        errors.append('speaker_mismatch')
    if summary.input_hash!=raw.fingerprint or summary.prompt_version!=PROMPT_VERSION:
        errors.append('stale_summary')
    if raw.evidence not in ('full_text','transcript','official_text'):
        errors.append('insufficient_evidence')
    if not raw.locator:
        errors.append('missing_locator')
    if not source.verified or source.rights=='pending':
        errors.append('source_not_cleared')
    if raw.published>datetime.now(UTC):
        errors.append('future_publication')
    if len(summary.quote.strip())<20 or normalized(summary.quote) not in normalized(raw.text):
        errors.append('quote_not_supported')
    if source.category=='official' and summary.ticker:
        errors.append('official_stock_call')
    if bool(summary.conditions_zh)!=bool(summary.conditions_en):
        errors.append('conditions_translation_missing')
    if summary.stance=='conditional' and not summary.conditions_zh:
        errors.append('missing_conditions')
    return errors
