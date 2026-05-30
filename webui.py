from flask import Flask, render_template_string, request
import json
import subprocess
import os

app = Flask(__name__)

CONFIG_PATH = "submap.json"

HTML = """
<!doctype html>
<html>
<head>
    <title>XUI Dashboard</title>
    <style>
        body { font-family: Arial; background:#0f0f0f; color:#eee; margin:20px; }
        table { width:100%; border-collapse: collapse; margin-top:20px; }
        th, td { border:1px solid #333; padding:8px; }
        th { background:#222; }
        input { padding:8px; width:300px; }
        button { padding:8px; margin:5px; cursor:pointer; }
        a { color:#4af; }
        .box { margin-bottom:15px; }
    </style>
</head>
<body>

<h2>📡 XUI Subscription Dashboard</h2>

<div class="box">
<form method="get">
    <input name="q" placeholder="Search email or subId" value="{{q}}">
    <button type="submit">Search</button>
</form>
</div>

<div class="box">
<form method="post" action="/sync">
    <button>🔄 Run Sync Now</button>
</form>
</div>

<p><b>Total users:</b> {{count}}</p>

<table>
<tr>
    <th>Email</th>
    <th>SubID</th>
    <th>File</th>
    <th>Link</th>
</tr>

{% for k,v in data.items() %}
<tr>
    <td>{{v.email}}</td>
    <td>{{k}}</td>
    <td>{{v.filename}}</td>
    <td><a href="{{v.github_url}}" target="_blank">Open</a></td>
</tr>
{% endfor %}
</table>

</body>
</html>
"""


def load_data():
    if not os.path.exists(CONFIG_PATH):
        return {}
    return json.load(open(CONFIG_PATH))


@app.route("/", methods=["GET"])
def index():
    q = request.args.get("q", "").lower()
    data = load_data()

    if q:
        data = {
            k: v for k, v in data.items()
            if q in k.lower() or q in v.get("email", "").lower()
        }

    return render_template_string(HTML, data=data, count=len(data), q=q)


@app.route("/sync", methods=["POST"])
def sync():
    subprocess.Popen(["python", "update.py", "sync"])
    return "<script>window.location='/'</script>"


if __name__ == "__main__":
    port = int(os.getenv("PORT", 2087))
    app.run(host="127.0.0.1", port=port)
