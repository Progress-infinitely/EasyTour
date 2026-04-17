from __future__ import annotations

from dataclasses import asdict, dataclass
import re


_CITY_TO_PROVINCE = {
    '三亚': '海南',
    '海口': '海南',
    '琼海': '海南',
    '文昌': '海南',
    '北京': '北京',
    '上海': '上海',
    '天津': '天津',
    '重庆': '重庆',
    '广州': '广东',
    '深圳': '广东',
    '珠海': '广东',
    '杭州': '浙江',
    '宁波': '浙江',
    '成都': '四川',
    '西安': '陕西',
    '昆明': '云南',
    '大理': '云南',
    '丽江': '云南',
    '厦门': '福建',
    '福州': '福建',
    '南京': '江苏',
    '苏州': '江苏',
    '青岛': '山东',
    '桂林': '广西',
    '拉萨': '西藏',
    '乌鲁木齐': '新疆',
    '长沙': '湖南',
    '武汉': '湖北',
}

_MUNICIPALITIES = {'北京', '上海', '天津', '重庆'}
_KNOWN_CITIES = sorted(_CITY_TO_PROVINCE.keys(), key=len, reverse=True)
_KNOWN_PROVINCES = sorted({*_CITY_TO_PROVINCE.values(), *_MUNICIPALITIES}, key=len, reverse=True)

_PROVINCE_SUFFIXES = ('省', '自治区', '特别行政区', '壮族自治区', '回族自治区', '维吾尔自治区')
_CITY_SUFFIXES = ('市', '州', '地区', '盟', '县')


@dataclass(slots=True)
class RegionInfo:
    raw: str = ''
    province: str = ''
    city: str = ''
    region_path: str = ''

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _strip_suffix(value: str, suffixes: tuple[str, ...]) -> str:
    result = value.strip()
    for suffix in suffixes:
        if result.endswith(suffix):
            return result[: -len(suffix)]
    return result


def _normalize_token(token: str) -> str:
    return re.sub(r'[\s/\\>\-|]+', '', token or '').strip()


def _pick_known_region_token(tokens: list[str], names: list[str], suffixes: tuple[str, ...]) -> str:
    for token in tokens:
        normalized = _strip_suffix(token, suffixes)
        if normalized in names:
            return normalized
    return ''


def _find_known_region_name(text: str, names: list[str]) -> str:
    for name in names:
        if name and name in text:
            return name
    return ''


def normalize_region(region_text: str | None) -> RegionInfo:
    text = (region_text or '').strip()
    if not text:
        return RegionInfo()

    cleaned = text.replace('，', '/').replace(',', '/').replace('>', '/').replace(' - ', '/')
    # [修改] LLM 常把 province/city/region_path 用空格拼起来，这里统一按空白和分隔符切 token。
    tokens = [_normalize_token(token) for token in re.split(r'[/\s]+', cleaned) if _normalize_token(token)]

    city = _pick_known_region_token(tokens, _KNOWN_CITIES, _CITY_SUFFIXES)
    province = _pick_known_region_token(tokens, _KNOWN_PROVINCES, _PROVINCE_SUFFIXES)

    if not city:
        city = _find_known_region_name(text, _KNOWN_CITIES)
    if not province:
        province = _find_known_region_name(text, _KNOWN_PROVINCES)

    if city and not province:
        province = _CITY_TO_PROVINCE.get(city, '')
    if province in _MUNICIPALITIES and not city:
        city = province

    if province and city and province == city:
        region_parts = [province]
    else:
        region_parts = [part for part in (province, city) if part]
    region_path = '/'.join(region_parts)
    if not region_path:
        region_path = text

    return RegionInfo(raw=text, province=province, city=city, region_path=region_path)


def infer_region(region_text: str | None, fallback_text: str | None = None) -> RegionInfo:
    primary = normalize_region(region_text)
    if primary.region_path:
        return primary
    return normalize_region(fallback_text)
