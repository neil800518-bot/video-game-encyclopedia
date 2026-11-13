
import base64
import io
import json
from pathlib import Path
from html import escape

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / 'data' / 'games.json'
IMAGE_DIR = BASE_DIR / 'data' / 'images'
PASTE_DIR = BASE_DIR / 'paste_component'

st.set_page_config(
    page_title='电子游戏百科全书',
    page_icon='🎮',
    layout='wide',
)

st.markdown(
    '''
    <style>
    h1 {font-size: 2rem !important;}
    h2, h3 {font-size: 1.2rem !important;}
    @media (max-width: 640px) {
        h1 {font-size: 1.6rem !important;}
    }
    /* Search panel: compact spacing and red horizontal selector. */
    .st-key-search_panel [data-testid="stVerticalBlock"] { gap: 0.55rem; }
    .st-key-search_panel [data-testid="stSegmentedControl"] { width: 100%; }
    .st-key-search_panel [data-testid="stSegmentedControl"] button {
        flex: 1 1 0; justify-content: center; min-height: 2.5rem;
    }
    .st-key-search_panel [data-testid="stSegmentedControl"] button[aria-checked="true"],
    .st-key-search_panel [data-testid="stSegmentedControl"] button[aria-pressed="true"],
    .st-key-search_panel [data-testid="stSegmentedControl"] button[data-state="checked"] {
        background-color: #d32f42 !important;
        border-color: #d32f42 !important;
        color: #fff !important;
    }
    </style>
    ''',
    unsafe_allow_html=True,
)

# Use Streamlit's native heading instead of a custom HTML text element.
# This avoids platform-dependent CJK glyph clipping and weight rendering.
header_title, header_description = st.columns([1.1, 2.7], gap="small", vertical_alignment="bottom")
with header_title:
    st.title("🎮 电子游戏百科全书")
with header_description:
    st.caption("Video Game Encyclopedia · 游戏名称 / ID 搜索 · 以图搜图")


def load_games():
    if not DATA_FILE.is_file():
        return []
    with DATA_FILE.open('r', encoding='utf-8') as f:
        data = json.load(f)
    return (
        [g for g in data if isinstance(g, dict)]
        if isinstance(data, list)
        else []
    )


def display_game_name(game):
    """Never render spreadsheet image formulas as game titles."""
    name = str(game.get('name') or '').strip()
    if not name or name.upper().startswith('=DISPIMG('):
        return '名稱待補'
    return name


def safe_image_path(game):
    name = str(game.get('image') or '').strip()

    if name and Path(name).name == name:
        path = IMAGE_DIR / name
        if path.is_file():
            return path

    game_id = str(game.get('id') or '').strip()

    if (
        not game_id
        or Path(game_id).name != game_id
        or game_id in ('.', '..')
    ):
        return None

    for extension in ('.jpg', '.jpeg', '.png', '.webp'):
        path = IMAGE_DIR / f'{game_id}{extension}'
        if path.is_file():
            return path

    return None


def prepare_image(img):
    img = ImageOps.exif_transpose(img).convert('RGB')
    img.thumbnail((900, 900))
    return img


DB_IMAGE_ROTATIONS = {
    'DB-0017': 90,
    'DB-0018': 90,
    'DB-0019': 90,
    'DB-0024': 90,
    'DB-0028': 90,
}


def oriented_game_image(source, game):
    image = ImageOps.exif_transpose(source).convert('RGB')

    if str(game.get('provider', '')).strip() == 'DB':
        angle = DB_IMAGE_ROTATIONS.get(
            str(game.get('id', '')).strip(),
            0,
        )
        if angle:
            image = image.rotate(angle, expand=True)

    return image


@st.cache_data(show_spinner=False, max_entries=3000)
def cached_card_image(path_string, provider, game_id, file_mtime_ns):
    with Image.open(path_string) as source:
        image = oriented_game_image(
            source,
            {'provider': provider, 'id': game_id},
        )
        image.thumbnail(
            (240, 320),
            Image.Resampling.LANCZOS,
        )

        canvas = Image.new('RGB', (240, 320), 'white')
        canvas.paste(
            image,
            (
                (240 - image.width) // 2,
                (320 - image.height) // 2,
            ),
        )

        output = io.BytesIO()
        canvas.save(output, format='PNG')
        return output.getvalue()


