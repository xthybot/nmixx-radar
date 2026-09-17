from app.runtime_data import RuntimeDataStore
from app.url_policy import is_allowed_external_url


def _merge_unique_updates(generated_updates, manual_updates):
    seen = set()
    merged = []
    for item in [*generated_updates, *manual_updates]:
        key = (item.get("href", "").strip(), item.get("title", "").strip())
        if key in seen or not is_allowed_external_url(key[0]):
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _current_hero_slides(runtime_data: RuntimeDataStore | None) -> list[dict[str, str]]:
    if runtime_data:
        generated = runtime_data.read_hero_slides()
        if generated:
            return generated
    return HERO_SLIDES


OFFICIAL_LINKS = {
    "home": "https://nmixx.jype.com/",
    "notice": "https://nmixx.jype.com/Mobile/NoticeList",
    "caution": "https://nmixx.jype.com/Mobile/NoticeView?AnSeq=6992&NoticeNumber=547",
    "heavy_serenade": "https://nmixx.jype.com/Mobile/NoticeView?AnSeq=6977&NoticeNumber=545",
    "heavy_serenade_video": "https://nmixx.jype.com/Mobile/NoticeView?AnSeq=6976&NoticeNumber=544",
    "crescendo": "https://nmixx.jype.com/Mobile/NoticeView?AnSeq=6956&NoticeNumber=540",
    "concept": "https://nmixx.jype.com/Mobile/NoticeView?NoticeNumber=538&AnSeq=6947",
    "discography": "https://nmixx.jype.com/Mobile/DiscographyList",
    "schedule": "https://nmixx.jype.com/Mobile/Schedule",
    "instagram": "https://www.instagram.com/nmixx_official/",
    "youtube": "https://www.youtube.com/@NMIXXOfficial",
    "video": "https://www.youtube.com/watch?v=GrrMUB9D12g",
}

IMAGES = {
    "hero": "https://d1al7qj7ydfbpt.cloudfront.net/artist/bbs/16d13b7375e6482f850e9c586a9fd6e4-700%29unit_01.jpg",
    "concept": "https://d1al7qj7ydfbpt.cloudfront.net/artist/bbs/7a25046ea30a45d385a30ed545407a80-700%29unit_04.jpg",
    "schedule": "https://d1al7qj7ydfbpt.cloudfront.net/general/1776132736772-92d9e2d3.jpg",
    "video": "https://i.ytimg.com/vi/GrrMUB9D12g/maxresdefault.jpg",
}

HERO_SLIDES = [
    {
        "src": IMAGES["hero"],
        "alt": "NMIXX 官方概念照 1",
        "label": "Fe3O4: FORWARD · 單位照 01",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artist/bbs/e5312a89d15f44ea97d43783643e3f73-700%29unit_02.jpg",
        "alt": "NMIXX 官方概念照 2",
        "label": "Fe3O4: FORWARD · 單位照 02",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artist/bbs/b5406941b66e438e992812cb8c6370ae-700%29unit_03.jpg",
        "alt": "NMIXX 官方概念照 3",
        "label": "Fe3O4: FORWARD · 單位照 03",
        "source": "JYP 娛樂官方",
    },
    {
        "src": IMAGES["concept"],
        "alt": "NMIXX 官方概念照 4",
        "label": "Fe3O4: FORWARD · 單位照 04",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/main/1776134952606-f2eeafae.png",
        "alt": "NMIXX 官方主視覺 5",
        "label": "官方主視覺",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/main/1776135065292-4f0ab68d.png",
        "alt": "NMIXX 官方主視覺 6",
        "label": "官方主視覺",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/main/1777042896365-28cdd51f.jpg",
        "alt": "NMIXX 官方照片 7",
        "label": "官方照片",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/main/1777042900671-548c2315.jpg",
        "alt": "NMIXX 官方照片 8",
        "label": "官方照片",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/main/1776135025649-2efcba36.jpg",
        "alt": "NMIXX 官方照片 9",
        "label": "官方照片",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/main/1777042397740-5e1cd1c8.jpg",
        "alt": "NMIXX 官方照片 10",
        "label": "官方照片",
        "source": "JYP 娛樂官方",
    },
    {
        "src": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/albums/1778468916611-2fcfcbe5.jpg",
        "alt": "NMIXX 官方專輯照片 11",
        "label": "官方專輯照片",
        "source": "JYP 娛樂官方",
    },
]

