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


def display_card_image(path, game=None):
    """Use a consistent portrait canvas without cropping the original image."""
    with Image.open(path) as source:
        image = oriented_game_image(source, game or {})
        image.thumbnail((240, 320), Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', (240, 320), 'white')
        canvas.paste(image, ((240 - image.width) // 2, (320 - image.height) // 2))
    st.image(canvas, use_container_width=True)


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

left_col, right_col = st.columns(2, gap='large')
games = load_games()
providers = sorted({str(g.get('provider', '')).strip() for g in games if g.get('provider')})
with left_col:
    st.subheader('🔍 名称 / ID 搜索')
    search = st.text_input('搜寻游戏', placeholder='输入游戏名称、厂商或游戏 ID，例如 CG-0010')
    provider = st.selectbox('游戏厂商', ['全部厂商'] + providers)
with right_col:
    st.subheader('🖼️ 以图搜图')
    st.caption('上传截图，或点击贴图框后按 Command + V（Windows：Ctrl + V）')
    uploaded = st.file_uploader('拖拉 / 选择游戏截图', type=['png', 'jpg', 'jpeg', 'webp'], key=f'reverse_upload_{st.session_state.image_input_version}')
    paste_component = components.declare_component('game_image_paste_v1', path=str(PASTE_DIR))
    pasted = paste_component(key=f'clipboard_paste_{st.session_state.image_input_version}', default=None)
    if st.button('🗑️ 清除圖片', key='clear_search_image'):
        st.session_state.image_input_version += 1
        st.rerun()
filtered = []
for game in games:
    if provider != '全部厂商' and str(game.get('provider', '')) != provider:
        continue
    terms = [str(game.get(k, '')) for k in ('name', 'id', 'provider')]
    if search.casefold() not in ' '.join(terms).casefold():
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
if query_image is not None:
    st.image(query_image, caption='待比对截图', width=260)
    with st.spinner('正在比对数据库图片…'):
        index = build_image_index()
        ranked = rank_image_matches(query_image, index)
    st.caption(f'v2 多区域搜索 · 已比对 {len(index)} 张有图片的游戏记录；缺图游戏不参与图片搜索。')
    if not ranked:
        st.warning('数据库中尚无可比对的图片。')
    else:
        st.subheader('最相似的 5 款游戏')
        cols = st.columns(5)
        for i, (score, game, matched_region) in enumerate(ranked):
            with cols[i]:
                path = safe_image_path(game)
                if path:
                    display_card_image(path, game)
                st.markdown(f"**{i+1}. {display_game_name(game)}**")
                st.caption(f"厂商：{game.get('provider', '未知')}")
                st.caption(f"游戏 ID：{game.get('id', '无')}")
                st.caption(f'图片相似分数：{score * 100:.1f}/100')
                st.caption(f'比对区域：{matched_region}')
        st.info('相似分数不是身份确认概率；截图经过裁切、缩放或遮挡时，可能出现误判。')
else:
    st.info('上传或贴上图片后，会自动显示最相似的 5 款游戏。')

st.divider()
st.subheader('📚 名称 / ID 搜索结果')
st.write(f'共找到 {len(filtered)} 款游戏')
if not filtered:
    st.info('目前没有符合条件的游戏。')
else:
    items_per_row = st.radio(
        '每列顯示筆數',
        options=[5, 10],
        index=0,
        horizontal=True,
        format_func=lambda count: f'每列 {count} 筆',
        key='search_results_columns',
    )
    # Build a fresh set of columns for each row. Reusing the same columns
    # makes Streamlit stack each column independently and misalign cards.
    for row_start in range(0, len(filtered), items_per_row):
        row_games = filtered[row_start:row_start + items_per_row]
        cols = st.columns(items_per_row, gap='small')
        for col, game in zip(cols, row_games):
            with col:
                # A separate bordered card keeps each image and its labels together.
                with st.container(border=True):
                    path = safe_image_path(game)
                    if path:
                        display_card_image(path, game)
                    st.markdown(
                        '<div style="padding:2px 0 4px;">'
                        f'<div style="min-height:2.5em;line-height:1.25;font-weight:600;'
                        f'text-align:center;overflow-wrap:anywhere;">'
                        f'{escape(display_game_name(game))}</div>'
                        f'<div style="font-size:0.78rem;color:gray;line-height:1.35;">'
                        f'厂商：{escape(str(game.get("provider", "未知")))}</div>'
                        f'<div style="font-size:0.78rem;color:gray;line-height:1.35;">'
                        f'ID：{escape(str(game.get("id", "无")))}</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
