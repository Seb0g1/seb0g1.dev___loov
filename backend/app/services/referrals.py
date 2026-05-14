from __future__ import annotations

from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl


def add_utm(url: str, params: dict[str, str | None]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    for key, value in params.items():
        if value:
            query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_affiliate_url(template_url: str, product_url: str, source: str, extra: dict[str, str | None] | None = None) -> str:
    data = {
        "url": product_url,
        "source": source,
    }
    if extra:
        data.update(extra)
    return add_utm(template_url.format(**data), {k: v for k, v in data.items() if k.startswith("utm_")})

