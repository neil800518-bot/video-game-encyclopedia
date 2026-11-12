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

st.set_page_config(page_title='电子游戏百科全书', page_icon='🎮', layout='wide')
st.markdown('''<style>h1 {font-size: 2rem !important;} h2, h3 {font-size: 1.2rem !important;} @media (max-width: 640px) {h1 {font-size: 1.6rem !important;}}</style>''', unsafe_allow_html=True)
st.title('🎮 电子游戏百科全书')
st.caption('Video Game Encyclopedia · 游戏名称 / ID 搜索 · 以图搜图')

def load_games():
    if not DATA_FILE.is_file():
        return []
    with DATA_FILE.open('r', encoding='utf-8') as f:
        data = json.load(f)
    return [g for g in data if isinstance(g, dict)] if isinstance(data, list) else []


def display_game_name(game):
    """Never render spreadsheet image formulas as game titles."""
    name = str(game.get('name') or '').strip()
    if not name or name.upper().startswith('=DISPIMG('):
        return '名稱待補'
    return name


def safe_image_path(game):
    # Prefer the image explicitly linked in the database.
    name = str(game.get('image') or '').strip()
    if name and Path(name).name == name:
        path = IMAGE_DIR / name
        if path.is_file():
            return path

    # Older imported records may have an empty image field even when
    # their ID-named image has already been uploaded.
    game_id = str(game.get('id') or '').strip()
    if not game_id or Path(game_id).name != game_id or game_id in ('.', '..'):
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
    """Apply reviewed DB-only orientation overrides; retain original image files."""
    image = ImageOps.exif_transpose(source).convert('RGB')
    if str(game.get('provider', '')).strip() == 'DB':
        angle = DB_IMAGE_ROTATIONS.get(str(game.get('id', '')).strip(), 0)
        if angle:
            image = image.rotate(angle, expand=True)
    return image


