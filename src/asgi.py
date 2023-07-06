import contextlib
import enum
import os
import pathlib
from datetime import datetime, timezone

import asyncpg
import fastapi


DSN = os.environ["DSN"]

app = fastapi.FastAPI()


class Emotion(enum.Enum):
    angry = "angry"
    happy = "happy"
    sad = "sad"
    surprise = "surprise"
    fear = "fear"
    disgust = "disgust"
    contempt = "contempt"


@app.get("/")
async def index():
    return fastapi.responses.HTMLResponse(HTML)


@app.get("/images/{channel_id}/{emotion}.jpg")
async def images(channel_id: str, emotion: Emotion):
    filepath = pathlib.Path(__file__).parent / "images" / channel_id / (emotion.value + ".jpg")
    if filepath.exists():
        return fastapi.responses.FileResponse(filepath)
    else:
        return fastapi.responses.Response(status_code=404)


@app.get("/api")
async def api(order_by: Emotion = Emotion.happy, asc: bool = False):
    async with get_db_pool() as db_pool:
        asc_or_desc = "ASC" if asc else "DESC"
        query = f"""
            SELECT "id", "title", "angry", "happy", "sad", "surprise", "fear", "disgust", "neutral", "contempt"
            FROM "channel"
            WHERE "angry" IS NOT NULL AND "happy" IS NOT NULL AND "sad" IS NOT NULL AND "surprise" IS NOT NULL
            AND "fear" IS NOT NULL AND "disgust" IS NOT NULL AND "neutral" IS NOT NULL AND "contempt" IS NOT NULL
            ORDER BY "{order_by.value}" {asc_or_desc}
        """
        rows = await db_pool.fetch(query)
    return [dict(r) for r in rows]


@contextlib.asynccontextmanager
async def get_db_pool():
    if not hasattr(get_db_pool, "pool"):
        get_db_pool.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=50, command_timeout=60)
    yield get_db_pool.pool


def now():
    return datetime.utcnow().replace(tzinfo=timezone.utc)


HTML = """<!DOCTYPE html>
<html>
    <head>
        <title>YouMood</title>
        <style>
            table {
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
            }
            tr:nth-child(odd) {
                background-color: #f0f0f0;
            }
            tr img {
                width: 100%;
                height: auto;
            }
        </style>
        <script>
            var current_order_by = null;
            var current_asc = false;
            var rowNodes = [];
        
            async function loadList(order_by){
                for (var i=0; i < rowNodes.length; ++i){
                    rowNodes[i].parentNode.removeChild(rowNodes[i]);
                }
                rowNodes = [];
                if (order_by == current_order_by){
                    current_asc = !current_asc;
                } else {
                    current_order_by = order_by;
                    current_asc = false;
                }
                var response = await fetch("/api?order_by=" + current_order_by + "&asc=" + (current_asc ? "1" : "0"));
                var items = await response.json();
                render(items);
            }
            
            function render(items){
                for (var i=0; i < items.length; ++i) {
                    rowNode = createRowNode(items[i]);
                    tableNode.insertBefore(rowNode, null);
                    rowNodes.push(rowNode);
                }
            }
            
            function createRowNode(item){
                var rowNode = document.createElement("tr");

                var titleNode = createTitleNode(item.id, item.title);
                rowNode.appendChild(titleNode);

                rowNode.appendChild(createEmotionNode(item.id, "angry", item.angry));
                rowNode.appendChild(createEmotionNode(item.id, "disgust", item.disgust));
                rowNode.appendChild(createEmotionNode(item.id, "fear", item.fear));
                rowNode.appendChild(createEmotionNode(item.id, "happy", item.happy));
                rowNode.appendChild(createEmotionNode(item.id, "sad", item.sad));
                rowNode.appendChild(createEmotionNode(item.id, "surprise", item.surprise));
                rowNode.appendChild(createEmotionNode(item.id, "contempt", item.contempt));

                return rowNode;
            }
            
            function createTitleNode(id_, title){
                var cellNode = document.createElement("td");
                var linkNode = document.createElement("a");
                linkNode.innerText = title;
                linkNode.href = "https://www.youtube.com/channel/" + id_;
                cellNode.appendChild(linkNode);
                return cellNode;
            }
            
            function createEmotionNode(channel_id, emotion, value){
                var node = document.createElement("td");
                node.innerHTML = `<div>${(value * 100).toFixed(1)}%</div><div><img src="/images/${channel_id}/${emotion}.jpg"></div>`;
                return node;
            }
        </script>
    </head>
    <body>
        <table id="table">
            <tr>
                <th>Title</th>
                <th><a onclick="loadList('angry')" href="#">Angry</a></th>
                <th><a onclick="loadList('disgust')" href="#">Disgust</a></th>
                <th><a onclick="loadList('fear')" href="#">Fear</a></th>
                <th><a onclick="loadList('happy')" href="#">Happy</a></th>
                <th><a onclick="loadList('sad')" href="#">Sad</a></th>
                <th><a onclick="loadList('surprise')" href="#">Surprise</a></th>
                <th><a onclick="loadList('contempt')" href="#">Contempt</a></th>
            </tr>
        </table>
        <script>
            var tableNode = document.getElementById("table");
            loadList("happy");
        </script>
    </body>
</html>
"""
