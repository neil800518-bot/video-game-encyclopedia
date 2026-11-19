
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


def render_search_copy_details(game, *, rank=None, score=None, matched_region=None):
    """Compact name/provider copy controls without extra card height."""
    name = escape(display_game_name(game), quote=True)
    provider = escape(str(game.get('provider', '未知')), quote=True)
    is_image_match = rank is not None
    markup = """
    <style>
      html, body { margin: 0; padding: 0; background: transparent; color: inherit; font-family: sans-serif; overflow: visible; }
      .line { display: flex; align-items: flex-start; gap: 3px; min-width: 0; }
      .name { font-weight: 700; font-size: 14px; line-height: 20px; display: -webkit-box;
              -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden;
              overflow-wrap: anywhere; flex: 1; min-width: 0; }
      .provider { color: #808080; font-size: 13px; line-height: 22px; overflow-wrap: anywhere; }
      button { border: 0; background: transparent; color: #777; cursor: pointer;
               padding: 2px; width: 22px; height: 23px; flex-shrink: 0; border-radius: 4px;
               display: inline-flex; align-items: center; justify-content: center; }
      button:hover, button:focus-visible { background: #eeeeee; color: #222; }
      button svg { width: 15px; height: 15px; stroke: currentColor; fill: none;
                   stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
      button.copied { color: #16803c; }
      .status { display: none !important; }
      .rank { font-weight: 700; font-size: 14px; line-height: 20px; margin-bottom: 4px; }
      .meta { color: #808080; font-size: 13px; line-height: 18px; margin-top: 4px; }
      .score { color: inherit; font-size: 14px; font-weight: 700; line-height: 20px; margin-top: 4px; }
    </style>
    __RANK__
    <div class="line">
      <div class="name" title="__NAME__">__NAME__</div>
      <button type="button" data-copy="__NAME__" aria-label="复制完整游戏名称" title="复制完整游戏名称"></button>
    </div>
    <div class="line">
      <span class="provider">厂商：__PROVIDER__</span>
      <button type="button" data-copy="__PROVIDER__" aria-label="复制厂商名称" title="复制厂商名称"></button>
    </div>
    __MATCH_META__
    <div class="status" role="status" aria-live="polite"></div>
    <script>
    const copyIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>';
    const checkIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>';
    async function copyText(value) {
      if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(value); return true; } catch (e) {}
      }
      const area = document.createElement('textarea');
      area.value = value; area.setAttribute('readonly', '');
      area.style.position = 'fixed'; area.style.opacity = '0';
      document.body.appendChild(area); area.focus(); area.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (e) {}
      area.remove();
      return ok;
    }
    document.querySelectorAll('button[data-copy]').forEach(button => {
      button.innerHTML = copyIcon;
      button.addEventListener('click', async () => {
        const ok = await copyText(button.dataset.copy);
        const message = ok ? '已复制成功' : '复制失败，请检查浏览器剪贴簿权限';
        document.querySelector('.status').textContent = message;
        button.innerHTML = ok ? checkIcon : copyIcon;
        button.classList.toggle('copied', ok);
        button.title = message;
        clearTimeout(button.resetTimer);
        button.resetTimer = setTimeout(() => {
          button.innerHTML = copyIcon;
          button.classList.remove('copied');
          button.title = button.getAttribute('aria-label');
        }, 1500);
      });
    });
    </script>
    """
    rank_html = f'<div class="rank">第 {rank} 名</div>' if is_image_match else ''
    match_html = ''
    if is_image_match:
        game_id = escape(str(game.get('id', '无')), quote=True)
        region = escape(str(matched_region), quote=True)
        match_html = (
            f'<div class="meta">ID：{game_id}</div>'
            f'<div class="score">相似分数：{score * 100:.1f}/100</div>'
            f'<div class="meta">比对区域：{region}</div>'
        )
    components.html(
        markup.replace("__NAME__", name)
        .replace("__PROVIDER__", provider)
        .replace("__RANK__", rank_html)
        .replace("__MATCH_META__", match_html),
        height=183 if is_image_match else 76,
        scrolling=False,
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


def remove_thumbnail_padding(img):
    """Conservatively remove near-white overview-thumbnail side padding.

    Accept either two white side bands or four-sided white padding.
    Never crop a single side, and leave ordinary screenshots unchanged.
    """
    img = prepare_image(img)
    if img.width < 48 or img.height < 48:
        return None

    rgb = np.asarray(img, dtype=np.uint8)
    white = np.all(rgb >= 245, axis=2)
    h, w = white.shape

    # Count consecutive near-white columns from each side. A column must
    # be almost entirely white, not just white at its corners.
    column_white = white.mean(axis=0) >= 0.98
    left = 0
    while left < w and column_white[left]:
        left += 1
    right = w
    while right > left and column_white[right - 1]:
        right -= 1

    # Require meaningful padding on BOTH sides. Limit the amount removed
    # to avoid treating a mostly-white screenshot as a thumbnail canvas.
    min_band = max(3, int(round(w * 0.015)))
    if not (min_band <= left <= int(w * 0.30)
            and min_band <= w - right <= int(w * 0.30)):
        return None

    # The inner edges should be substantially more colorful than the
    # padding, which guards against cropping plain light game screens.
    if right - left < 32:
        return None
    inner = white[:, left:right]
    if float((~inner).mean()) < 0.20:
        return None

    # Optionally remove top/bottom near-white rows inside the content
    # width; neither is required for side-padding detection.
    row_white = white[:, left:right].mean(axis=1) >= 0.98
    top = 0
    while top < h and row_white[top]:
        top += 1
    bottom = h
    while bottom > top and row_white[bottom - 1]:
        bottom -= 1
    if top > int(h * 0.20):
        top = 0
    if h - bottom > int(h * 0.20):
        bottom = h
    if bottom - top < 32:
        return None

    return img.crop((left, top, right, bottom))



def locate_portrait_game_regions(img):
    """Find dense portrait content inside a wide browser screenshot.

    This is an optional candidate generator, not a replacement for the
    existing matching features or scoring. Reject ambiguous/light layouts.
    """
    w, h = img.size
    if w < 700 or w / max(1, h) < 1.15:
        return []

    rgb = np.asarray(img, dtype=np.float32) / 255.0
    hi = rgb.max(axis=2)
    lo = rgb.min(axis=2)
    chroma = hi - lo
    # Dense game artwork is usually colorful and nonwhite, unlike browser UI.
    ink = (chroma > 0.16) & (lo < 0.76)
    row_start, row_end = int(h * 0.16), int(h * 0.88)
    column_density = ink[row_start:row_end].mean(axis=0)
    kernel = np.ones(9, dtype=np.float32) / 9.0
    smoothed = np.convolve(column_density, kernel, mode='same')
    active = smoothed > 0.24

    runs = []
    start = None
    for x in range(w + 1):
        occupied = x < w and bool(active[x])
        if occupied and start is None:
            start = x
        elif not occupied and start is not None:
            if int(w * 0.14) <= x - start <= int(w * 0.40):
                runs.append((start, x))
            start = None

    candidates = []
    for left, right in sorted(
        runs, key=lambda pair: -float(smoothed[pair[0]:pair[1]].mean())
    )[:3]:
        # Recover vertical content boundaries using the same conservative mask.
        row_density = ink[:, left:right].mean(axis=1)
        ys = np.flatnonzero(row_density > 0.25)
        if len(ys) < int(h * 0.42):
            continue
        top, bottom = int(ys[0]), int(ys[-1]) + 1
        if not (int(h * 0.40) <= bottom - top <= int(h * 0.95)):
            continue
        if not (0.35 <= (right - left) / (bottom - top) <= 0.85):
            continue
        # Include a small boundary margin for antialiased game edges.
        margin_x = max(2, int(w * 0.004))
        margin_y = max(2, int(h * 0.004))
        box = (max(0, left - margin_x), max(0, top - margin_y),
               min(w, right + margin_x), min(h, bottom + margin_y))
        candidates.append((
            '第五階段｜自動定位直向遊戲',
            img.crop(box),
        ))
    return candidates


def refine_portrait_game_boundaries(img):
    """Add edge-guided portrait bounds without changing existing scoring.

    The fifth-stage color mask supplies the seed.  A local image-gradient
    search then looks for dark/low-saturation frame edges which that mask
    can miss.  Legacy phase-six margin candidates are retained.
    """
    w, h = img.size
    if w < 700 or w / max(1, h) < 1.15:
        return []

    rgb = np.asarray(img, dtype=np.float32) / 255.0
    hi, lo = rgb.max(axis=2), rgb.min(axis=2)
    ink = ((hi - lo) > 0.16) & (lo < 0.76)
    start_y, end_y = int(h * 0.16), int(h * 0.88)
    density = np.convolve(
        ink[start_y:end_y].mean(axis=0),
        np.ones(9, dtype=np.float32) / 9.0,
        mode='same',
    )
    active = density > 0.24
    runs, start = [], None
    for x in range(w + 1):
        occupied = x < w and bool(active[x])
        if occupied and start is None:
            start = x
        elif not occupied and start is not None:
            if int(w * 0.14) <= x - start <= int(w * 0.40):
                runs.append((start, x))
            start = None

    # Grayscale differences reveal boundaries even when their pixels are
    # dark or desaturated. Only inspect a narrow band near the color seed.
    gray = rgb.mean(axis=2)
    candidates = []
    for left, right in sorted(
        runs, key=lambda pair: -float(density[pair[0]:pair[1]].mean())
    )[:3]:
        row_density = ink[:, left:right].mean(axis=1)
        ys = np.flatnonzero(row_density > 0.25)
        if len(ys) < int(h * 0.42):
            continue
        top, bottom = int(ys[0]), int(ys[-1]) + 1
        bw, bh = right - left, bottom - top
        if not (int(h * 0.40) <= bh <= int(h * 0.95)):
            continue
        if not (0.35 <= bw / max(1, bh) <= 0.85):
            continue

        # Preserve all previous sixth-stage regions for comparison.
        for margin_fraction in (0.025, 0.055, 0.085):
            mx = max(3, int(round(bw * margin_fraction)))
            my = max(3, int(round(bh * margin_fraction)))
            x0, x1 = max(0, left - mx), min(w, right + mx)
            y0, y1 = max(0, top - my), min(h, bottom + my)
            if x1 - x0 >= 48 and y1 - y0 >= 96:
                candidates.append((
                    '第六階段｜邊界精修 ' + str(round(margin_fraction * 100, 1)) + '%',
                    img.crop((x0, y0, x1, y1)),
                ))

        # Search outward for a coherent vertical/horizontal frame edge.
        # Median over the central span suppresses isolated UI/text edges.
        y0 = max(0, top + int(bh * 0.12))
        y1 = min(h, bottom - int(bh * 0.12))
        x0 = max(0, left + int(bw * 0.12))
        x1 = min(w, right - int(bw * 0.12))
        if y1 - y0 < 32 or x1 - x0 < 32:
            continue
        vertical = np.median(
            np.abs(np.diff(gray[y0:y1, :], axis=1)), axis=0
        )
        horizontal = np.median(
            np.abs(np.diff(gray[:, x0:x1], axis=0)), axis=1
        )

        def outward_edge(seed, direction, strength, max_distance, bound):
            # Require a visible, coherent edge; otherwise use the seed.
            indices = [
                seed + direction * offset
                for offset in range(1, max_distance + 1)
                if 1 <= seed + direction * offset < bound
            ]
            if not indices:
                return seed
            best = max(indices, key=lambda pos: float(strength[pos - 1]))
            if float(strength[best - 1]) < 0.055:
                return seed
            return best

        dx = max(3, int(bw * 0.12))
        dy = max(3, int(bh * 0.12))
        edge_left = outward_edge(left, -1, vertical, dx, w)
        edge_right = outward_edge(right, 1, vertical, dx, w)
        edge_top = outward_edge(top, -1, horizontal, dy, h)
        edge_bottom = outward_edge(bottom, 1, horizontal, dy, h)
        # Add a small safety border for antialiasing, not a broad crop.
        box = (
            max(0, edge_left - 2), max(0, edge_top - 2),
            min(w, edge_right + 2), min(h, edge_bottom + 2),
        )
        rw, rh = box[2] - box[0], box[3] - box[1]
        if rw >= 48 and rh >= 96 and 0.35 <= rw / rh <= 0.85:
            candidates.append((
                '第六階段｜邊緣導向精確定位',
                img.crop(box),
            ))
    return candidates


def query_regions(img):
    img = prepare_image(img)
    w, h = img.size

    regions = [('完整截图', img)]

    # Overview cards are letterboxed on a 240x320 white canvas.
    # Compare their unpadded content as an additional query candidate.
    unpadded = remove_thumbnail_padding(img)
    if unpadded is not None:
        regions.append(('去除总览缩图白边', unpadded))


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

    # v3 phase 4: additional portrait-window candidates for full browser
    # screenshots. Existing candidates and similarity weights remain intact.
    # These windows cover a game occupying roughly a quarter of a desktop
    # screenshot, including a surrounding browser/DevTools interface.
    if w >= 700 and w / max(1, h) >= 1.15:
        for width_fraction in (0.23, 0.30):
            window_w = int(w * width_fraction)
            for left_fraction in (0.16, 0.24, 0.32, 0.40):
                left = min(w - window_w, int(w * left_fraction))
                for top_fraction in (0.12, 0.20):
                    top = int(h * top_fraction)
                    window_h = min(h - top, int(h * 0.70))
                    if window_w >= 48 and window_h >= 96:
                        regions.append((
                            '第四階段｜直向遊戲定位候選',
                            img.crop((left, top, left + window_w, top + window_h)),
                        ))

    # Phase 5: content-aware candidates; original candidates stay untouched.
    regions.extend(locate_portrait_game_regions(img))
    # Phase six only adds boundary candidates; no existing candidate is removed.
    regions.extend(refine_portrait_game_boundaries(img))
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


def diagnostic_image_match(query, index, target_id='CG-0001'):
    """Read-only v3 diagnostics; ranking algorithm remains unchanged."""
    prepared = prepare_image(query)
    trimmed = remove_thumbnail_padding(query)
    all_regions = query_regions(query)
    target = next(
        ((game, features) for game, features in index
         if str(game.get('id', '')).strip() == target_id),
        None,
    )
    details = {
        'input_size': query.size,
        'prepared_size': prepared.size,
        'trimmed_size': trimmed.size if trimmed is not None else None,
        'target_found': target is not None,
        'regions': [],
    }
    if target is None:
        return details
    for label, region in all_regions:
        features = image_features(region)
        fraction = region.width * region.height / max(1, query.width * query.height)
        penalty = 0.025 * (1 - min(1.0, fraction))
        target_score = max(0.0, similarity(features, target[1]) - penalty)
        higher = sum(
            similarity(features, other_features) - penalty > target_score
            for _, other_features in index
        )
        details['regions'].append({
            'label': label,
            'size': region.size,
            'rank': higher + 1,
            'score': target_score,
        })
    return details



def diagnostic_final_ranking(query, index, target_id='CG-0001'):
    """Read-only audit of the existing best-region ranking, with no score changes."""
    regions = []
    area = max(1, query.width * query.height)
    for label, region in query_regions(query):
        fraction = region.width * region.height / area
        penalty = 0.025 * (1 - min(1.0, fraction))
        regions.append((label, image_features(region), penalty))

    results = []
    for game, features in index:
        if not regions:
            continue
        score, label = max(
            ((similarity(candidate, features) - penalty, label)
             for label, candidate, penalty in regions),
            key=lambda value: value[0],
        )
        results.append({
            'id': str(game.get('id', '')).strip(),
            'name': str(game.get('name', '')),
            'score': max(0.0, score),
            'region': label,
        })
    results.sort(key=lambda item: item['score'], reverse=True)
    target = next(
        ((position, item) for position, item in enumerate(results, 1)
         if item['id'] == target_id),
        None,
    )
    return {
        'target': target,
        'top_five': results[:5],
        'total': len(results),
    }


def diagnostic_score_breakdown(query, index, target_id='CG-0001'):
    """Read-only breakdown of each game's existing best-region score.

    Uses the same regions, penalty, and tie behavior as final ranking.
    Does not modify the search pipeline or its weights.
    """
    area = max(1, query.width * query.height)
    regions = []
    for label, region in query_regions(query):
        fraction = region.width * region.height / area
        penalty = 0.025 * (1 - min(1.0, fraction))
        regions.append((label, image_features(region), penalty))

    rows = []
    for game, features in index:
        if not regions:
            continue
        best = None
        for label, candidate, penalty in regions:
            gray_a, hash_a, hist_a = candidate
            gray_b, hash_b, hist_b = features
            structural = float(np.corrcoef(gray_a.ravel(), gray_b.ravel())[0, 1])
            if not np.isfinite(structural):
                structural = 0.0
            structural = max(0.0, structural)
            hash_score = 1.0 - float(np.mean(hash_a != hash_b))
            color_score = float(np.minimum(hist_a, hist_b).sum() / 3.0)
            raw = similarity(candidate, features)
            adjusted = raw - penalty
            if best is None or adjusted > best['adjusted']:
                best = {
                    'id': str(game.get('id', '')).strip(),
                    'name': str(game.get('name', '')),
                    'region': label,
                    'structural': structural,
                    'hash': hash_score,
                    'color': color_score,
                    'penalty': penalty,
                    'raw': raw,
                    'adjusted': adjusted,
                    'score': max(0.0, adjusted),
                }
        rows.append(best)

    rows.sort(key=lambda row: row['score'], reverse=True)
    selected = rows[:5]
    target = next((row for row in rows if row['id'] == target_id), None)
    if target is not None and all(row['id'] != target_id for row in selected):
        selected.append(target)
    return selected


def diagnostic_aspect_ratio(query, index, target_id='CG-0001'):
    """Inspect source dimensions and letterboxing without changing matching."""
    game = next(
        (game for game, _ in index
         if str(game.get('id', '')).strip() == target_id),
        None,
    )
    output = {
        'query_size': query.size,
        'query_ratio': query.width / max(1, query.height),
        'source_size': None,
        'source_ratio': None,
    }
    if game is None:
        return output
    path = safe_image_path(game)
    if path is None:
        return output
    try:
        with Image.open(path) as image:
            oriented = oriented_game_image(image, game)
            output['source_size'] = oriented.size
            output['source_ratio'] = oriented.width / max(1, oriented.height)
    except (OSError, ValueError, UnidentifiedImageError):
        pass
    return output


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

        selected_providers = []
        if search_mode == '名称 / ID 搜寻':
            selected_providers = st.multiselect(
                '游戏厂商',
                options=providers,
                default=[],
                placeholder='全部厂商（可复选）',
                help='此筛选只影响名称 / ID 搜寻，不影响以图搜图或游戏图片总览。',
                key='selected_game_providers',
            )

        if search_mode == '以图搜图':
            # Keep the current scroll position when changing the top-3/top-5 radio.
            # The browser script only targets this radio; other controls are unchanged.
            components.html("""
            <script>
            (() => {
              const doc = window.parent.document;
              const win = window.parent;
              const key = '__vge_image_rank_scroll';
              if (win.__vgeRankScrollInstalled) return;
              win.__vgeRankScrollInstalled = true;
              const scroller = () => doc.querySelector('[data-testid="stAppViewContainer"]') || doc.scrollingElement;
              doc.addEventListener('change', (ev) => {
                const radio = ev.target.closest('input[type="radio"]');
                if (!radio) return;
                const group = radio.closest('[role="radiogroup"]');
                if (!group || !group.textContent.includes('前 3 名') && !group.textContent.includes('前 5 名')) return;
                const el = scroller();
                win.__vgeRankScrollRestore = {top: el.scrollTop, until: Date.now() + 1800};
              }, true);
              const observer = new MutationObserver(() => {
                const state = win.__vgeRankScrollRestore;
                if (!state) return;
                if (Date.now() > state.until) {win.__vgeRankScrollRestore = null; return;}
                const el = scroller();
                if (Math.abs(el.scrollTop - state.top) > 2) el.scrollTop = state.top;
              });
              observer.observe(doc.body, {childList:true, subtree:true});
            })();
            </script>
            """, height=0)
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
            st.markdown("""
            <style>
            .image-results-heading {display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:.15rem}
            .image-results-heading-title {font-size:1.2rem;font-weight:700}
            .image-results-heading-count {font-size:.88rem;color:#808080}
            </style>
            """, unsafe_allow_html=True)
            if query_image is None:
                image_result_count = None
            else:
                with st.spinner('正在比对数据库图片…'):
                    index = build_image_index()
                    ranked = rank_image_matches(query_image, index, limit=result_limit)
                image_result_count = len(index)
                # Diagnostics are intentionally limited to the isolated v3 test branch.
                with st.expander('🔬 v3 辨識診斷｜CG-0001', expanded=False):
                    diagnostic = diagnostic_image_match(query_image, index)
                    st.caption('僅顯示診斷資訊，不影響實際搜尋排名。')
                    st.write(f"上傳圖片尺寸：{diagnostic['input_size'][0]} × {diagnostic['input_size'][1]}")
                    st.write(f"預處理尺寸：{diagnostic['prepared_size'][0]} × {diagnostic['prepared_size'][1]}")
                    if diagnostic['trimmed_size'] is None:
                        st.write('白邊裁切：未觸發')
                    else:
                        tw, th = diagnostic['trimmed_size']
                        st.write(f'白邊裁切：已觸發，裁切後 {tw} × {th}')
                    final_audit = diagnostic_final_ranking(query_image, index)
                    aspect_audit = diagnostic_aspect_ratio(query_image, index)
                    st.markdown('**第二階段｜最終排序稽核（唯讀）**')
                    target_final = final_audit['target']
                    if target_final is None:
                        st.warning('CG-0001 未出現在最終排序索引。')
                    else:
                        final_position, final_item = target_final
                        st.write(
                            f"CG-0001 最終排名：{final_position} / {final_audit['total']}；"
                            f"最高分：{final_item['score'] * 100:.1f}/100；"
                            f"最佳區域：{final_item['region']}"
                        )
                    st.dataframe(
                        [
                            {
                                '最終排名': i,
                                '遊戲 ID': item['id'],
                                '遊戲名稱': item['name'],
                                '最高分': round(item['score'] * 100, 1),
                                '最佳區域': item['region'],
                            }
                            for i, item in enumerate(final_audit['top_five'], 1)
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                    st.markdown('**第七階段｜相似度分數拆解（唯讀）**')
                    st.caption(
                        '顯示前五名及 CG-0001 各自最佳區域的原始特徵分數；'
                        '權重固定為結構 48%、雜湊 32%、色彩 20%。'
                        '最終分數 = max(0, 加權分數 − 區域面積扣分)。'
                        '此表不影響實際搜尋、裁切或排名。'
                    )
                    breakdown = diagnostic_score_breakdown(query_image, index)
                    st.dataframe(
                        [
                            {
                                '遊戲 ID': item['id'],
                                '最佳區域': item['region'],
                                '結構原始分': round(item['structural'] * 100, 2),
                                '雜湊原始分': round(item['hash'] * 100, 2),
                                '色彩原始分': round(item['color'] * 100, 2),
                                '結構貢獻(48%)': round(item['structural'] * 48, 2),
                                '雜湊貢獻(32%)': round(item['hash'] * 32, 2),
                                '色彩貢獻(20%)': round(item['color'] * 20, 2),
                                '面積扣分': round(item['penalty'] * 100, 2),
                                '最終分數': round(item['score'] * 100, 2),
                            }
                            for item in breakdown
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                    st.markdown('**第二階段｜尺寸及長寬比**')
                    st.write(
                        f"查詢圖片：{aspect_audit['query_size'][0]} × "
                        f"{aspect_audit['query_size'][1]}；"
                        f"寬高比：{aspect_audit['query_ratio']:.3f}"
                    )
                    if aspect_audit['source_size'] is not None:
                        sw, sh = aspect_audit['source_size']
                        st.write(
                            f"CG-0001 索引原圖：{sw} × {sh}；"
                            f"寬高比：{aspect_audit['source_ratio']:.3f}；"
                            f"比例差：{abs(aspect_audit['query_ratio'] - aspect_audit['source_ratio']):.3f}"
                        )
                    st.caption('上述資訊僅供診斷；未變更搜尋特徵、權重、裁切或排序。')
                    if not diagnostic['target_found']:
                        st.warning('CG-0001 不在目前可搜尋的圖片索引中。')
                    else:
                        st.dataframe(
                            [
                                {
                                    '比對區域': item['label'],
                                    '區域尺寸': f"{item['size'][0]} × {item['size'][1]}",
                                    'CG-0001 排名': item['rank'],
                                    '相似分數': round(item['score'] * 100, 1),
                                }
                                for item in diagnostic['regions']
                            ],
                            hide_index=True,
                            use_container_width=True,
                        )
            subtitle = (
                f'v2 多区域搜索 · 已比对 {image_result_count} 张有图片的游戏记录；'
                '缺图游戏不参与图片搜索。'
                if image_result_count is not None else ''
            )
            st.markdown(
                '<div class="image-results-heading">'
                '<span class="image-results-heading-title">图片比对结果</span>'
                f'<span class="image-results-heading-count">{subtitle}</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            if query_image is None:
                st.info(
                    '上传或贴上图片后，'
                    '会自动显示最相似的游戏。'
                )

            else:
                st.image(
                    query_image,
                    caption='待比对截图',
                    width=140,
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
                                [0.65, 2.7, 0.65],
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
                                    render_search_copy_details(
                                        game,
                                        rank=start + 1,
                                        score=score,
                                        matched_region=matched_region,
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

                                render_search_copy_details(game)

                                st.caption(
                                    f"ID：{game.get('id', '无')}"
                                )



@st.fragment
def render_game_gallery():
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

    gallery_selected_providers = st.session_state.get('gallery_selected_providers', [])
    gallery_games = [
        game for game in games
        if not gallery_selected_providers
        or str(game.get('provider', '')).strip() in gallery_selected_providers
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

    # Use the same ordinary vertical layout as the working name/ID selector.
    # Constrain only the outer wrapper width; do not override BaseWeb internals.
    st.markdown(
        """
        <style>
        .st-key-gallery_provider_selector {
            width: 100%;
            max-width: 440px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key='gallery_provider_selector'):
        st.multiselect(
            '总览游戏厂商',
            options=providers,
            default=[],
            placeholder='全部厂商（可复选）',
            help='仅筛选下方游戏图片总览，不影响以图搜图与名称 / ID 搜寻。',
            key='gallery_selected_providers',
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


render_game_gallery()