UPDATES = [
    {
        "tag": "公告",
        "title": "NMIXX, Anderson .Paak <Caution> 發布案內",
        "meta": "2026.05.29 · JYP 官方",
        "href": OFFICIAL_LINKS["caution"],
        "tone": "lime",
    },
    {
        "tag": "發行",
        "title": "NMIXX 5th EP <Heavy Serenade> 發售",
        "meta": "2026.05.11 · JYP 官方",
        "href": OFFICIAL_LINKS["heavy_serenade"],
        "tone": "blue",
    },
    {
        "tag": "影片",
        "title": "Heavy Serenade 官方 M/V",
        "meta": "2026.05.11 · NMIXX 官方",
        "href": OFFICIAL_LINKS["heavy_serenade_video"],
        "tone": "white",
    },
    {
        "tag": "MV",
        "title": "Crescendo 官方 M/V",
        "meta": "2026.04.28 · NMIXX 官方",
        "href": OFFICIAL_LINKS["crescendo"],
        "tone": "pink",
    },
]

SCHEDULE = [
    ("05.29", "Caution 發布案內"),
    ("05.26", "KYUJIN 生日"),
    ("05.11", "Heavy Serenade 發售"),
    ("05.11", "Heavy Serenade 音樂錄影帶"),
    ("05.10", "Heavy Serenade 音樂錄影帶預告"),
]

RELEASES = [
    {
        "title": "Heavy Serenade",
        "date": "2026.05.11",
        "type": "第 5 張迷你專輯",
        "href": OFFICIAL_LINKS["heavy_serenade"],
    },
    {
        "title": "Blue Valentine (MIXX Ver.)",
        "date": "2025.10.17",
        "type": "單曲",
        "href": OFFICIAL_LINKS["discography"],
    },
    {
        "title": "Blue Valentine",
        "date": "2025.10.13",
        "type": "單曲",
        "href": OFFICIAL_LINKS["discography"],
    },
    {
        "title": "Fe3O4: FORWARD",
        "date": "2025.03.17",
        "type": "迷你專輯",
        "href": OFFICIAL_LINKS["discography"],
    },
]

MEMBERS = [
    {
        "name": "LILY",
        "title": "核心主唱",
        "intro": "聲線辨識度高，負責撐起歌曲裡最有爆發力的段落。",
        "focus": "主唱",
        "photo": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/profiles/1777042449390-f77243f7.jpg",
    },
    {
        "name": "HAEWON",
        "title": "隊長／主唱",
        "intro": "穩定掌握舞台節奏，也是團體訪談與現場互動的重心。",
        "focus": "隊長",
        "photo": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/profiles/1777042456467-3b884da3.jpg",
    },
    {
        "name": "SULLYOON",
        "title": "主唱／門面",
        "intro": "清亮音色與乾淨視覺風格突出，適合概念照與鏡頭焦點。",
        "focus": "門面",
        "photo": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/profiles/1777042462763-be9288ce.jpg",
    },
    {
        "name": "BAE",
        "title": "主唱／表演",
        "intro": "舞台表情自然，能把活潑能量帶進團體表演裡。",
        "focus": "舞台",
        "photo": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/profiles/1777042468612-0c85ce9b.jpg",
    },
    {
        "name": "JIWOO",
        "title": "饒舌／舞蹈",
        "intro": "舞蹈線條有力，節奏型段落和表演張力很有存在感。",
        "focus": "舞蹈",
        "photo": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/profiles/1777042474189-690b0f09.jpg",
    },
    {
        "name": "KYUJIN",
        "title": "全能成員",
        "intro": "忙內但完成度高，唱跳、表情和舞台細節都很穩。",
        "focus": "王牌",
        "photo": "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/profiles/1777042480509-57f474da.jpg",
    },
]

OFFICIAL_CHANNELS = [
    {
        "name": "NMIXX 官方網站",
        "desc": "JYP 官方首頁，適合查看基本資訊與官方入口。",
        "href": OFFICIAL_LINKS["home"],
        "label": "官網",
        "icon": "◎",
    },
    {
        "name": "JYP 官方公告",
        "desc": "公告、行程圖、活動資訊與官方素材來源。",
        "href": OFFICIAL_LINKS["notice"],
        "label": "公告",
        "icon": "↗",
    },
    {
        "name": "NMIXX YouTube",
        "desc": "MV、特別影片、幕後內容與官方影像更新。",
        "href": OFFICIAL_LINKS["youtube"],
        "label": "影音",
        "icon": "▶",
    },
    {
        "name": "NMIXX Instagram",
        "desc": "概念照、現場照片與官方社群動態。",
        "href": OFFICIAL_LINKS["instagram"],
        "label": "社群",
        "icon": "□",
    },
]

def get_site_data(runtime_data: RuntimeDataStore | None = None) -> dict[str, object]:
    generated_updates = runtime_data.read_updates() if runtime_data else []
    return {
        "official_links": OFFICIAL_LINKS,
        "images": IMAGES,
        "hero_slides": _current_hero_slides(runtime_data),
        "updates": _merge_unique_updates(generated_updates, UPDATES),
        "schedule": SCHEDULE,
        "releases": RELEASES,
        "members": MEMBERS,
        "official_channels": OFFICIAL_CHANNELS,
    }


SITE_DATA = get_site_data()
