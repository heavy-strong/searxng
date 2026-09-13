# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=line-too-long
"""Naver for SearXNG"""

import re
import typing as t

from urllib.parse import urlencode, urlparse, parse_qs
from lxml import html

from searx.exceptions import SearxEngineAPIException, SearxEngineXPathException
from searx.result_types import EngineResults, MainResult
from searx.utils import (
    eval_xpath_getindex,
    eval_xpath_list,
    eval_xpath,
    extract_text,
    html_to_text,
    parse_duration_string,
    js_obj_str_to_python,
)

# engine metadata
about = {
    "website": "https://search.naver.com",
    "wikidata_id": "Q485639",
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}
language = "ko"

categories = []
paging = True

time_range_support = True
time_range_dict = {"day": "1d", "week": "1w", "month": "1m", "year": "1y"}

base_url = "https://search.naver.com"

naver_category = "general"
"""Naver supports general, images, news, videos search.

- ``general``: search for general
- ``images``: search for images
- ``news``: search for news
- ``videos``: search for videos
"""

# Naver cannot set the number of results on one page, set default value for paging
naver_category_dict = {
    "general": {
        "start": 15,
        "where": "web",
    },
    "images": {
        "start": 50,
        "where": "image",
    },
    "news": {
        "start": 10,
        "where": "news",
    },
    "videos": {
        "start": 48,
        "where": "video",
    },
}


def setup(_: dict[str, t.Any]) -> bool | None:
    if naver_category not in ('general', 'images', 'news', 'videos'):
        raise SearxEngineAPIException(f"Unsupported category: {naver_category}")


def request(query, params):
    query_params = {
        "query": query,
    }

    if naver_category in naver_category_dict:
        query_params["start"] = (params["pageno"] - 1) * naver_category_dict[naver_category]["start"] + 1
        query_params["where"] = naver_category_dict[naver_category]["where"]

    if params["time_range"] in time_range_dict:
        query_params["nso"] = f"p:{time_range_dict[params['time_range']]}"

    params["url"] = f"{base_url}/search.naver?{urlencode(query_params)}"
    return params


def response(resp) -> EngineResults:
    parsers = {'general': parse_general, 'images': parse_images, 'news': parse_news, 'videos': parse_videos}

    return parsers[naver_category](resp.text)


def parse_general(data):
    results = EngineResults()

    dom = html.fromstring(data)

    for item in eval_xpath_list(dom, "//div[contains(@class, 'fds-web-normal-doc-root')]"):
        thumbnail = extract_text(
            eval_xpath(
                item,
                ".//div[contains(@class, 'sds-comps-image') and not(contains(@class, 'sds-comps-image-circle'))]/img/@src",
            )
        )

        title = extract_text(eval_xpath(item, ".//span[contains(@class, 'sds-comps-text-type-headline1')]"))

        url = None
        try:
            url = eval_xpath_getindex(
                item, ".//a[starts-with(@href, 'http') and not(contains(@href, 'keep.naver.com'))]/@href", 0
            )
        except (ValueError, TypeError, SearxEngineXPathException):
            pass

        content = extract_text(eval_xpath(item, ".//span[contains(@class, 'sds-comps-text-type-body1')]"))

        if title and url:
            results.add(
                MainResult(
                    title=title,
                    url=url,
                    content=content or "",
                    thumbnail=thumbnail or "",
                )
            )

    return results


def parse_images(data):
    results = []

    # The data object is embedded as ``var imageSearchTabData = {...}`` inside a
    # <script> tag whose attributes / whitespace vary, so anchor on the variable.
    match = None
    var_match = re.search(r'var\s+imageSearchTabData\s*=\s*', data)
    if var_match:
        match = data[var_match.end() :].split('</script>', 1)[0].strip().rstrip(';')

    if match:
        json = js_obj_str_to_python(match.strip())
        items = json.get('content', {}).get('items', [])

        for item in items:
            results.append(
                {
                    "template": "images.html",
                    "url": item.get('link'),
                    "thumbnail_src": item.get('thumb'),
                    "img_src": item.get('originalUrl'),
                    "title": html_to_text(item.get('title')),
                    "source": item.get('source'),
                    "resolution": f"{item.get('orgWidth')} x {item.get('orgHeight')}",
                }
            )

    return results


def parse_news(data):
    results = EngineResults()
    dom = html.fromstring(data)

    for item in eval_xpath_list(
        dom, "//div[contains(@class, 'sds-comps-base-layout') and contains(@class, 'sds-comps-full-layout')]"
    ):
        title = extract_text(eval_xpath(item, ".//span[contains(@class, 'sds-comps-text-type-headline1')]/text()"))

        url = eval_xpath_getindex(item, ".//a[@href and @nocr='1']/@href", 0)

        content = extract_text(eval_xpath(item, ".//span[contains(@class, 'sds-comps-text-type-body1')]"))

        thumbnail = None
        try:
            thumbnail = eval_xpath_getindex(
                item,
                ".//div[contains(@class, 'sds-comps-image') and contains(@class, 'sds-rego-thumb-overlay')]//img[@src]/@src",
                0,
            )
        except (ValueError, TypeError, SearxEngineXPathException):
            pass

        if title and content and url:
            results.add(
                MainResult(
                    title=title,
                    url=url,
                    content=content,
                    thumbnail=thumbnail or "",
                )
            )

    return results


def _youtube_embed_url(url: str) -> str | None:
    """Return an embeddable player URL when ``url`` points at a YouTube video."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()
    video_id = None

    if host in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/")):
            video_id = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else None
    elif host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0] or None

    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return f"https://www.youtube.com/embed/{video_id}"

    return None


def parse_videos(data):
    res = EngineResults()

    dom = html.fromstring(data)

    # Each result is a container holding a thumbnail link
    # (``fds-video-thumbnail-size``) and a title block
    # (``fds-video-title-with-profile``).
    for title_block in eval_xpath_list(dom, "//div[contains(@class, 'fds-video-title-with-profile')]"):
        item = title_block.getparent()
        if item is None:
            continue

        url = None
        try:
            url = eval_xpath_getindex(title_block, ".//a[starts-with(@href, 'http')]/@href", 0)
        except (ValueError, TypeError, SearxEngineXPathException):
            pass

        title = extract_text(eval_xpath(title_block, ".//span[contains(@class, 'sds-comps-text-type-headline')]"))

        if not url or not title:
            continue

        thumbnail = None
        try:
            thumbnail = eval_xpath_getindex(
                item, ".//a[contains(@class, 'fds-video-thumbnail-size')]//img[@src]/@src", 0
            )
        except (ValueError, TypeError, SearxEngineXPathException):
            pass

        length = None
        try:
            length = parse_duration_string(
                extract_text(
                    eval_xpath(
                        item,
                        ".//a[contains(@class, 'fds-video-thumbnail-size')]//span[contains(@class, 'sds-comps-text-type-footnote')]",
                    )
                )
                or ""
            )
        except (ValueError, TypeError):
            pass

        # channel / uploader name; direct text only to skip the "opens in new
        # window" screen-reader hint nested in the link
        content = extract_text(
            eval_xpath(
                title_block,
                "(.//span[contains(@class, 'sds-comps-profile-info-title-text')]//a/span[contains(@class, 'sds-comps-text-type')])[1]",
            )
        )

        result = {
            "template": "videos.html",
            "title": title,
            "url": url,
            "content": content or "",
            "thumbnail": thumbnail,
            "length": length,
        }

        iframe_src = _youtube_embed_url(url)
        if iframe_src:
            result["iframe_src"] = iframe_src

        res.add(res.types.LegacyResult(**result))

    return res