def display_card_image(path, game=None):
    game = game or {}

    st.image(
        cached_card_image(
            str(path),
            str(game.get('provider', '')),
            str(game.get('id', '')),
            path.stat().st_mtime_ns,
        ),
        use_container_width=True,
    )


def image_features(img):
    img = prepare_image(img)

    gray = ImageOps.fit(
        img.convert('L'),
        (32, 32),
        method=Image.Resampling.LANCZOS,
    )

    gray_array = np.asarray(gray, dtype=np.float32) / 255.0
    gray_array = (
        (gray_array - gray_array.mean())
        / (gray_array.std() + 0.12)
    )

    hash_image = ImageOps.fit(
        img.convert('L'),
        (17, 16),
        method=Image.Resampling.LANCZOS,
    )

    pixels = np.asarray(hash_image, dtype=np.int16)
    dhash = (pixels[:, 1:] > pixels[:, :-1]).reshape(-1)

    color = ImageOps.fit(
        img,
        (64, 64),
        method=Image.Resampling.LANCZOS,
    )

    rgb = np.asarray(color, dtype=np.uint8)
    hist = []

    for channel in range(3):
        h, _ = np.histogram(
            rgb[:, :, channel],
            bins=16,
            range=(0, 256),
        )
        hist.append(
            h.astype(np.float32)
            / rgb[:, :, channel].size
        )

    return gray_array, dhash, np.concatenate(hist)


def similarity(a, b):
    gray_a, hash_a, hist_a = a
    gray_b, hash_b, hist_b = b

    structural = max(
        0.0,
        float(
            np.corrcoef(
                gray_a.ravel(),
                gray_b.ravel(),
            )[0, 1]
        ),
    )

    if not np.isfinite(structural):
        structural = 0.0

    hash_score = 1.0 - float(np.mean(hash_a != hash_b))
    color_score = float(np.minimum(hist_a, hist_b).sum() / 3.0)

    return (
        0.48 * structural
        + 0.32 * hash_score
        + 0.20 * color_score
    )


@st.cache_resource(show_spinner='建立图片索引中…')
def build_image_index():
    entries = []

    for game in load_games():
        path = safe_image_path(game)

        if path is None:
            continue

        try:
            with Image.open(path) as image:
                features = image_features(
                    oriented_game_image(image, game)
                )
            entries.append((game, features))

        except (OSError, ValueError, UnidentifiedImageError):
            continue

    return entries


def query_regions(img):
    img = prepare_image(img)
    w, h = img.size

    regions = [('完整截图', img)]

    for fraction in (0.28, 0.38, 0.50, 0.65, 0.80):
        crop_w = max(32, int(w * fraction))

        if crop_w >= w:
            continue

        for center in (0.40, 0.50, 0.60):
            left = max(
                0,
                min(
                    w - crop_w,
                    int(w * center - crop_w / 2),
                ),
            )

            regions.append(
                (
                    f'中央区域 {int(fraction * 100)}%',
                    img.crop((left, 0, left + crop_w, h)),
                )
            )

    for top, bottom in ((0.06, 0.96), (0.12, 0.92)):
        regions.append(
            (
                '去除上下边框',
                img.crop(
                    (0, int(h * top), w, int(h * bottom))
                ),
            )
        )

    return regions


def rank_image_matches(query, index, limit=5):
    candidates = []

    for label, region in query_regions(query):
        features = image_features(region)

        fraction = (
            region.width * region.height
            / max(1, query.width * query.height)
        )

        penalty = 0.025 * (
            1 - min(1.0, fraction)
        )

        candidates.append(
            (label, features, penalty)
        )

    ranked = []

    for game, features in index:
        best_score, best_region = max(
            (
                (
                    similarity(candidate, features) - penalty,
                    label,
                )
                for label, candidate, penalty in candidates
            ),
            key=lambda result: result[0],
        )

        ranked.append(
            (
                max(0.0, best_score),
                game,
                best_region,
            )
        )

    return sorted(
        ranked,
        key=lambda item: item[0],
        reverse=True,
    )[:limit]


def decode_pasted_image(data):
    if (
        not isinstance(data, str)
        or not data.startswith('data:image/')
    ):
        return None

    try:
        payload = base64.b64decode(
            data.split(',', 1)[1],
            validate=True,
        )

        if len(payload) > 12 * 1024 * 1024:
            return None

        return Image.open(
            io.BytesIO(payload)
        ).copy()

    except (
        ValueError,
        OSError,
        IndexError,
        UnidentifiedImageError,
    ):
        return None


