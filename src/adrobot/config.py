from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: PostgresDsn
    keitaro_url: AnyHttpUrl
    keitaro_api_key: SecretStr
    keitaro_timezone: str = 'Europe/Minsk'
    campaign_prefix: str = Field(
        default='test_kryvanos_',
        pattern=r'^test_[a-z0-9]{1,30}_$',
    )

    @property
    def keitaro_origin(self) -> str:
        return str(self.keitaro_url).rstrip('/')

    @field_validator('keitaro_url')
    @classmethod
    def validate_tracker_url(cls, url: AnyHttpUrl) -> AnyHttpUrl:
        if (
            url.scheme != 'https'
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ('', '/', None)
        ):
            raise ValueError('Use the HTTPS origin of the tracker.')
        return url

    @field_validator('keitaro_api_key')
    @classmethod
    def validate_tracker_key(cls, key: SecretStr) -> SecretStr:
        if not key.get_secret_value().strip():
            raise ValueError('Keitaro API key is required.')
        return key

    @field_validator('keitaro_timezone')
    @classmethod
    def validate_timezone(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except ValueError, ZoneInfoNotFoundError:
            raise ValueError('Use a valid IANA timezone.') from None
        return timezone