@st.cache_data(show_spinner=False, max_entries=3000)
def cached_card_image(path_string, provider, game_id, file_mtime_ns):
    """Cache the display thumbnail; file mtime invalidates replaced images."""
    with Image.open(path_string) as source:
        image = oriented_game_image(source, {'provider': provider, 'id': game_id})
        image.thumbnail((240, 320), Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', (240, 320), 'white')
        canvas.paste(image, ((240 - image.width) // 2, (320 - image.height) // 2))
        output = io.BytesIO()
        canvas.save(output, format='PNG')
        return output.getvalue()


def display_card_image(path, game=None):
    """Use cached portrait thumbnails without changing original images."""
    game = game or {}
    st.image(
        cached_card_image(str(path), str(game.get('provider', '')),
                          str(game.get('id', '')), path.stat().st_mtime_ns),
        use_container_width=True,
    )


def image_features(img):
    # Structural grayscale thumbnail, gradient-sign difference hash and RGB histogram.
    img = prepare_image(img)
    gray = ImageOps.fit(img.convert('L'), (32, 32), method=Image.Resampling.LANCZOS)
    gray_array = np.asarray(gray, dtype=np.float32) / 255.0
    gray_array = (gray_array - gray_array.mean()) / (gray_array.std() + 0.12)
    hash_image = ImageOps.fit(img.convert('L'), (17, 16), method=Image.Resampling.LANCZOS)
    pixels = np.asarray(hash_image, dtype=np.int16)
    dhash = (pixels[:, 1:] > pixels[:, :-1]).reshape(-1)
    color = ImageOps.fit(img, (64, 64), method=Image.Resampling.LANCZOS)
    rgb = np.asarray(color, dtype=np.uint8)
    hist = []
    for channel in range(3):
        h, _ = np.histogram(rgb[:, :, channel], bins=16, range=(0, 256))
        hist.append(h.astype(np.float32) / rgb[:, :, channel].size)
    return gray_array, dhash, np.concatenate(hist)


def similarity(a, b):
    gray_a, hash_a, hist_a = a
    gray_b, hash_b, hist_b = b
    structural = max(0.0, float(np.corrcoef(gray_a.ravel(), gray_b.ravel())[0, 1]))
    if not np.isfinite(structural):
        structural = 0.0
    hash_score = 1.0 - float(np.mean(hash_a != hash_b))
    color_score = float(np.minimum(hist_a, hist_b).sum() / 3.0)
    return 0.48 * structural + 0.32 * hash_score + 0.20 * color_score


@st.cache_resource(show_spinner='建立图片索引中…')
def build_image_index():
    entries = []
    for game in load_games():
        path = safe_image_path(game)
        if path is None:
            continue
        try:
            with Image.open(path) as image:
                features = image_features(oriented_game_image(image, game))
            entries.append((game, features))
        except (OSError, ValueError, UnidentifiedImageError):
            continue
    return entries


def query_regions(img):
    """Generate candidate game areas for screenshots with browser/background margins."""
    img = prepare_image(img)
    w, h = img.size
    regions = [('完整截图', img)]
    # Central portrait game canvases are often embedded in wide screenshots.
    for fraction in (0.28, 0.38, 0.50, 0.65, 0.80):
        crop_w = max(32, int(w * fraction))
        if crop_w >= w:
            continue
        for center in (0.40, 0.50, 0.60):
            left = max(0, min(w - crop_w, int(w * center - crop_w / 2)))
            regions.append((f'中央区域 {int(fraction * 100)}%', img.crop((left, 0, left + crop_w, h))))
    # Also handle screenshots with toolbars at the top/bottom.
    for top, bottom in ((0.06, 0.96), (0.12, 0.92)):
        regions.append(('去除上下边框', img.crop((0, int(h * top), w, int(h * bottom)))))
    return regions


def rank_image_matches(query, index, limit=5):
    # Compare every candidate crop against each reference image.
    # Slightly penalize aggressive crops to reduce accidental false matches.
    candidates = []
    for label, region in query_regions(query):
        features = image_features(region)
        fraction = region.width * region.height / max(1, query.width * query.height)
        penalty = 0.025 * (1 - min(1.0, fraction))
        candidates.append((label, features, penalty))
    ranked = []
    for game, features in index:
        best_score, best_region = max(
            ((similarity(candidate, features) - penalty, label)
             for label, candidate, penalty in candidates),
            key=lambda result: result[0],
        )
        ranked.append((max(0.0, best_score), game, best_region))
    return sorted(ranked, key=lambda item: item[0], reverse=True)[:limit]


def decode_pasted_image(data):
    if not isinstance(data, str) or not data.startswith('data:image/'):
        return None
    try:
        payload = base64.b64decode(data.split(',', 1)[1], validate=True)
        if len(payload) > 12 * 1024 * 1024:
            return None
        return Image.open(io.BytesIO(payload)).copy()
    except (ValueError, OSError, IndexError, UnidentifiedImageError):
        return None


# Reset both upload and clipboard components by rotating their widget keys.
if 'image_input_version' not in st.session_state:
    st.session_state.image_input_version = 0

games = load_games()
providers = sorted({str(g.get('provider', '')).strip() for g in games if g.get('provider')})
st.markdown("""
<style>
.block-container {max-width: 1500px; padding-top: 1.4rem;}
/* Hide Streamlit's stale elements while a new widget state is rendering. */
[data-stale="true"] { display: none !important; }
[data-stale="true"] * { animation: none !important; transition: none !important; }
/* Prevent delayed exit fades from leaving outdated search text visible. */
[data-testid="stVerticalBlock"] [data-stale="true"],
[data-testid="stElementContainer"][data-stale="true"] { display: none !important; }
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 14px;}
</style>
""", unsafe_allow_html=True)

search_col, result_col = st.columns([1, 2], gap='medium')
with search_col:
    with st.container(border=True):
        st.subheader('搜寻方式')
        search_mode = st.radio('选择搜寻方式', ['以图搜图', '名称 / ID 搜寻'], label_visibility='collapsed')
        st.divider()
        search = ''
        uploaded = None
        pasted = None
        if search_mode == '以图搜图':
            title_col, clear_col = st.columns([2.1, 1], gap='small', vertical_alignment='center')
            with title_col:
                st.markdown('**上传游戏截图**')
            with clear_col:
                if st.button('🗑️ 清除图片', key='clear_search_image', use_container_width=True):
                    st.session_state.image_input_version += 1
                    st.rerun()
            uploaded = st.file_uploader('拖放 / 选择游戏截图', type=['png', 'jpg', 'jpeg', 'webp'], key=f'reverse_upload_{st.session_state.image_input_version}')
            st.caption('正式版保留上传与贴图 · 点击下方区域后按 Command + V（Windows：Ctrl + V）')
            paste_component = components.declare_component('game_image_paste_v1', path=str(PASTE_DIR))
            pasted = paste_component(key=f'clipboard_paste_{st.session_state.image_input_version}', default=None)
        else:
            search = st.text_input('游戏名称 / ID', placeholder='输入游戏名称、厂商或 ID')
        provider = st.selectbox('游戏厂商', ['全部厂商'] + providers)
        if search_mode == '以图搜图':
            result_limit = st.radio('显示比对结果', [3, 5], format_func=lambda n: f'前 {n} 名', horizontal=True)
        else:
            result_limit = 5

filtered = []
for game in games:
    if provider != '全部厂商' and str(game.get('provider', '')) != provider:
        continue
    terms = [str(game.get(k, '')) for k in ('name', 'id', 'provider')]
    if search_mode == '名称 / ID 搜寻' and search.strip() and search.casefold() not in ' '.join(terms).casefold():
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
        st.warning('贴上的图片无法读取，或图片超过 12 MB。')

with result_col:
    with st.container(border=True):
        if search_mode == '以图搜图':
            st.subheader('图片比对结果')
            if query_image is None:
                st.info('上传或贴上图片后，会自动显示最相似的游戏。')
            else:
                st.image(query_image, caption='待比对截图', width=180)
                with st.spinner('正在比对数据库图片…'):
                    index = build_image_index()
                    ranked = rank_image_matches(query_image, index, limit=result_limit)
                st.caption(f'v2 多区域搜索 · 已比对 {len(index)} 张有图片的游戏记录；缺图游戏不参与图片搜索。')
                if not ranked:
                    st.warning('数据库中尚无可比对的图片。')
                else:
                    st.markdown(f'**最相似的 {len(ranked)} 款游戏**')
                    # Rank one is centered for both top-3 and top-5 modes.
                    for start in range(len(ranked)):
                        if start == 0:
                            _, center, _ = st.columns([1, 2, 1], gap='small')
                            target = center
                        elif start % 2 == 1:
                            pair_cols = st.columns(2, gap='small')
                            target = pair_cols[0]
                        else:
                            target = pair_cols[1]
                        score, game, matched_region = ranked[start]
                        with target:
                            with st.container(border=True):
                                pic, details = st.columns([1, 2], gap='small')
                                with pic:
                                    path = safe_image_path(game)
                                    if path:
                                        display_card_image(path, game)
                                with details:
                                    st.markdown(f'**{start+1}. {display_game_name(game)}**')
                                    st.caption(f"厂商：{game.get('provider', '未知')} · ID：{game.get('id', '无')}")
                                    st.markdown(f'**相似分数：{score * 100:.1f}/100**')
                                    st.caption(f'比对区域：{matched_region}')
                    st.info('相似分数不是身份确认概率；截图经过裁切、缩放或遮挡时，可能出现误判。')
        else:
            st.subheader('名称 / ID 搜寻结果')
            st.caption(f'共找到 {len(filtered) if search.strip() else 0} 款游戏')
            if not search.strip():
                st.info('请输入游戏名称或 ID，右侧将显示符合条件的游戏。')
            elif not filtered:
                st.info('目前没有符合条件的游戏。')
            else:
                items_per_row = 5
                for row_start in range(0, len(filtered), items_per_row):
                    cols = st.columns(items_per_row, gap='small')
                    for col, game in zip(cols, filtered[row_start:row_start+items_per_row]):
                        with col:
                            with st.container(border=True):
                                path = safe_image_path(game)
                                if path:
                                    display_card_image(path, game)
                                st.markdown(f'**{display_game_name(game)}**')
                                st.caption(f"厂商：{game.get('provider', '未知')}")
                                st.caption(f"ID：{game.get('id', '无')}")

# Keep the original complete gallery below both search modes.
# Search results above never replace the browsing gallery.
st.divider()
st.subheader('游戏图片总览')
gallery_games = [
    game for game in games
    if provider == '全部厂商' or str(game.get('provider', '')) == provider
]
st.caption(f'共 {len(gallery_games)} 款游戏')
gallery_per_row = st.radio(
    '每列显示笔数', [5, 10], horizontal=True,
    format_func=lambda n: f'每列 {n} 笔', key='gallery_columns',
)
for row_start in range(0, len(gallery_games), gallery_per_row):
    gallery_cols = st.columns(gallery_per_row, gap='small')
    for col, game in zip(gallery_cols, gallery_games[row_start:row_start + gallery_per_row]):
        with col:
            with st.container(border=True):
                path = safe_image_path(game)
                if path:
                    display_card_image(path, game)
                st.markdown(f'**{display_game_name(game)}**')
                st.caption(f"厂商：{game.get('provider', '未知')}")
                st.caption(f"ID：{game.get('id', '无')}")