# ============================================================
# FIX 1: Clear uploaded and pasted images before the next render.
# ============================================================

if 'image_input_version' not in st.session_state:
    st.session_state.image_input_version = 0


def clear_search_image():
    """Reset both image input widgets before Streamlit reruns."""
    st.session_state.image_input_version += 1


# ============================================================
# FIX 2: Floating back-to-top button.
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1500px;
        padding-top: 1.4rem;
    }

    [data-stale="true"],
    [data-testid="stElementContainer"][data-stale="true"] {
        display: none !important;
        transition: none !important;
        animation: none !important;
    }

    /* Do not paint empty card shells during Streamlit rerenders. */
    .st-key-image_results [data-testid="stVerticalBlockBorderWrapper"]:not(:has(img, p, h1, h2, h3, button, [data-testid="stAlert"])),
    .st-key-text_results [data-testid="stVerticalBlockBorderWrapper"]:not(:has(img, p, h1, h2, h3, button, [data-testid="stAlert"])) {
        display: none !important;
    }

    [data-stale="true"] * {
        animation: none !important;
        transition: none !important;
    }

    [data-testid="stVerticalBlock"] [data-stale="true"],
    [data-testid="stElementContainer"][data-stale="true"] {
        display: none !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
    }

    html {
        scroll-behavior: smooth;
    }

    #back-to-top {
        position: fixed;
        right: 24px;
        bottom: 82px;
        z-index: 999999;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 12px 18px;
        border-radius: 30px;
        background: #2563eb;
        color: white !important;
        font-size: 15px;
        font-weight: 600;
        text-decoration: none !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        cursor: pointer;
    }

    #back-to-top:hover {
        background: #1d4ed8;
        color: white !important;
    }

    @media (max-width: 640px) {
        #back-to-top {
            right: 12px;
            bottom: 78px;
            padding: 10px 14px;
            font-size: 13px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# A small browser component provides a working floating button.
# Streamlit's main page scrolls inside its application container.
components.html(
    """
    <script>
    (function () {
        const doc = window.parent.document;

        function installButton() {
            let button = doc.getElementById(
                'game-encyclopedia-back-to-top'
            );

            if (!button) {
                button = doc.createElement('button');
                button.id = 'game-encyclopedia-back-to-top';
                button.type = 'button';
                button.textContent = '↑ 回到頂部';

                Object.assign(button.style, {
                    position: 'fixed',
                    right: '24px',
                    bottom: '82px',
                    zIndex: '999999',
                    padding: '12px 18px',
                    borderRadius: '30px',
                    border: 'none',
                    background: '#2563eb',
                    color: '#ffffff',
                    fontSize: '15px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.2)'
                });

                doc.body.appendChild(button);
            }

            button.onclick = function (event) {
                event.preventDefault();
                const win = window.parent;
                const selectors = [
                    '[data-testid="stAppScrollContainer"]',
                    '[data-testid="stMain"]',
                    'section.main',
                    '.main',
                    '[data-testid="stAppViewContainer"]'
                ];
                const candidates = selectors.flatMap(
                    selector => Array.from(doc.querySelectorAll(selector))
                );
                candidates.push(doc.scrollingElement, doc.documentElement, doc.body);
                for (const element of candidates) {
                    if (!element || typeof element.scrollTo !== 'function') continue;
                    if (element.scrollTop > 0 || element.scrollHeight > element.clientHeight + 5) {
                        element.scrollTo({top: 0, behavior: 'smooth'});
                    }
                }
                win.scrollTo({top: 0, behavior: 'smooth'});
                // A second pass handles Streamlit layout updates during reruns.
                win.requestAnimationFrame(() => {
                    for (const element of candidates) {
                        if (element && element.scrollTop > 0) {
                            element.scrollTop = 0;
                        }
                    }
                });
            };
        }

        installButton();
    })();
    </script>
    """,
    height=0,
)


games = load_games()

providers = sorted({
    str(g.get('provider', '')).strip()
    for g in games
    if g.get('provider')
})


search_col, result_col = st.columns(
    [1, 2],
    gap='medium',
)

with search_col:
    with st.container(border=True, key='search_panel'):
        st.subheader('搜寻方式')

        search_mode = st.segmented_control(
            '选择搜寻方式',
            ['以图搜图', '名称 / ID 搜寻'],
            default='以图搜图',
            selection_mode='single',
            label_visibility='collapsed',
            key='search_mode_switch',
        ) or '以图搜图'

        st.markdown(
            '<div style="border-top:1px solid #e5e7eb;'
            'margin:0.1rem 0 0.25rem"></div>',
            unsafe_allow_html=True,
        )

        search = ''
        uploaded = None
        pasted = None

        if search_mode == '以图搜图':
            title_col, clear_col = st.columns(
                [2.1, 1],
                gap='small',
                vertical_alignment='center',
            )

            with title_col:
                st.markdown('**上传游戏截图**')

            with clear_col:
                st.button(
                    '🗑️ 清除图片',
                    key='clear_search_image',
                    use_container_width=True,
                    on_click=clear_search_image,
                )

            uploaded = st.file_uploader(
                '拖放 / 选择游戏截图',
                type=['png', 'jpg', 'jpeg', 'webp'],
                key=(
                    f'reverse_upload_'
                    f'{st.session_state.image_input_version}'
                ),
            )

            st.caption(
                '正式版保留上传与贴图 · '
                '点击下方区域后按 Command + V'
                '（Windows：Ctrl + V）'
            )

            paste_component = components.declare_component(
                'game_image_paste_v1',
                path=str(PASTE_DIR),
            )

            pasted = paste_component(
                key=(
                    f'clipboard_paste_'
                    f'{st.session_state.image_input_version}'
                ),
                default=None,
            )

        else:
            search = st.text_input(
                '游戏名称 / ID',
                placeholder='输入游戏名称、厂商或 ID',
            )

        selected_providers = st.multiselect(
            '游戏厂商',
            options=providers,
            default=[],
            placeholder='全部厂商（可复选）',
            help='不选择表示全部厂商；可同时选择多个厂商，点击选项旁的 × 可取消。',
            key='selected_game_providers',
        )

        if search_mode == '以图搜图':
            result_limit = st.radio(
                '显示比对结果',
                [3, 5],
                format_func=lambda n: f'前 {n} 名',
                horizontal=True,
            )
        else:
            result_limit = 5


filtered = []

for game in games:
    if (
        selected_providers
        and str(game.get('provider', '')).strip() not in selected_providers
    ):
        continue

    terms = [
        str(game.get(k, ''))
        for k in ('name', 'id', 'provider')
    ]

    if (
        search_mode == '名称 / ID 搜寻'
        and search.strip()
        and search.casefold()
        not in ' '.join(terms).casefold()
    ):
        continue

    filtered.append(game)


query_image = None

if uploaded is not None:
    try:
        query_image = Image.open(uploaded).copy()
    except (OSError, UnidentifiedImageError):
        st.error('上传文件不是有效图片。')

elif pasted:
    query_image = decode_pasted_image(pasted)

    if query_image is None:
        st.warning(
            '贴上的图片无法读取，或图片超过 12 MB。'
        )


with result_col:
    # Separate keyed result trees prevent old image cards being reused on mode changes.
    result_key = 'image_results' if search_mode == '以图搜图' else 'text_results'
    with st.container(border=True, key=result_key):
        if search_mode == '以图搜图':
            st.subheader('图片比对结果')

            if query_image is None:
                st.info(
                    '上传或贴上图片后，'
                    '会自动显示最相似的游戏。'
                )

            else:
                st.image(
                    query_image,
                    caption='待比对截图',
                    width=180,
                )

                with st.spinner('正在比对数据库图片…'):
                    index = build_image_index()
                    if selected_providers:
                        index = [
                            (game, features)
                            for game, features in index
                            if str(game.get('provider', '')).strip()
                            in selected_providers
                        ]

                    ranked = rank_image_matches(
                        query_image,
                        index,
                        limit=result_limit,
                    )

                st.caption(
                    f'v2 多区域搜索 · '
                    f'已比对 {len(index)} 张有图片的游戏记录；'
                    f'缺图游戏不参与图片搜索。'
                )

                if not ranked:
                    st.warning(
                        '数据库中尚无可比对的图片。'
                    )

                else:
                    st.markdown(
                        f'**最相似的 {len(ranked)} 款游戏**'
                    )

                    for start in range(len(ranked)):
                        if start == 0:
                            _, center, _ = st.columns(
                                [1, 2, 1],
                                gap='small',
                            )
                            target = center

                        elif start % 2 == 1:
                            pair_cols = st.columns(
                                2,
                                gap='small',
                            )
                            target = pair_cols[0]

                        else:
                            target = pair_cols[1]

                        score, game, matched_region = ranked[start]

                        with target:
                            with st.container(border=True):
                                pic, details = st.columns(
                                    [1, 2],
                                    gap='small',
                                )

                                with pic:
                                    path = safe_image_path(game)

                                    if path:
                                        display_card_image(
                                            path,
                                            game,
                                        )

                                with details:
                                    st.markdown(
                                        f'**{start + 1}. '
                                        f'{display_game_name(game)}**'
                                    )

                                    st.caption(
                                        f"厂商："
                                        f"{game.get('provider', '未知')}"
                                        f" · ID："
                                        f"{game.get('id', '无')}"
                                    )

                                    st.markdown(
                                        f'**相似分数：'
                                        f'{score * 100:.1f}/100**'
                                    )

                                    st.caption(
                                        f'比对区域：{matched_region}'
                                    )

                    st.info(
                        '相似分数不是身份确认概率；'
                        '截图经过裁切、缩放或遮挡时，'
                        '可能出现误判。'
                    )

        else:
            st.markdown(
                """
                <style>
                .search-results-heading {
                    display: flex;
                    align-items: baseline;
                    gap: 14px;
                    flex-wrap: wrap;
                    margin-bottom: 0.65rem;
                }
                .search-results-heading-title {
                    font-size: 1.2rem;
                    font-weight: 700;
                }
                .search-results-heading-count {
                    color: #808080;
                    font-size: 0.88rem;
                }
                [class*="st-key-search_card_"] [data-testid="stVerticalBlock"] {
                    gap: 0.4rem;
                    overflow: visible;
                }
                [class*="st-key-search_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
                    height: 100%;
                    overflow: visible;
                }
                [class*="st-key-search_card_"] .search-game-name {
                    font-weight: 700;
                    font-size: 0.95rem;
                    line-height: 1.4;
                    height: 2.8em;
                    display: -webkit-box;
                    -webkit-box-orient: vertical;
                    -webkit-line-clamp: 2;
                    line-clamp: 2;
                    overflow: hidden;
                    overflow-wrap: anywhere;
                    cursor: help;
                }
                [class*="st-key-search_card_"] .search-name-wrap {
                    position: relative;
                    overflow: visible;
                    z-index: 1;
                }
                [class*="st-key-search_card_"] .search-name-wrap:hover,
                [class*="st-key-search_card_"] .search-name-wrap:focus-within {
                    z-index: 1000;
                }
                [class*="st-key-search_card_"] .search-name-wrap:hover::after,
                [class*="st-key-search_card_"] .search-name-wrap:focus-within::after {
                    content: attr(data-full-name);
                    position: absolute;
                    left: 0;
                    bottom: calc(100% + 6px);
                    width: max-content;
                    max-width: min(340px, 80vw);
                    white-space: normal;
                    overflow-wrap: anywhere;
                    padding: 8px 10px;
                    border-radius: 6px;
                    background: #262626;
                    color: #fff;
                    font-size: 0.85rem;
                    font-weight: 400;
                    line-height: 1.5;
                    box-shadow: 0 4px 14px rgba(0,0,0,0.2);
                    pointer-events: none;
                    z-index: 1001;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            result_count = len(filtered) if search.strip() else 0
            st.markdown(
                '<div class="search-results-heading">'
                '<span class="search-results-heading-title">名称 / ID 搜寻结果</span>'
                f'<span class="search-results-heading-count">共找到 {result_count} 款游戏</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            if not search.strip():
                st.info(
                    '请输入游戏名称或 ID，'
                    '右侧将显示符合条件的游戏。'
                )

            elif not filtered:
                st.info(
                    '目前没有符合条件的游戏。'
                )

            else:
                items_per_row = 5

                for row_start in range(
                    0,
                    len(filtered),
                    items_per_row,
                ):
                    cols = st.columns(
                        items_per_row,
                        gap='small',
                    )

                    for card_index, (col, game) in enumerate(zip(
                        cols,
                        filtered[
                            row_start:
                            row_start + items_per_row
                        ],
                    )):
                        with col:
                            with st.container(border=True, key=f'search_card_{row_start}_{card_index}'):
                                path = safe_image_path(game)

                                if path:
                                    display_card_image(
                                        path,
                                        game,
                                    )

                                full_name = escape(display_game_name(game), quote=True)
                                st.markdown(
                                    f'<div class="search-name-wrap" data-full-name="{full_name}">'
                                    f'<div class="search-game-name" tabindex="0">'
                                    f'{full_name}</div></div>',
                                    unsafe_allow_html=True,
                                )

                                st.caption(
                                    f"厂商："
                                    f"{game.get('provider', '未知')}"
                                )

                                st.caption(
                                    f"ID：{game.get('id', '无')}"
                                )


# ============================================================
# Original complete game gallery.
# ============================================================

st.divider()
st.markdown(
    """
    <style>
    .gallery-heading {
        display: flex;
        align-items: baseline;
        gap: 14px;
        flex-wrap: wrap;
        margin-bottom: 0.4rem;
    }
    .gallery-heading-title { font-size: 1.2rem; font-weight: 700; }
    .gallery-heading-count { color: #808080; font-size: 0.88rem; }
    [class*="st-key-gallery_card_"] [data-testid="stVerticalBlock"] {
        gap: 0.4rem;
    }
    [class*="st-key-gallery_card_"] .gallery-game-name {
        font-weight: 700;
        font-size: 0.95rem;
        line-height: 1.4;
        height: 2.8em;
        display: -webkit-box;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 2;
        line-clamp: 2;
        overflow: hidden;
        overflow-wrap: anywhere;
        cursor: help;
    }
    [class*="st-key-gallery_card_"] .gallery-name-wrap {
        position: relative;
        overflow: visible;
        z-index: 1;
    }
    [class*="st-key-gallery_card_"] .gallery-name-wrap:hover,
    [class*="st-key-gallery_card_"] .gallery-name-wrap:focus-within {
        z-index: 1000;
    }
    [class*="st-key-gallery_card_"] .gallery-name-wrap:hover::after,
    [class*="st-key-gallery_card_"] .gallery-name-wrap:focus-within::after {
        content: attr(data-full-name);
        position: absolute;
        left: 0;
        bottom: calc(100% + 6px);
        width: max-content;
        max-width: min(340px, 80vw);
        white-space: normal;
        overflow-wrap: anywhere;
        padding: 8px 10px;
        border-radius: 6px;
        background: #262626;
        color: #fff;
        font-size: 0.85rem;
        font-weight: 400;
        line-height: 1.5;
        box-shadow: 0 4px 14px rgba(0,0,0,0.2);
        pointer-events: none;
        z-index: 1001;
    }
    [class*="st-key-gallery_card_"] [data-testid="stVerticalBlock"],
    [class*="st-key-gallery_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
        overflow: visible;
    }
    [class*="st-key-gallery_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
        height: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

gallery_games = [
    game
    for game in games
    if (
        not selected_providers
        or str(game.get('provider', '')).strip() in selected_providers
    )
]

st.markdown(
    '<div class="gallery-heading">'
    '<span class="gallery-heading-title">游戏图片总览</span>'
    f'<span class="gallery-heading-count">共 {len(gallery_games)} 款游戏</span>'
    '</div>',
    unsafe_allow_html=True,
)

gallery_per_row = st.radio(
    '每列显示笔数',
    [5, 10],
    horizontal=True,
    format_func=lambda n: f'每列 {n} 笔',
    key='gallery_columns',
)

for row_start in range(
    0,
    len(gallery_games),
    gallery_per_row,
):
    gallery_cols = st.columns(
        gallery_per_row,
        gap='small',
    )

    for card_index, (col, game) in enumerate(zip(
        gallery_cols,
        gallery_games[
            row_start:
            row_start + gallery_per_row
        ],
    )):
        with col:
            with st.container(border=True, key=f'gallery_card_{row_start}_{card_index}'):
                path = safe_image_path(game)

                if path:
                    display_card_image(
                        path,
                        game,
                    )

                full_name = escape(display_game_name(game), quote=True)
                st.markdown(
                    f'<div class="gallery-name-wrap" data-full-name="{full_name}">'
                    f'<div class="gallery-game-name" tabindex="0">'
                    f'{full_name}</div></div>',
                    unsafe_allow_html=True,
                )

                st.caption(
                    f"厂商："
                    f"{game.get('provider', '未知')}"
                )

                st.caption(
                    f"ID：{game.get('id', '无')}"
                )
