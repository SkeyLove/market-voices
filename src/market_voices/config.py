import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from pydantic import Field, SecretStr
from .contracts import Model, url


class Rates(Model):
    # Explicit current provider prices are required before any paid call.
    input_per_million: float = Field(gt=0)
    output_per_million: float = Field(gt=0)
    currency_to_cny: float = Field(gt=0)
    verified_on: str


class Settings(Model):
    provider: str = 'deepseek'
    base_url: str = 'https://api.deepseek.com'
    model: str = 'deepseek-flash'
    api_key: SecretStr = Field(default=SecretStr(''),exclude=True,repr=False)
    monthly_cap_cny: float = Field(default=30,gt=0,le=30)
    rates: Rates | None = None
    allowed_tickers: list[str] = []
    daily_limit: int = Field(default=12,ge=1,le=100)


def path():
    override=os.environ.get('MARKET_VOICES_CONFIG')
    if override:
        return Path(override).expanduser()
    base=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    if sys.platform=='darwin' and 'XDG_CONFIG_HOME' not in os.environ:
        base=Path.home()/'Library/Application Support'
    return base/'market-voices/model.json'


def settings():
    p=path()
    try:
        data=json.loads(p.read_text()) if p.exists() else {}
        for key in ('api_key','base_url','model','provider'):
            env=os.environ.get('MARKET_VOICES_'+key.upper())
            if env is not None:
                data[key]=env
        result=Settings.model_validate(data)
        if result.provider not in ('deepseek','compatible','ollama'):
            raise ValueError('provider_not_supported')
        if result.provider=='ollama':
            if result.base_url!='http://127.0.0.1:11434/v1':
                raise ValueError('ollama_endpoint_invalid')
        else:
            url(result.base_url)
            p=urlsplit(result.base_url)
            if p.query or p.fragment:
                raise ValueError('base_url_invalid')
        return result
    except Exception:
        raise ValueError('invalid_model_config') from None
