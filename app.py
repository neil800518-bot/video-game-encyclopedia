
import json
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "games.json"
IMAGE_DIR = BASE_DIR / "data" / "images"

st.set_page_config(
    page_title="电子游戏百科全书",
    page_icon="🎮",
    layout="wide",
)

st.title("🎮 电子游戏百科全书")
st.caption("Video Game Encyclopedia")
st.write("搜寻游戏名称、筛选游戏厂商，浏览游戏图片。")


def load_games():
    if not DATA_FILE.exists():
        return []

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        st.error("游戏资料库读取失败，请检查 games.json。")
        return []


games = load_games()

search = st.text_input(
    "🔍 搜寻游戏",
    placeholder="输入游戏名称或关键词",
)

providers = sorted({
    str(game.get("provider", "")).strip()
    for game in games
    if isinstance(game, dict) and game.get("provider")
})

provider = st.selectbox(
    "游戏厂商",
    ["全部厂商"] + providers,
)

filtered = []

for game in games:
    if not isinstance(game, dict):
        continue

    name = str(game.get("name", ""))
    game_provider = str(game.get("provider", ""))

    if search.casefold() not in name.casefold():
        continue

    if provider != "全部厂商" and game_provider != provider:
        continue

    filtered.append(game)

st.write(f"共找到 {len(filtered)} 款游戏")

if not filtered:
    st.info("目前没有符合条件的游戏。")
else:
    columns = st.columns(4)

    for index, game in enumerate(filtered):
        with columns[index % 4]:
            image_name = str(game.get("image", ""))
            image_path = IMAGE_DIR / image_name

            if (
                image_name
                and image_path.is_file()
                and image_path.resolve().is_relative_to(
                    IMAGE_DIR.resolve()
                )
            ):
                st.image(str(image_path), use_container_width=True)
            else:
                st.caption("暂无游戏图片")

            st.subheader(str(game.get("name", "未命名游戏")))
            st.caption(str(game.get("provider", "未知厂商")))
